import math
import struct
import unittest

from joycon2_emulator.motion import common_motion


class CommonMotionTests(unittest.TestCase):
    def test_stationary_one_g_and_timestamp(self):
        self.assertEqual(struct.unpack("<I7h", common_motion(0x12345678)),
                         (0x12345678, 0, 0, 0, 4096, 0, 0, 0))

    def test_signed_axes_scales_and_temperature(self):
        self.assertEqual(struct.unpack("<I7h", common_motion(
            0xFFFFFFFF, (8, -8, 0), (2000, -2000, 0), 35)),
            (0xFFFFFFFF, 1269, 32767, -32767, 0, 32767, -32767, 0))
        self.assertEqual(len(common_motion(0)), 18)

    def test_rejects_out_of_range_nonfinite_and_bad_shapes(self):
        for kwargs in ({"timestamp_us": -1}, {"timestamp_us": True}, {"timestamp_us": 2**32},
                       {"accel_g": [0, 0]}, {"accel_g": [0, 0, 8.1]},
                       {"gyro_dps": [0, -2001, 0]}, {"gyro_dps": [math.nan, 0, 0]},
                       {"gyro_dps": [True, 0, 0]}, {"temperature_c": math.inf},
                       {"temperature_c": 1000}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                common_motion(**{"timestamp_us": 0, **kwargs})
