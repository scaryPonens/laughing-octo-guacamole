import re
import unittest

from ocpp16_min import common


class TestCommon(unittest.TestCase):
    def test_make_call_and_result(self) -> None:
        call = common.make_call("uid-1", "BootNotification", {"a": 1})
        result = common.make_call_result("uid-1", {"ok": True})
        self.assertEqual(call, [2, "uid-1", "BootNotification", {"a": 1}])
        self.assertEqual(result, [3, "uid-1", {"ok": True}])

    def test_new_uid_hex(self) -> None:
        uid = common.new_uid()
        self.assertEqual(len(uid), 32)
        self.assertRegex(uid, r"^[0-9a-f]{32}$")

    def test_is_call(self) -> None:
        self.assertTrue(common.is_call([2, "u", "Heartbeat", {}]))
        self.assertFalse(common.is_call([3, "u", {}]))
        self.assertFalse(common.is_call("not-a-list"))

    def test_is_call_result(self) -> None:
        self.assertTrue(common.is_call_result([3, "u", {}]))
        self.assertFalse(common.is_call_result([2, "u", "Heartbeat", {}]))
        self.assertFalse(common.is_call_result({"not": "a-list"}))

    def test_validate_call_success(self) -> None:
        uid, action, payload = common.validate_call([2, "u1", "Heartbeat", {}])
        self.assertEqual(uid, "u1")
        self.assertEqual(action, "Heartbeat")
        self.assertEqual(payload, {})

    def test_validate_call_errors(self) -> None:
        cases = [
            ("frame must be a JSON list", "bad"),
            ("CALL frame must have length 4", [2, "u"]),
            ("MessageTypeId must be 2 (CALL)", [3, "u", "Heartbeat", {}]),
            ("CALL uid must be a non-empty string", [2, "", "Heartbeat", {}]),
            ("CALL action must be a non-empty string", [2, "u", "", {}]),
            ("CALL payload must be an object", [2, "u", "Heartbeat", "nope"]),
        ]
        for expected, msg in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError) as ctx:
                    common.validate_call(msg)
                self.assertIn(expected, str(ctx.exception))

    def test_make_heartbeat_call_default_uid(self) -> None:
        msg = common.make_heartbeat_call()
        self.assertEqual(msg[0], 2)
        self.assertEqual(msg[2], "Heartbeat")
        self.assertEqual(msg[3], {})
        self.assertRegex(msg[1], r"^[0-9a-f]{32}$")

    def test_make_status_notification_call_defaults(self) -> None:
        msg = common.make_status_notification_call()
        self.assertEqual(msg[0], 2)
        self.assertEqual(msg[2], "StatusNotification")
        payload = msg[3]
        self.assertEqual(payload["connectorId"], 0)
        self.assertEqual(payload["status"], "Available")
        self.assertEqual(payload["errorCode"], "NoError")
        self.assertTrue(payload["timestamp"].endswith("Z"))
        self.assertRegex(payload["timestamp"], r"^\d{4}-\d{2}-\d{2}T")

    def test_parse_message(self) -> None:
        data = common.parse_message('{"a": 1}')
        self.assertEqual(data, {"a": 1})

    def test_parse_call_result_payload(self) -> None:
        payload = common.parse_call_result_payload([3, "u", {"ok": True}])
        self.assertEqual(payload, {"ok": True})
        with self.assertRaises(ValueError):
            common.parse_call_result_payload([2, "u", "Heartbeat", {}])
        with self.assertRaises(ValueError):
            common.parse_call_result_payload([3, "u", "nope"])


if __name__ == "__main__":
    unittest.main()
