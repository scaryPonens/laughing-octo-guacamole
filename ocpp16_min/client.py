from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import sys

import websockets
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .common import (
    AVAILABLE,
    BOOTING,
    is_call_result,
    make_call,
    make_heartbeat_call,
    make_status_notification_call,
    make_start_transaction_call,
    make_stop_transaction_call,
    new_uid,
    parse_call_result_payload,
    parse_message,
    SessionState,
)

logger = logging.getLogger(__name__)


def _boot_notification_payload() -> dict[str, str]:
    return {
        "chargePointVendor": "RalphCo",
        "chargePointModel": "RalphModel1",
        "firmwareVersion": "0.1.0",
        "meterType": "RalphMeter",
    }


def setup_tracing() -> None:
    service_name = os.getenv("OTEL_SERVICE_NAME", "ocpp16-client")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    atexit.register(provider.shutdown)


class SpanEventHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        span = trace.get_current_span()
        if span and span.is_recording():
            span.add_event(
                "log",
                {
                    "log.level": record.levelname,
                    "log.message": record.getMessage(),
                    "log.logger": record.name,
                },
            )


async def _heartbeat_loop(
    websocket: websockets.WebSocketClientProtocol,
    interval: int,
    ws_lock: asyncio.Lock,
    max_count: int = 3,
) -> None:
    for idx in range(max_count):
        await asyncio.sleep(interval)
        heartbeat_call = make_heartbeat_call()
        heartbeat_uid = heartbeat_call[1]
        async with ws_lock:
            await websocket.send(json.dumps(heartbeat_call))
            logger.info("Heartbeat %s sent", idx + 1)
            heartbeat_response_text = await websocket.recv()
        logger.info("RAW RESPONSE: %s", heartbeat_response_text)
        try:
            heartbeat_response = parse_message(heartbeat_response_text)
        except json.JSONDecodeError:
            logger.error("Heartbeat %s: invalid JSON response", idx + 1)
            return
        logger.info("PARSED RESPONSE: %s", heartbeat_response)
        if (
            not is_call_result(heartbeat_response)
            or heartbeat_response[1] != heartbeat_uid
        ):
            logger.error("Heartbeat %s: invalid CALLRESULT", idx + 1)
            return
        try:
            parse_call_result_payload(heartbeat_response)
        except ValueError as exc:
            logger.error("Heartbeat %s: response error: %s", idx + 1, exc)
            return
        logger.info("Heartbeat %s acknowledged", idx + 1)


