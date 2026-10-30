"""Run in the existing NXBT environment; mocks all Bluetooth/process operations."""

import importlib
import json
import unittest
from unittest.mock import Mock


web = importlib.import_module("nxbt.web.app")


class WebTests(unittest.TestCase):
    def setUp(self):
        self.original = web.nxbt, web.joycon2, web.emit
        self.background = web.sio.start_background_task
        web.sio.start_background_task = Mock()
        # The installed Flask-SocketIO test client's outgoing hook predates its
        # python-socketio dependency. Capture emits, retaining real event dispatch.
        web.emit = Mock()
        web.nxbt = None
        web.joycon2 = Mock()
        web.joycon2.mouse_test_active = False
        web.joycon2.generation = 1
        web.joycon2.status.return_value = {"state": "connected", "errors": []}
        web.joycon2_owner = None
        web.USER_INFO.clear()
        self.owner = web.sio.test_client(web.app)
        self.other = web.sio.test_client(web.app)

    def tearDown(self):
        self.owner.disconnect()
        self.other.disconnect()
        web.nxbt, web.joycon2, web.emit = self.original
        web.sio.start_background_task = self.background
        web.joycon2_owner = None

    def create(self):
        self.owner.emit("web_create_pro_controller", {"backend": "joycon2_right"})
        web.emit.assert_any_call("create_pro_controller", -1)

    def test_create_state_input_and_disconnect(self):
        self.create()
        self.owner.emit("state")
        self.assertEqual(web.emit.call_args.args[0], "state")
        self.owner.emit("input", json.dumps([-1, {"A": True}, {"stick": "right", "orientation": "raw"}]))
        value = web.joycon2.request.call_args.args[0]
        self.assertEqual(value["state"]["buttons"], ["A"])
        self.assertEqual(value["state"]["duration"], 0.45)
        self.owner.emit("shutdown", -1)
        web.joycon2.stop.assert_called_once()
        self.assertIsNone(web.joycon2_owner)

    def test_non_owner_cannot_input_shutdown_or_run_macro(self):
        self.create()
        self.other.emit("input", json.dumps([-1, {"HOME": True}]))
        self.other.emit("macro", json.dumps([-1, "[]"]))
        self.other.emit("shutdown", -1)
        self.other.emit("joycon2_join")
        web.joycon2.request.assert_not_called()
        web.joycon2.stop.assert_not_called()
        self.assertIsNotNone(web.joycon2_owner)

    def test_refuses_radio_conflict(self):
        self.create()
        self.other.emit("web_create_pro_controller", {"backend": "pro"})
        self.assertEqual(web.emit.call_args.args[0], "error")
        self.assertIsNone(web.nxbt)

    def test_allowlisted_extra_buttons_and_stop_ack(self):
        self.create()
        for button in web.RIGHT_BUTTON_NAMES:
            self.owner.emit("joycon2_button", button)
            web.joycon2.request.assert_called_with({"op": "set", "state": {
                "buttons": [button], "duration": 0.05 if button == "HOME" else 0.1}})
        web.joycon2.request.reset_mock()
        self.owner.emit("joycon2_button", "ZL")
        self.other.emit("joycon2_button", "C")
        web.joycon2.request.assert_not_called()
        result = self.owner.emit("shutdown", -1, callback=True)
        self.assertEqual(result, {"ok": True})
        self.assertIsNone(web.joycon2_owner)

    def test_pro_choice_keeps_original_nxbt_route(self):
        web.nxbt = Mock()
        web.nxbt.get_switch_addresses.return_value = ["AA:BB:CC:DD:EE:FF"]
        web.nxbt.create_controller.return_value = 3
        self.owner.emit("web_create_pro_controller", {"backend": "pro"})
        web.emit.assert_any_call("create_pro_controller", 3)
        web.nxbt.create_controller.assert_called_once_with(web.PRO_CONTROLLER,
            reconnect_address=["AA:BB:CC:DD:EE:FF"])
        web.joycon2.stop.assert_called_once()

    def test_explicit_sideways_face_layout_for_taps_and_live_input(self):
        self.create()
        self.owner.emit("joycon2_button", {"button": "A", "layout": "sideways-right"})
        web.joycon2.request.assert_called_with({"op": "set", "state": {"buttons": ["X"], "duration": 0.1}})
        self.owner.emit("input", json.dumps([-1, {"B": True}, {"button_layout": "sideways-right"}]))
        self.assertEqual(web.joycon2.request.call_args.args[0]["state"]["buttons"], ["A"])

    def test_sequence_preserves_json_and_disconnect_stops_backend(self):
        self.create()
        steps = [{"buttons": ["HOME"], "duration": 0.05}]
        self.owner.emit("macro", json.dumps([-1, json.dumps(steps)]))
        web.joycon2.request.assert_called_with({"op": "sequence", "steps": steps})
        self.owner.disconnect()
        web.joycon2.stop.assert_called_once()
        self.owner = web.sio.test_client(web.app)

    def test_reconnect_is_owner_only_and_does_not_reset_controller_ownership(self):
        self.create()
        self.assertFalse(self.other.emit("joycon2_reconnect", callback=True)["ok"])
        self.assertTrue(self.owner.emit("joycon2_reconnect", callback=True)["ok"])
        web.joycon2.reconnect.assert_called_once_with()
        self.assertIsNotNone(web.joycon2_owner)
        web.joycon2.mouse_test_active = True
        self.assertFalse(self.owner.emit("joycon2_reconnect", callback=True)["ok"])

    def test_native_mouse_ownership_validation_and_normal_input_suppression(self):
        self.create()
        self.assertFalse(self.other.emit("joycon2_mouse_test", callback=True)["ok"])
        self.assertTrue(self.owner.emit("joycon2_mouse_test", callback=True)["ok"])
        web.joycon2.start.assert_called_with(native_mouse=True)
        web.sio.start_background_task.assert_called_once()
        web.joycon2.mouse_test_active = True
        web.joycon2.request.reset_mock()
        self.owner.emit("input", json.dumps([-1, {"HOME": True}]))
        self.other.emit("joycon2_mouse", {"dx": 10}, callback=True)
        for value in ({"dx": True}, {"dx": 2048}, {"dy": 1.5}, {"dx": 1, "lifted": True},
                      {"surface": 0}, None):
            self.assertFalse(self.owner.emit("joycon2_mouse", value, callback=True)["ok"])
        web.joycon2.request.assert_not_called()
        self.assertTrue(self.owner.emit("joycon2_mouse", {"dx": 12, "dy": -3}, callback=True)["ok"])
        web.joycon2.request.assert_called_with({"op": "mouse", "dx": 12, "dy": -3, "surface": 50})
        self.owner.emit("joycon2_mouse", {"lifted": True}, callback=True)
        web.joycon2.request.assert_called_with({"op": "mouse", "dx": 0, "dy": 0, "lifted": True})
        self.assertFalse(self.other.emit("joycon2_mouse_stop", callback=True)["ok"])
        self.assertTrue(self.owner.emit("joycon2_mouse_stop", callback=True)["ok"])
        web.joycon2.start.assert_called_with()

    def test_native_expiry_restores_only_the_same_owner_and_generation(self):
        self.create()
        owner = web.joycon2_owner
        web.joycon2.active.return_value = False
        web.joycon2.start.reset_mock()
        web.restore_after_mouse(owner, 1)
        web.joycon2.start.assert_called_once_with()
        web.joycon2.start.reset_mock()
        web.joycon2.generation = 2
        web.restore_after_mouse(owner, 1)
        web.joycon2.start.assert_not_called()

    def test_native_mouse_click_and_release_require_owner_and_explicit_mode(self):
        self.create()
        web.joycon2.request.reset_mock()
        self.assertFalse(self.owner.emit("joycon2_mouse_click", callback=True)["ok"])
        web.joycon2.mouse_test_active = True
        self.assertFalse(self.other.emit("joycon2_mouse_click", callback=True)["ok"])
        self.assertFalse(self.other.emit("joycon2_mouse_release", callback=True)["ok"])
        self.assertFalse(self.owner.emit("joycon2_mouse_click", {"button": "HOME"}, callback=True)["ok"])
        web.joycon2.request.assert_not_called()
        self.assertTrue(self.owner.emit("joycon2_mouse_click", callback=True)["ok"])
        web.joycon2.request.assert_called_with({"op": "mouse_click"})
        self.assertTrue(self.owner.emit("joycon2_mouse_release", callback=True)["ok"])
        web.joycon2.request.assert_called_with({"op": "release"})


if __name__ == "__main__":
    unittest.main()
