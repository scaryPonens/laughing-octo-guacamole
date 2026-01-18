from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


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


def utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_message(text: str) -> Any:
    return json.loads(text)