async def main() -> int:
    setup_tracing()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    logger.addHandler(SpanEventHandler())
    state = BOOTING
    uri = "ws://localhost:9000/CP_1"
    uid = new_uid()
    payload = _boot_notification_payload()
    message = json.dumps(make_call(uid, "BootNotification", payload))
    with trace.get_tracer(__name__).start_as_current_span("ws.client") as span:
        try:
            carrier: dict[str, str] = {}
            span.set_attribute("ws.uri", uri)
            span.set_attribute("ws.message", message)
            propagate.inject(carrier)
            connect_kwargs = {"additional_headers": carrier}
            try:
                connect_ctx = websockets.connect(uri, **connect_kwargs)
            except TypeError:
                connect_ctx = websockets.connect(uri, extra_headers=carrier)

            async with connect_ctx as websocket:
                span.set_attribute("ws.connected", True)
                await websocket.send(message)
                response_text = await websocket.recv()
                span.set_attribute("ws.response_text", response_text)
                logger.info("RAW RESPONSE: %s", response_text)
                try:
                    response = parse_message(response_text)
                except json.JSONDecodeError:
                    logger.error("PARSED RESPONSE: <invalid JSON>")
                    return 1

                logger.info("PARSED RESPONSE: %s", response)
                if not is_call_result(response) or response[1] != uid:
                    logger.error("BootNotification response is not a valid CALLRESULT")
                    span.set_attribute("ws.response_status", "Invalid")
                    return 1

                try:
                    boot_payload = parse_call_result_payload(response)
                except ValueError as exc:
                    logger.error("BootNotification response error: %s", exc)
                    span.set_attribute("ws.response_status", "Invalid")
                    return 1
                status = boot_payload.get("status")
                if status != "Accepted":
                    logger.error("BootNotification not accepted: %s", status)
                    span.set_attribute("ws.response_status", "Rejected")
                    return 1

                interval = boot_payload.get("interval")
                if not isinstance(interval, int) or interval <= 0:
                    interval = 10
                span.set_attribute("ocpp.heartbeat_interval", interval)
                span.set_attribute("ws.response_status", "Accepted")
                logger.info("Boot accepted. Heartbeat interval=%s", interval)

                state = AVAILABLE
                logger.info("State transition: %s -> %s", BOOTING, state)
                status_call = make_status_notification_call(connector_id=0, status="Available", error_code="NoError")
                status_uid = status_call[1]
                await websocket.send(json.dumps(status_call))
                logger.info("StatusNotification sent (Available)")
                status_response_text = await websocket.recv()
                logger.info("RAW RESPONSE: %s", status_response_text)
                try:
                    status_response = parse_message(status_response_text)
                except json.JSONDecodeError:
                    logger.error("StatusNotification: invalid JSON response")
                    return 1
                logger.info("PARSED RESPONSE: %s", status_response)
                if not is_call_result(status_response) or status_response[1] != status_uid:
                    logger.error("StatusNotification: invalid CALLRESULT")
                    return 1
                try:
                    parse_call_result_payload(status_response)
                except ValueError as exc:
                    logger.error("StatusNotification response error: %s", exc)
                    return 1
                logger.info("StatusNotification acknowledged")

                start_call = make_start_transaction_call(
                    connector_id=1,
                    id_tag="TEST",
                    meter_start=0,
                )
                start_uid = start_call[1]
                await websocket.send(json.dumps(start_call))
                logger.info("StartTransaction sent (connectorId=1)")
                start_response_text = await websocket.recv()
                logger.info("RAW RESPONSE: %s", start_response_text)
                try:
                    start_response = parse_message(start_response_text)
                except json.JSONDecodeError:
                    logger.error("StartTransaction: invalid JSON response")
                    return 1
                logger.info("PARSED RESPONSE: %s", start_response)
                if not is_call_result(start_response) or start_response[1] != start_uid:
                    logger.error("StartTransaction: invalid CALLRESULT")
                    return 1
                try:
                    start_payload = parse_call_result_payload(start_response)
                except ValueError as exc:
                    logger.error("StartTransaction response error: %s", exc)
                    return 1
                transaction_id = start_payload.get("transactionId")
                id_tag_info = start_payload.get("idTagInfo", {})
                if not isinstance(transaction_id, int):
                    logger.error("StartTransaction: missing transactionId")
                    return 1
                if not isinstance(id_tag_info, dict) or id_tag_info.get("status") != "Accepted":
                    logger.error("StartTransaction not accepted")
                    return 1
                session = SessionState(
                    transaction_id=transaction_id,
                    connector_id=1,
                    meter_start=0,
                    meter_stop=42,
                )
                logger.info("StartTransaction acknowledged (transactionId=%s)", session.transaction_id)

                ws_lock = asyncio.Lock()
                heartbeat_task = asyncio.create_task(
                    _heartbeat_loop(websocket, interval, ws_lock, max_count=3)
                )
                await asyncio.sleep(10)

                stop_call = make_stop_transaction_call(
                    transaction_id=session.transaction_id,
                    id_tag="TEST",
                    meter_stop=session.meter_stop,
                    reason="Local",
                )
                stop_uid = stop_call[1]
                async with ws_lock:
                    await websocket.send(json.dumps(stop_call))
                    logger.info("StopTransaction sent (transactionId=%s)", session.transaction_id)
                    stop_response_text = await websocket.recv()
                logger.info("RAW RESPONSE: %s", stop_response_text)
                try:
                    stop_response = parse_message(stop_response_text)
                except json.JSONDecodeError:
                    logger.error("StopTransaction: invalid JSON response")
                    return 1
                logger.info("PARSED RESPONSE: %s", stop_response)
                if not is_call_result(stop_response) or stop_response[1] != stop_uid:
                    logger.error("StopTransaction: invalid CALLRESULT")
                    return 1
                try:
                    stop_payload = parse_call_result_payload(stop_response)
                except ValueError as exc:
                    logger.error("StopTransaction response error: %s", exc)
                    return 1
                stop_tag_info = stop_payload.get("idTagInfo", {})
                if not isinstance(stop_tag_info, dict) or stop_tag_info.get("status") != "Accepted":
                    logger.error("StopTransaction not accepted")
                    return 1
                logger.info("StopTransaction acknowledged (transactionId=%s)", session.transaction_id)

                await heartbeat_task
                return 0
        except ConnectionRefusedError:
            logger.error("Could not connect to server")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
