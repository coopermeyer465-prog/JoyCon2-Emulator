import json
from pathlib import Path
import tempfile
import unittest

from joycon2_emulator.features import Features
from joycon2_emulator.control import InputState
from joycon2_emulator.protocol import right_report
from joycon2_emulator.sensor_replay import SensorReplay


class SensorReplayTests(unittest.TestCase):
    def load(self, frames):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps({"version": 1, "frames": frames}))
            return SensorReplay(path)

    def frame(self, report=None, elapsed=0):
        if report is None:
            report = bytearray([0xA5] * 63)
            report[15] = 40
        return {"kind": "right", "elapsed": elapsed, "data": bytes(report).hex()}

    def test_only_allowlisted_sensor_bytes_enter_generated_report(self):
        replay = self.load([self.frame()])
        neutral = right_report(19, x=2030, y=2090)
        result = replay.next_report(neutral, 0x17)
        self.assertEqual(result[9:14], bytes([0xA5]) * 5)
        self.assertEqual(result[15:56], bytes([40]) + bytes([0xA5]) * 40)
        for index in (*range(9), 14, *range(56, 63)):
            self.assertEqual(result[index], neutral[index])
        self.assertIsNone(replay.next_report(neutral, 0x17))

    def test_rejects_inactive_features_without_consuming(self):
        replay = self.load([self.frame()])
        for enabled in (0, 3, 0x13, 7):
            with self.assertRaises(ValueError):
                replay.next_report(right_report(), enabled)
            self.assertEqual(replay.index, 0)

    def test_captured_controls_are_not_used_even_in_startup_frames(self):
        startup = bytearray([255] * 63)
        startup[15] = 0
        replay = self.load([self.frame(startup), self.frame()])
        self.assertEqual(len(replay.samples), 1)
        result = replay.next_report(right_report(), 0x17)
        self.assertEqual(result[2:4], bytes(2))
        self.assertEqual(result[5:8], right_report()[5:8])

    def test_rejects_common_empty_truncated_and_unknown_motion(self):
        bad_length = self.frame()
        bad_length["data"] = "00"
        common = self.frame()
        common["kind"] = "common"
        unknown = bytearray(63)
        unknown[15] = 30
        no_motion = bytearray(63)
        for frames in ([], [bad_length], [common], [self.frame(unknown)], [self.frame(no_motion)],
                       [None], [self.frame()] * 2049):
            with self.subTest(count=len(frames)), self.assertRaises(ValueError):
                self.load(frames)

    def test_feature_imu_is_only_available_in_explicit_recorded_mode(self):
        self.assertEqual(Features(mouse=True).supported, 0x13)
        features = Features(mouse=True, sensor_replay=True)
        self.assertEqual(features.supported, 0x17)
        self.assertEqual(features.handle(1, bytes.fromhex("ff000000"))[6], 3)
        features.handle(2, bytes.fromhex("ff000000"))
        features.handle(4, bytes.fromhex("ff000000"))
        self.assertEqual(features.enabled, 0x17)
        with self.assertRaises(ValueError):
            features.handle(6, bytes.fromhex("04000000020201008a00"))

    def test_baseline_keeps_command_mouse_and_regenerates_only_timing(self):
        replay = self.load([self.frame()])
        neutral = right_report(23, mouse=(5, -6, 50))
        result = replay.baseline_report(neutral, 0x17, 4097, 30)
        self.assertEqual(result[:15], neutral[:15])
        self.assertEqual(result[15], 40)
        self.assertEqual(int.from_bytes(result[16:19], "little"), 1 | (30 << 12))
        self.assertEqual(result[19:56], bytes([0xA5]) * 37)
        self.assertEqual(result[56:], neutral[56:])
        self.assertEqual(replay.index, 0)
        for timestamp, interval in ((-1, 1), (True, 1), (0, 0), (0, 4096), (0, 1.5)):
            with self.assertRaises(ValueError):
                replay.baseline_report(neutral, 0x17, timestamp, interval)

    def test_moving_motion_can_be_isolated_from_recorded_mouse(self):
        replay = self.load([self.frame()])
        neutral = right_report(7, mouse=(100, -100, 50))
        result = replay.next_report(neutral, 0x17, command_mouse=True)
        self.assertEqual(result[:15], neutral[:15])
        self.assertEqual(result[15:56], bytes([40]) + bytes([0xA5]) * 40)
        self.assertIsNone(replay.next_report(neutral, 0x17, command_mouse=True))

    def test_command_mouse_can_loop_at_the_recorded_cadence(self):
        first = bytearray([0xA5] * 63)
        first[15] = 40
        second = bytearray([0x5A] * 63)
        second[15] = 40
        replay = self.load([self.frame(first, 0), self.frame(second, 0.02)])
        neutral = right_report(mouse=(1, 2, 50))
        self.assertEqual(replay.next_report(neutral, 0x17, command_mouse=True, elapsed=0, loop=True)[19], 0xA5)
        self.assertEqual(replay.next_report(neutral, 0x17, command_mouse=True, elapsed=0.02, loop=True)[19], 0x5A)
        self.assertEqual(replay.next_report(neutral, 0x17, command_mouse=True, elapsed=0.019, loop=True)[19], 0xA5)
        self.assertEqual(replay.next_report(neutral, 0x17, command_mouse=True, elapsed=0.04, loop=True)[19], 0xA5)
        with self.assertRaises(ValueError):
            replay.next_report(neutral, 0x17, command_mouse=True, loop=True)

    def test_recorded_diagnostic_rejects_button_and_stick_commands(self):
        state = InputState()
        state.ready = state.mouse_supported = state.mouse_enabled = state.mouse_only = True
        for request in ({"op": "set", "state": {"buttons": ["HOME"]}},
                        {"op": "sequence", "steps": [{"x": 1}]}):
            with self.assertRaises(ValueError):
                state.execute(request, 0)
        self.assertTrue(state.execute({"op": "mouse", "dx": 1}, 0)["ok"])

    def test_only_explicit_generated_a_can_accompany_command_mouse(self):
        report = right_report(buttons=("A", "HOME", "R", "C"))
        full_replay = self.load([self.frame()]).next_report(report, 0x17)
        command_replay = self.load([self.frame()]).next_report(report, 0x17, command_mouse=True)
        self.assertEqual(full_replay[2:4], bytes(2))
        self.assertEqual(command_replay[2:4], bytes((2, 0)))
        state = InputState()
        state.ready = state.mouse_supported = state.mouse_enabled = state.mouse_only = True
        state.execute({"op": "mouse_click"}, 0)
        for now, expected in ((0.04, 2), (0.08, 0)):
            buttons, _, _ = state.snapshot(now)
            generated = right_report(buttons=buttons)
            replayed = self.load([self.frame()]).next_report(generated, 0x17, command_mouse=True)
            self.assertEqual(replayed[2], expected)
