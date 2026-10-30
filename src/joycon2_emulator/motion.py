"""Offline codec for the documented COMMON (0x05) report's IMU block.

This is NOT the packed 0x08 motion codec used by our console connection.
It is intentionally not wired to the peripheral or advertised as a capability.
Layout and scales: ndeadly/switch2_controller_research, hid_reports.md.
"""

import math
import struct


def _scaled(value, limit, scale, name):
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or not -limit <= value <= limit):
        raise ValueError(f"{name} must be finite and within +/-{limit}")
    return round(value * scale)


def common_motion(timestamp_us, accel_g=(0, 0, 1), gyro_dps=(0, 0, 0), temperature_c=25):
    """Encode 18 bytes: u32 microseconds, i16 temperature, 3 accel, 3 gyro.

    Body axes are passed through, not rotated to a horizontal grip. No factory
    biases or synthetic quaternion data are supplied by this offline codec.
    """
    if type(timestamp_us) is not int or not 0 <= timestamp_us <= 0xFFFFFFFF:
        raise ValueError("timestamp_us must be an unsigned 32-bit integer")
    if (not isinstance(accel_g, (list, tuple)) or len(accel_g) != 3
            or not isinstance(gyro_dps, (list, tuple)) or len(gyro_dps) != 3):
        raise ValueError("Expected three acceleration and three angular-velocity axes")
    if (isinstance(temperature_c, bool) or not isinstance(temperature_c, (float, int))
            or not math.isfinite(temperature_c)):
        raise ValueError("temperature_c must be finite")
    temperature = _scaled(temperature_c - 25, 32767 / 126.9, 126.9, "temperature offset")
    accel = [_scaled(value, 8, 32767 / 8, "accel_g") for value in accel_g]
    gyro = [_scaled(value, 2000, 32767 / 2000, "gyro_dps") for value in gyro_dps]
    return struct.pack("<I7h", timestamp_us, temperature, *accel, *gyro)
