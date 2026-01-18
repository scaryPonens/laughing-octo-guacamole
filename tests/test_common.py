import re

import pytest

from ocpp16_min import common


def test_make_call_and_result() -> None:
    call = common.make_call("uid-1", "BootNotification", {"a": 1})
    result = common.make_call_result("uid-1", {"ok": True})
    assert call == [2, "uid-1", "BootNotification", {"a": 1}]
    assert result == [3, "uid-1", {"ok": True}]


def test_new_uid_hex() -> None:
    uid = common.new_uid()
    assert len(uid) == 32
    assert re.fullmatch(r"[0-9a-f]{32}", uid)


def test_is_call() -> None:
    assert common.is_call([2, "u", "Heartbeat", {}])
    assert not common.is_call([3, "u", {}])
    assert not common.is_call("not-a-list")


def test_is_call_result() -> None:
    assert common.is_call_result([3, "u", {}])
    assert not common.is_call_result([2, "u", "Heartbeat", {}])
    assert not common.is_call_result({"not": "a-list"})


def test_validate_call_success() -> None:
    uid, action, payload = common.validate_call([2, "u1", "Heartbeat", {}])
    assert uid == "u1"
    assert action == "Heartbeat"
    assert payload == {}


@pytest.mark.parametrize(
    "expected,msg",
    [
        ("frame must be a JSON list", "bad"),
        ("CALL frame must have length 4", [2, "u"]),
        ("MessageTypeId must be 2 (CALL)", [3, "u", "Heartbeat", {}]),
        ("CALL uid must be a non-empty string", [2, "", "Heartbeat", {}]),
        ("CALL action must be a non-empty string", [2, "u", "", {}]),
        ("CALL payload must be an object", [2, "u", "Heartbeat", "nope"]),
    ],
)
def test_validate_call_errors(expected: str, msg: object) -> None:
    with pytest.raises(ValueError) as excinfo:
        common.validate_call(msg)
    assert expected in str(excinfo.value)


def test_make_heartbeat_call_default_uid() -> None:
    msg = common.make_heartbeat_call()
    assert msg[0] == 2
    assert msg[2] == "Heartbeat"
    assert msg[3] == {}
    assert re.fullmatch(r"[0-9a-f]{32}", msg[1])


def test_make_status_notification_call_defaults() -> None:
    msg = common.make_status_notification_call()
    assert msg[0] == 2
    assert msg[2] == "StatusNotification"
    payload = msg[3]
    assert payload["connectorId"] == 0
    assert payload["status"] == "Available"
    assert payload["errorCode"] == "NoError"
    assert payload["timestamp"].endswith("Z")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*Z", payload["timestamp"])


def test_parse_message() -> None:
    data = common.parse_message('{"a": 1}')
    assert data == {"a": 1}


def test_parse_call_result_payload() -> None:
    payload = common.parse_call_result_payload([3, "u", {"ok": True}])
    assert payload == {"ok": True}
    with pytest.raises(ValueError):
        common.parse_call_result_payload([2, "u", "Heartbeat", {}])
    with pytest.raises(ValueError):
        common.parse_call_result_payload([3, "u", "nope"])
