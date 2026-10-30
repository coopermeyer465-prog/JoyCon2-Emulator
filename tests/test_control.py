import math
from pathlib import Path
import tempfile
import unittest

from joycon2_emulator.control import ControlServer, InputState, send


class InputStateTests(unittest.TestCase):
    def setUp(self):
        self.state = InputState()
        self.state.ready = self.state.connected = True

    def test_timed_chord_releases(self):
        result = self.state.execute({"op": "set", "state": {"buttons": ["SL", "SR"], "duration": 0.25}}, 10)
        self.assertTrue(result["ok"])
        self.assertEqual(self.state.snapshot(10.1), (("SL", "SR"), 0.0, 0.0))
        self.assertEqual(self.state.snapshot(10.25), ((), 0.0, 0.0))

    def test_sideways_right_screen_directions(self):
        for x, y, raw_x, raw_y in ((1, 0, 0, 1), (-1, 0, 0, -1),
                                    (0, 1, -1, 0), (0, -1, 1, 0),
                                    (0.5, -0.25, 0.25, 0.5)):
            with self.subTest(x=x, y=y):
                self.state.execute({"op": "set", "state": {
                    "x": x, "y": y, "orientation": "sideways-right", "duration": 0.1}}, 0)
                self.assertEqual(self.state.snapshot(0.05), ((), raw_x, raw_y))
                self.assertEqual(self.state.snapshot(0.1), ((), 0.0, 0.0))

    def test_orientation_in_sequence_does_not_rotate_buttons(self):
        self.state.execute({"op": "sequence", "steps": [
            {"x": 0.5, "duration": 0.1},
            {"x": 0.5, "buttons": ["A"], "orientation": "sideways-right", "duration": 0.1}]}, 0)
        self.assertEqual(self.state.snapshot(0.05), ((), 0.5, 0))
        self.assertEqual(self.state.snapshot(0.15), (("A",), 0, 0.5))

    def test_sequence_order_and_release_preemption(self):
        self.state.execute({"op": "sequence", "steps": [
            {"buttons": ["A"], "duration": 0.1}, {"duration": 0.2},
            {"x": -1, "y": 1, "duration": 0.5}]}, 0)
        self.assertEqual(self.state.snapshot(0.05)[0], ("A",))
        self.assertEqual(self.state.snapshot(0.2), ((), 0.0, 0.0))
        self.assertEqual(self.state.snapshot(0.4), ((), -1.0, 1.0))
        self.state.execute({"op": "release"}, 0.41)
        self.assertEqual(self.state.snapshot(0.42), ((), 0.0, 0.0))

    def test_invalid_input_does_not_replace_active_command(self):
        self.state.execute({"op": "set", "state": {"buttons": ["B"], "duration": 1}}, 0)
        for value in ({"buttons": ["ZL"]}, {"x": math.nan}, {"x": 2}, {"duration": 0},
                      {"duration": 11}, {"x": True}, {"unexpected": 1},
                      {"orientation": "unknown"}, {"orientation": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.state.execute({"op": "set", "state": value}, 0.1)
        self.assertEqual(self.state.snapshot(0.2)[0], ("B",))

    def test_not_ready_and_sequence_limits(self):
        self.state.ready = False
        with self.assertRaises(ValueError):
            self.state.execute({"op": "set", "state": {}})

        self.state.ready = True
        for steps in ([], [{}] * 257, [{"duration": 10}] * 31):
            with self.assertRaises(ValueError):
                self.state.execute({"op": "sequence", "steps": steps})
        self.state.execute({"op": "stop"})
        self.state.execute({"op": "release"})
        self.assertTrue(self.state.stopping)
        with self.assertRaises(ValueError):
            self.state.execute({"op": "set", "state": {}})

    def test_registration_blocks_user_input_and_reports_not_ready(self):
        self.state.registering = True
        result = self.state.execute({"op": "status"})
        self.assertFalse(result["ready"])
        self.assertTrue(result["registering"])
        with self.assertRaises(ValueError):
            self.state.execute({"op": "set", "state": {"buttons": ["A"]}})
        self.state.registering = False
        self.assertTrue(self.state.execute({"op": "status"})["ready"])


class ControlSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_socket_roundtrip_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control.sock"
            state = InputState()
            state.ready = state.connected = True
            server = ControlServer(path, state)
            await server.start()
            try:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                result = await send(path, {"op": "set", "state": {"buttons": ["HOME"]}})
                self.assertEqual(result["buttons"], ["HOME"])
                self.assertFalse((await send(path, {"op": "set", "state": {"buttons": ["ZL"]}}))["ok"])
                self.assertEqual((await send(path, {"op": "release"}))["buttons"], [])
                with self.assertRaises(ValueError):
                    await ControlServer(path, state).start()
            finally:
                await server.close()
            self.assertFalse(path.exists())

    async def test_refuses_regular_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control.sock"
            path.write_text("preserve this file")
            with self.assertRaises(ValueError):
                await ControlServer(path, InputState()).start()
            link = Path(directory) / "link.sock"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                await ControlServer(link, InputState()).start()
            self.assertEqual(path.read_text(), "preserve this file")
