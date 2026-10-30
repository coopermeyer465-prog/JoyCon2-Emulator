import importlib.util
import math
from pathlib import Path
import unittest
from unittest.mock import Mock


FILE = Path(__file__).resolve().parents[1] / "integrations/nxbt/web/joycon2_bridge.py"
spec = importlib.util.spec_from_file_location("joycon2_bridge", FILE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def test_overlay_has_no_mouse_mode(self):
        root = FILE.parent
        javascript = (root / "static/js/main.js").read_text()
        template = (root / "templates/index.html").read_text()
        for marker in ("InputDevice.MOUSE", "captureMouse", "pointerlockchange", "mousePadActive"):
            self.assertNotIn(marker, javascript)
        self.assertNotIn('value="mouse"', template)
        self.assertNotIn('id="mouse-settings"', template)

    def test_packet_mapping_and_lease(self):
        value = bridge.input_step({"A": True, "B": False, "L": True, "ZL": True,
                                   "JCR_SL": True, "L_STICK": {
                                       "X_VALUE": 50, "Y_VALUE": -25, "PRESSED": True}})
        self.assertEqual(value, {"buttons": ["A", "STICK", "SL"], "x": 0.5, "y": -0.25,
                                 "orientation": "sideways-right", "duration": 0.45})

    def test_right_stick_and_raw_mode(self):
        value = bridge.input_step({"L_STICK": {"X_VALUE": 100}, "R_STICK": {"Y_VALUE": 75}}, "right", "raw")
        self.assertEqual((value["x"], value["y"], value["orientation"]), (0, 0.75, "raw"))

    def test_invalid_axes_and_options(self):
        for value in (True, math.inf, math.nan, 101, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.input_step({"L_STICK": {"X_VALUE": value}})
        for stick, orientation in (("both", "raw"), ("left", "unknown")):
            with self.assertRaises(ValueError):
                bridge.input_step({}, stick, orientation)

    def test_backend_readiness_is_not_just_connection(self):
        instance = bridge.JoyCon2Bridge()
        instance.request = Mock(return_value={"ready": False, "connected": True})
        self.assertEqual(instance.status()["state"], "connecting")
        instance.request.return_value["ready"] = True
        self.assertEqual(instance.status()["state"], "connected")
