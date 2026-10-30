"""Bounded diagnostic playback of privately owned compact sensor telemetry.

Never carries captured buttons, stick positions, power, identifiers or commands.
This is recorded sensor playback, not a generated or calibrated gyro emulator.
"""

import json
import math
from pathlib import Path
from bisect import bisect_right


class SensorReplay:
    def __init__(self, path):
        path = Path(path)
        with path.open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Sensor capture exceeds 2 MiB")
        capture = json.loads(raw)
        if not isinstance(capture, dict) or capture.get("version") != 1:
            raise ValueError("Expected a version 1 native sensor capture")
        frames = capture.get("frames")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 2048:
            raise ValueError("Expected 1..2048 compact frames")
        self.samples = []
        previous_elapsed = -1.0
        for frame in frames:
            if (not isinstance(frame, dict) or frame.get("kind") != "right"
                    or not isinstance(frame.get("data"), str) or len(frame["data"]) != 126
                    or isinstance(frame.get("elapsed"), bool)
                    or not isinstance(frame.get("elapsed"), (int, float))
                    or not math.isfinite(frame["elapsed"]) or frame["elapsed"] < previous_elapsed):
                raise ValueError("Only compact right-half captures are accepted")
            elapsed = float(frame["elapsed"])
            previous_elapsed = elapsed
            report = bytes.fromhex(frame["data"])
            if len(report) != 63 or report[15] not in (0, 40):
                raise ValueError("Unsupported compact sensor report")
            if report[15] == 40:
                self.samples.append((elapsed, report[9:14], report[15:56]))
        if not self.samples:
            raise ValueError("Capture has no 40-byte motion samples")
        self.index = 0
        origin = self.samples[0][0]
        self.times = [sample[0] - origin for sample in self.samples]
        tail = self.times[-1] - self.times[-2] if len(self.times) > 1 else 0.01
        self.duration = max(0.01, self.times[-1] + max(0.001, tail))

    def _sample(self, elapsed, loop):
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Expected a nonnegative replay elapsed time")
        if loop:
            elapsed %= self.duration
        elif elapsed > self.duration:
            return None
        return self.samples[max(0, bisect_right(self.times, elapsed) - 1)]

    def next_report(self, neutral, enabled, command_mouse=False, elapsed=None, loop=False):
        """Build a report from private sensors without carrying captured controls.

        Command-mouse mode may use a time-paced, looping motion bed. It only
        repeats opaque motion bytes; optical fields and A clicks remain local
        commands and all captured buttons/sticks are discarded.
        """
        if len(neutral) != 63:
            raise ValueError("Expected a compact neutral report")
        if enabled & 0x14 != 0x14:
            raise ValueError("Console must enable both mouse and recorded motion")
        if loop:
            if not command_mouse or elapsed is None:
                raise ValueError("Looping is limited to time-paced command mouse playback")
            _, mouse, motion = self._sample(elapsed, True)
        else:
            if elapsed is None:
                if self.index >= len(self.samples):
                    return None
                _, mouse, motion = self.samples[self.index]
                self.index += 1
            else:
                sample = self._sample(elapsed, False)
                if sample is None:
                    return None
                _, mouse, motion = sample
        report = bytearray(neutral)
        report[2:4] = bytes((neutral[2] & 2, 0)) if command_mouse else bytes(2)
        if not command_mouse:
            report[9:14] = mouse
        report[15:56] = motion
        return bytes(report)

    def baseline_report(self, neutral, enabled, timestamp_ms, interval_ms):
        """Private stationary-motion experiment; optical fields stay command-driven.

        Only the observed low 24 timing bits are regenerated. The remaining
        recorded block is opaque, not a synthesized or calibrated orientation.
        """
        if len(neutral) != 63 or enabled & 0x14 != 0x14:
            raise ValueError("Expected enabled mouse/motion and a compact report")
        if (type(timestamp_ms) is not int or timestamp_ms < 0 or type(interval_ms) is not int
                or not 1 <= interval_ms <= 4095):
            raise ValueError("Expected nonnegative milliseconds and a 1..4095 ms interval")
        report = bytearray(neutral)
        report[2:4] = bytes((neutral[2] & 2, 0))
        report[15:56] = self.samples[len(self.samples) // 2][2]
        timing = (timestamp_ms & 4095) | (interval_ms << 12)
        report[16:19] = timing.to_bytes(3, "little")
        return bytes(report)
