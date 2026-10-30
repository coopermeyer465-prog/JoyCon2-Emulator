import unittest

from joycon2_emulator.features import Features


class FeaturesTests(unittest.TestCase):
    def test_mask_enable_disable_and_clear(self):
        features = Features()
        self.assertEqual(features.handle(2, bytes.fromhex("2f000000")), bytes(4))
        self.assertEqual(features.mask, 3)
        features.handle(4, bytes.fromhex("2f000000"))
        self.assertEqual(features.enabled, 3)
        features.handle(5, bytes.fromhex("01000000"))
        self.assertEqual(features.enabled, 2)
        features.handle(3, bytes(4))
        self.assertEqual(features.enabled, 0)
        self.assertIsNone(features.mask)

    def test_reports_only_implemented_capabilities(self):
        info = Features().handle(1, bytes.fromhex("ff000000"))
        self.assertEqual(info, bytes.fromhex("000000000707000000000000"))

    def test_order_and_malformed_input(self):
        features = Features()
        with self.assertRaises(ValueError):
            features.handle(4, bytes(4))
        with self.assertRaises(ValueError):
            features.handle(2, bytes(3))
        with self.assertRaises(NotImplementedError):
            features.handle(6, bytes(4))
