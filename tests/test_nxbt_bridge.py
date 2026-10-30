import importlib.util
from html.parser import HTMLParser
import math
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from joycon2_emulator.control import InputState
from joycon2_emulator.protocol import RIGHT_BUTTONS, right_report


FILE = Path(__file__).resolve().parents[1] / "integrations/nxbt/web/joycon2_bridge.py"
spec = importlib.util.spec_from_file_location("joycon2_bridge", FILE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def test_every_right_button_is_available_on_the_web_pad(self):
        class Buttons(HTMLParser):
            def __init__(self):
                super().__init__()
                self.handlers = set()

            def handle_starttag(self, tag, attrs):
                if tag == "button":
                    self.handlers.add(dict(attrs).get("onclick"))

        buttons = Buttons()
        buttons.feed((FILE.parent / "templates/index.html").read_text())
        for name in RIGHT_BUTTONS:
            self.assertIn(f"tapJoyCon('{name}')", buttons.handlers)

    def test_every_right_button_through_bridge_state_and_wire_report(self):
        self.assertEqual(set(bridge.RIGHT_BUTTON_NAMES), set(RIGHT_BUTTONS))
        for name, bit in RIGHT_BUTTONS.items():
            for source in ("left", "right"):
                with self.subTest(button=name, stick=source):
                    if name == "STICK":
                        packet = {"L_STICK" if source == "left" else "R_STICK": {"PRESSED": True}}
                    else:
                        packet = {{"SL": "JCR_SL", "SR": "JCR_SR"}.get(name, name): True}
                    value = bridge.input_step(packet, source)
                    state = InputState()
                    state.connected = state.ready = True
                    state.execute({"op": "set", "state": value}, 0)
                    buttons, _, _ = state.snapshot(0.1)
                    report = right_report(buttons=buttons)
                    self.assertEqual(int.from_bytes(report[2:4], "little"), 1 << bit)
                    self.assertEqual(state.snapshot(0.45), ((), 0, 0))

    def test_all_raw_stick_directions_and_diagonals_through_both_sources(self):
        for source in ("left", "right"):
            for x, y in ((100, 0), (-100, 0), (0, 100), (0, -100),
                         (100, 100), (100, -100), (-100, 100), (-100, -100), (0, 0)):
                with self.subTest(stick=source, x=x, y=y):
                    packet = {"L_STICK" if source == "left" else "R_STICK": {"X_VALUE": x, "Y_VALUE": y}}
                    value = bridge.input_step(packet, source, "raw")
                    state = InputState()
                    state.ready = True
                    state.execute({"op": "set", "state": value}, 0)
                    self.assertEqual(state.snapshot(0.1), ((), x / 100, y / 100))

    def test_overlay_mouse_is_separate_and_off_by_default(self):
        root = FILE.parent
        javascript = (root / "static/js/main.js").read_text()
        template = (root / "templates/index.html").read_text()
        self.assertNotIn("InputDevice.MOUSE", javascript)
        self.assertIn('id="mouse-surface"', template)
        self.assertIn('<option value="off">Off</option>', template)
        self.assertIn('value="native" disabled', template)
        self.assertIn('value="left"', template)
        self.assertIn('value="right"', template)
        self.assertIn('nativeMouseRequested', javascript)

    def test_packet_mapping_and_lease(self):
        value = bridge.input_step({"A": True, "B": False, "L": True, "ZL": True,
                                   "JCR_SL": True, "L_STICK": {
                                       "X_VALUE": 50, "Y_VALUE": -25, "PRESSED": True}})
        self.assertEqual(value, {"buttons": ["A", "STICK", "SL"], "x": 0.5, "y": -0.25,
                                 "orientation": "sideways-right", "duration": 0.45})

    def test_right_stick_and_raw_mode(self):
        value = bridge.input_step({"L_STICK": {"X_VALUE": 100}, "R_STICK": {"Y_VALUE": 75}}, "right", "raw")
        self.assertEqual((value["x"], value["y"], value["orientation"]), (0, 0.75, "raw"))

    def test_sideways_face_layout_is_independent_of_stick_orientation(self):
        mapping = {"A": "X", "B": "A", "X": "Y", "Y": "B"}
        for logical, physical in mapping.items():
            value = bridge.input_step({logical: True}, orientation="raw", button_layout="sideways-right")
            self.assertEqual(value["buttons"], [physical])
            self.assertEqual(bridge.map_button(logical), logical)
            self.assertEqual(bridge.map_button(logical, "sideways-right"), physical)
        for button in set(RIGHT_BUTTONS) - set(mapping):
            self.assertEqual(bridge.map_button(button, "sideways-right"), button)
        with self.assertRaises(ValueError):
            bridge.input_step({}, button_layout="unknown")

    def test_invalid_axes_and_options(self):
        for value in (True, math.inf, math.nan, 101, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.input_step({"L_STICK": {"X_VALUE": value}})
        for stick, orientation in (("both", "raw"), ("left", "unknown")):
            with self.assertRaises(ValueError):
                bridge.input_step({}, stick, orientation)

    def test_backend_readiness_is_not_just_connection(self):
        instance = bridge.JoyCon2Bridge()
        instance.config = {"project": "/nonexistent-private-project"}
        instance.request = Mock(return_value={"ready": False, "connected": True})
        self.assertEqual(instance.status()["state"], "connecting")
        instance.request.return_value["ready"] = True
        self.assertEqual(instance.status()["state"], "connected")

    def test_native_web_session_is_bounded_and_separate_from_auto_join(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".state").mkdir()
            for name in ("bond.json", "factory-calibration.json", "mouse-motion.json"):
                (project / ".state" / name).write_text("{}")
            config = {"project": directory, "python": "/usr/bin/python3", "pythonpath": "/deps",
                      "address": "00:11:22:33:44:55"}
            path = project / "config.json"
            path.write_text(json.dumps(config))
            instance = bridge.JoyCon2Bridge(path)
            instance.active = Mock(return_value=False)
            instance.run = Mock()
            instance.request = Mock(return_value={"ready": False})
            instance.start(native_mouse=True)
            command = next(call.args for call in instance.run.call_args_list if call.args[0] == "systemd-run")
            self.assertIn("--property=RuntimeMaxSec=315", command)
            self.assertIn("--replay-command-mouse", command)
            self.assertEqual(command[command.index("--seconds") + 1], "300")
            self.assertNotIn("--auto-join", command)
            self.assertTrue(instance.mouse_test_active)
            generation = instance.generation
            instance.run.reset_mock()
            instance.start()
            command = next(call.args for call in instance.run.call_args_list if call.args[0] == "systemd-run")
            self.assertIn("--auto-join", command)
            self.assertNotIn("--experimental-sensor-replay", command)
            self.assertFalse(instance.mouse_test_active)
            self.assertGreater(instance.generation, generation)

    def test_reconnect_preserves_bond_and_restarts_normal_mode(self):
        instance = bridge.JoyCon2Bridge()
        instance.stop = Mock()
        instance.start = Mock(return_value={"ready": True})
        self.assertEqual(instance.reconnect(), {"ready": True})
        instance.stop.assert_called_once_with()
        instance.start.assert_called_once_with()
