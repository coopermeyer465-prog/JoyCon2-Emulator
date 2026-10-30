import struct
from pathlib import Path
import tempfile
import unittest

from joycon2_emulator.control import ControlServer, InputState, send
from joycon2_emulator.features import Features
from joycon2_emulator.protocol import right_report


class MouseTests(unittest.TestCase):
    def test_explicit_native_click_is_only_a_bounded_r_press(self):
        state = self.state()
        with self.assertRaises(ValueError):
            state.execute({"op": "mouse_click"}, 0)
        state.mouse_only = True
        state.execute({"op": "mouse_click"}, 0)
        self.assertEqual(state.snapshot(0.04), (("R",), 0, 0))
        with self.assertRaises(ValueError):
            state.execute({"op": "mouse_click"}, 0.04)
        with self.assertRaises(ValueError):
            state.execute({"op": "mouse_click", "button": "HOME"}, 0.04)
        self.assertEqual(state.snapshot(0.08), ((), 0, 0))
        state.execute({"op": "mouse_click"}, 0.1)
        state.execute({"op": "release"}, 0.11)
        self.assertEqual(state.snapshot(0.12), ((), 0, 0))
        state.execute({"op": "mouse_click"}, 0.13)
        state.clear_mouse()
        self.assertEqual(state.snapshot(0.14), ((), 0, 0))
        state.ready = False
        with self.assertRaises(ValueError):
            state.execute({"op": "mouse_click"}, 0.2)

    def state(self):
        state = InputState()
        state.ready = state.connected = True
        state.mouse_supported = state.mouse_enabled = True
        return state

    def test_packet_offsets_signed_bounds_and_legacy_bytes(self):
        original = right_report(17, ("R",), 1234, 2345)
        report = right_report(17, ("R",), 1234, 2345, (-32768, 32767, 255))
        self.assertEqual(len(report), 63)
        self.assertEqual(report[:9], original[:9])
        self.assertEqual(report[9:14], struct.pack("<hhB", -32768, 32767, 255))
        self.assertEqual(report[14:], original[14:])
        self.assertEqual(original[9:14], bytes(5))
        for mouse in ((32768, 0, 0), (0, -32769, 0), (0, 0, 256), (True, 0, 0), (0.5, 0, 0)):
            with self.subTest(mouse=mouse), self.assertRaises(ValueError):
                right_report(mouse=mouse)

    def test_opt_in_feature_negotiation_never_advertises_imu(self):
        features = Features(mouse=True)
        info = features.handle(1, b"\xff\x00\x00\x00")
        self.assertEqual(info, bytes.fromhex("000000000707000003000000"))
        features.handle(2, b"\xff\x00\x00\x00")
        features.handle(4, b"\xff\x00\x00\x00")
        self.assertEqual(features.enabled, 0x13)
        features.handle(5, b"\x10\x00\x00\x00")
        self.assertEqual(features.enabled, 3)
        self.assertEqual(Features().supported, 3)

    def test_one_shot_does_not_consume_on_status_or_cancel_buttons(self):
        state = self.state()
        state.execute({"op": "set", "state": {"buttons": ["R"], "duration": 1}}, 0)
        state.execute({"op": "mouse", "dx": 10, "dy": -7}, 0)
        self.assertTrue(state.execute({"op": "status"}, 0.1)["mouse_pending"])
        self.assertTrue(state.execute({"op": "status"}, 0.1)["mouse_pending"])
        self.assertEqual(state.take_mouse(0.1), (10, -7, 0))
        self.assertEqual(state.take_mouse(0.11), (0, 0, 0))
        self.assertEqual(state.take_mouse(0.25), (0, 0, 255))
        self.assertEqual(state.snapshot(0.11)[0], ("R",))

    def test_expiry_release_loss_of_readiness_and_feature_disable(self):
        for action in ("expiry", "release", "disconnected", "registering", "disable", "stop"):
            state = self.state()
            state.execute({"op": "mouse", "dx": 1}, 0)
            if action in ("release", "stop"):
                state.execute({"op": action}, 0.1)
            elif action == "disconnected":
                state.ready = False
            elif action == "registering":
                state.registering = True
            elif action == "disable":
                state.mouse_enabled = False
            with self.subTest(action=action):
                self.assertEqual(state.take_mouse(0.25 if action == "expiry" else 0.1),
                                 None if action == "disable" else (0, 0, 255))
                self.assertIsNone(state.pending_mouse)

    def test_invalid_commands_do_not_overwrite_pending_movement(self):
        state = self.state()
        state.execute({"op": "mouse", "dx": 2}, 0)
        for request in ({"op": "mouse", "dx": 3}, {"op": "mouse", "dx": True},
                        {"op": "mouse", "dx": 32768}, {"op": "mouse", "dy": 0.5},
                        {"op": "mouse", "lifted": 1}, {"op": "mouse", "lifted": True, "dx": 1}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                state.execute(request, 0.1)
        self.assertEqual(state.take_mouse(0.11), (2, 0, 0))
        state.execute({"op": "mouse", "lifted": True}, 0.12)
        self.assertEqual(state.take_mouse(0.13), (0, 0, 255))
        self.assertEqual(state.take_mouse(0.14), (0, 0, 255))

    def test_contact_refreshes_only_from_new_movements(self):
        state = self.state()
        state.execute({"op": "mouse", "dx": 1}, 0)
        self.assertEqual(state.take_mouse(0.01), (1, 0, 0))
        state.execute({"op": "mouse", "dy": 2}, 0.1)
        self.assertEqual(state.take_mouse(0.11), (0, 2, 0))
        for now in (0.12, 0.25, 0.34):
            self.assertEqual(state.take_mouse(now), (0, 0, 0))
        self.assertEqual(state.take_mouse(0.35), (0, 0, 255))

    def test_raw_surface_is_preserved_during_contact_lease(self):
        for surface in (0, 50, 254):
            state = self.state()
            state.execute({"op": "mouse", "dx": 7, "surface": surface}, 0)
            self.assertEqual(state.take_mouse(0.01), (7, 0, surface))
            self.assertEqual(state.take_mouse(0.1), (0, 0, surface))
            self.assertEqual(state.take_mouse(0.25), (0, 0, 255))
        for surface in (-1, 255, True, 1.5, None):
            with self.subTest(surface=surface), self.assertRaises(ValueError):
                self.state().execute({"op": "mouse", "surface": surface}, 0)
        with self.assertRaises(ValueError):
            self.state().execute({"op": "mouse", "surface": 50, "lifted": True}, 0)

    def test_active_contact_clears_on_release_or_readiness_loss(self):
        for action in ("release", "stop", "registering", "ready", "mouse_enabled", "clear"):
            state = self.state()
            state.execute({"op": "mouse", "dx": 1}, 0)
            state.take_mouse(0.01)
            if action in ("release", "stop"):
                state.execute({"op": action}, 0.02)
            elif action == "clear":
                state.clear_mouse()
            else:
                setattr(state, action, action == "registering")
            with self.subTest(action=action):
                self.assertEqual(state.take_mouse(0.03),
                                 None if action == "mouse_enabled" else (0, 0, 255))
                state.mouse_enabled = state.ready = True
                state.registering = state.stopping = False
                self.assertEqual(state.take_mouse(0.04), (0, 0, 255))

    def test_rejects_without_capability_console_enable_or_ready(self):
        for attribute in ("mouse_supported", "mouse_enabled", "ready"):
            state = self.state()
            setattr(state, attribute, False)
            with self.subTest(attribute=attribute), self.assertRaises(ValueError):
                state.execute({"op": "mouse", "dx": 1}, 0)
        self.assertIsNone(InputState().take_mouse(0))


class MouseSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_socket_ack_is_queue_receipt_and_disabled_mouse_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = InputState()
            state.ready = True
            server = ControlServer(Path(directory) / "input.sock", state)
            await server.start()
            try:
                self.assertFalse((await send(server.path, {"op": "mouse", "dx": 3}))["ok"])
                state.mouse_supported = state.mouse_enabled = True
                result = await send(server.path, {"op": "mouse", "dx": -3})
                self.assertTrue(result["ok"])
                self.assertTrue(result["mouse_pending"])
                expiry = state.pending_mouse[1]
                self.assertEqual(state.take_mouse(expiry - 0.1), (-3, 0, 0))
                self.assertEqual(state.take_mouse(expiry - 0.05), (0, 0, 0))
                self.assertEqual(state.take_mouse(expiry), (0, 0, 255))
            finally:
                await server.close()
