from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

BOOTING = "BOOTING"
AVAILABLE = "AVAILABLE"


def make_call(uid: str, action: str, payload: dict[str, Any]) -> list[Any]:
    return [2, uid, action, payload]


def make_call_result(uid: str, payload: dict[str, Any]) -> list[Any]:
    return [3, uid, payload]


def new_uid() -> str:
    return uuid4().hex


def is_call(msg: Any) -> bool:
    return isinstance(msg, list) and len(msg) == 4 and msg[0] == 2


def is_call_result(msg: Any) -> bool:
    return isinstance(msg, list) and len(msg) >= 3 and msg[0] == 3


def validate_call(msg: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(msg, list):
        raise ValueError("frame must be a JSON list")
    if len(msg) != 4:
        raise ValueError("CALL frame must have length 4")
    message_type, uid, action, payload = msg
    if message_type != 2:
        raise ValueError("MessageTypeId must be 2 (CALL)")
    if not isinstance(uid, str) or not uid:
        raise ValueError("CALL uid must be a non-empty string")
    if not isinstance(action, str) or not action:
        raise ValueError("CALL action must be a non-empty string")
    if not isinstance(payload, dict):
        raise ValueError("CALL payload must be an object")
    return uid, action, payload


def make_heartbeat_call(uid: str | None = None) -> list[Any]:
    return make_call(uid or new_uid(), "Heartbeat", {})


def make_status_notification_call(
    uid: str | None = None,
    connector_id: int = 0,
    status: str = "Available",
    error_code: str = "NoError",
) -> list[Any]:
    payload = {
        "connectorId": connector_id,
        "status": status,
        "errorCode": error_code,
        "timestamp": utc_now_iso_z(),
    }
    return make_call(uid or new_uid(), "StatusNotification", payload)


def make_start_transaction_call(
    uid: str | None = None,
    connector_id: int = 1,
    id_tag: str = "TEST",
    meter_start: int = 0,
    timestamp: str | None = None,
) -> list[Any]:
    payload = {
        "connectorId": connector_id,
        "idTag": id_tag,
        "meterStart": meter_start,
        "timestamp": timestamp or utc_now_iso_z(),
    }
    return make_call(uid or new_uid(), "StartTransaction", payload)


def make_stop_transaction_call(
    uid: str | None = None,
    transaction_id: int = 0,
    id_tag: str = "TEST",
    meter_stop: int = 42,
    timestamp: str | None = None,
    reason: str = "Local",
) -> list[Any]:
    payload = {
        "transactionId": transaction_id,
        "meterStop": meter_stop,
        "timestamp": timestamp or utc_now_iso_z(),
        "idTag": id_tag,
        "reason": reason,
    }
    return make_call(uid or new_uid(), "StopTransaction", payload)


def utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_message(text: str) -> Any:
    return json.loads(text)


def parse_call_result_payload(msg: Any) -> dict[str, Any]:
    if not isinstance(msg, list) or len(msg) < 3 or msg[0] != 3:
        raise ValueError("CALLRESULT frame expected")
    payload = msg[2]
    if not isinstance(payload, dict):
        raise ValueError("CALLRESULT payload must be an object")
    return payload


@dataclass
class SessionState:
    transaction_id: int
    connector_id: int
    meter_start: int
    meter_stop: int
