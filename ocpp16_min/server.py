from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os

import websockets
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from websockets.exceptions import ConnectionClosed

try:
    from .common import make_call_result, parse_message, utc_now_iso_z, validate_call
except ImportError:  # Allows running as a script without -m
    from common import make_call_result, parse_message, utc_now_iso_z, validate_call

CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4
HEARTBEAT_INTERVAL_SECONDS = 10
_next_transaction_id = 1
_active_transactions: dict[int, dict[str, object]] = {}


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def setup_tracing() -> None:
    service_name = os.getenv("OTEL_SERVICE_NAME", "ocpp16-server")
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


def _call_error(uid: str, code: str, description: str) -> list[object]:
    return [CALL_ERROR, uid, code, description, {}]


async def _send_error_and_close(websocket: websockets.WebSocketServerProtocol, text: str) -> None:
    await websocket.send(text)
    await websocket.close(code=1002, reason=text)


async def handle_client(websocket: websockets.WebSocketServerProtocol) -> None:
    request = getattr(websocket, "request", None)
    path = getattr(websocket, "path", None)
    if path is None and request is not None:
        path = getattr(request, "path", None)
    charge_point_id = ((path or "/").lstrip("/")) or "unknown"
    logger.info("Client connected: %s", charge_point_id)

    try:
        request_headers = getattr(websocket, "request_headers", None)
        if request_headers is None:
            request_headers = getattr(request, "headers", None)
        if request_headers is None:
            request_headers = {}

        parent_context = propagate.extract(request_headers)
        async for message in websocket:
            with tracer.start_as_current_span("ws.message", context=parent_context) as span:
                span.set_attribute("ocpp.charge_point_id", charge_point_id)
                span.set_attribute("ws.message_length", len(message))
                logger.info("Received raw: %s", message)

                try:
                    data = parse_message(message)
                except json.JSONDecodeError as exc:
                    await _send_error_and_close(websocket, f"ERROR: invalid JSON ({exc.msg})")
                    return

                try:
                    uid, action, payload = validate_call(data)
                except ValueError as exc:
                    await _send_error_and_close(websocket, f"ERROR: {exc}")
                    return

                logger.info("Parsed CALL: action=%s uid=%s", action, uid)

                if action == "BootNotification":
                    result_payload = {
                        "status": "Accepted",
                        "currentTime": utc_now_iso_z(),
                        "interval": HEARTBEAT_INTERVAL_SECONDS,
                    }
                elif action == "Heartbeat":
                    result_payload = {"currentTime": utc_now_iso_z()}
                elif action == "StatusNotification":
                    connector_id = payload.get("connectorId")
                    status = payload.get("status")
                    error_code = payload.get("errorCode")
                    if connector_id not in (0, 1):
                        await _send_error_and_close(websocket, "ERROR: connectorId must be 0 or 1")
                        return
                    if status != "Available":
                        await _send_error_and_close(websocket, "ERROR: status must be Available")
                        return
                    if error_code != "NoError":
                        await _send_error_and_close(websocket, "ERROR: errorCode must be NoError")
                        return
                    logger.info("StatusNotification: connectorId=%s status=%s", connector_id, status)
                    result_payload = {}
                elif action == "StartTransaction":
                    connector_id = payload.get("connectorId")
                    id_tag = payload.get("idTag")
                    meter_start = payload.get("meterStart")
                    timestamp = payload.get("timestamp")
                    if connector_id not in (0, 1):
                        await _send_error_and_close(websocket, "ERROR: connectorId must be 0 or 1")
                        return
                    if not isinstance(id_tag, str) or not id_tag:
                        await _send_error_and_close(websocket, "ERROR: idTag must be a non-empty string")
                        return
                    if not isinstance(meter_start, int):
                        await _send_error_and_close(websocket, "ERROR: meterStart must be an integer")
                        return
                    if not isinstance(timestamp, str) or not timestamp:
                        await _send_error_and_close(websocket, "ERROR: timestamp must be a string")
                        return
                    global _next_transaction_id
                    transaction_id = _next_transaction_id
                    _next_transaction_id += 1
                    _active_transactions[transaction_id] = {
                        "chargePointId": charge_point_id,
                        "connectorId": connector_id,
                        "meterStart": meter_start,
                    }
                    logger.info(
                        "StartTransaction: chargePointId=%s transactionId=%s",
                        charge_point_id,
                        transaction_id,
                    )
                    result_payload = {
                        "transactionId": transaction_id,
                        "idTagInfo": {"status": "Accepted"},
                    }
                elif action == "StopTransaction":
                    transaction_id = payload.get("transactionId")
                    meter_stop = payload.get("meterStop")
                    timestamp = payload.get("timestamp")
                    if not isinstance(transaction_id, int):
                        await _send_error_and_close(websocket, "ERROR: transactionId must be an integer")
                        return
                    if not isinstance(meter_stop, int):
                        await _send_error_and_close(websocket, "ERROR: meterStop must be an integer")
                        return
                    if not isinstance(timestamp, str) or not timestamp:
                        await _send_error_and_close(websocket, "ERROR: timestamp must be a string")
                        return
                    _active_transactions.pop(transaction_id, None)
                    logger.info(
                        "StopTransaction: transactionId=%s meterStop=%s",
                        transaction_id,
                        meter_stop,
                    )
                    result_payload = {"idTagInfo": {"status": "Accepted"}}
                else:
                    error = _call_error(
                        uid,
                        "NotSupported",
                        "Only BootNotification, Heartbeat, StatusNotification, StartTransaction, and StopTransaction are supported",
                    )
                    error_text = json.dumps(error)
                    await websocket.send(error_text)
                    logger.info("Sent: %s", error_text)
                    continue

                response = make_call_result(uid, result_payload)
                response_text = json.dumps(response)
                await websocket.send(response_text)
                logger.info("Sent: %s", response_text)
    except ConnectionClosed:
        pass
    finally:
        logger.info("Client disconnected: %s", charge_point_id)


async def main() -> None:
    setup_tracing()
    logger.addHandler(SpanEventHandler())
    host = os.getenv("APP_HOST", "localhost")
    port = int(os.getenv("APP_PORT", "9000"))
    logger.info("Starting server on ws://%s:%s/{chargePointId}", host, port)
    async with websockets.serve(handle_client, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
