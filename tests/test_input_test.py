import unittest

from joycon2_emulator.input_test import ButtonPulse


class ButtonPulseTests(unittest.TestCase):
    def test_join_is_bounded_and_releases(self):
        pulse = ButtonPulse("join")
        self.assertEqual(pulse.at(0), ())
        self.assertEqual(pulse.at(1.99), ())
        self.assertEqual(pulse.at(2), ("SL", "SR"))
        self.assertEqual(pulse.at(2.24), ("SL", "SR"))
        self.assertEqual(pulse.at(2.25), ())
        self.assertEqual(pulse.at(100), ())

    def test_explicit_button_allowlist(self):
        self.assertEqual(ButtonPulse("home").at(2), ("HOME",))
        with self.assertRaises(ValueError):
            ButtonPulse("anything")

    def test_home_is_a_short_tap_and_releases(self):
        pulse = ButtonPulse("home")
        self.assertEqual(pulse.duration_ms, 50)
        self.assertEqual(pulse.at(1.999), ())
        self.assertEqual(pulse.at(2.0), ("HOME",))
        self.assertEqual(pulse.at(2.049), ("HOME",))
        self.assertEqual(pulse.at(2.05), ())
        self.assertEqual(pulse.at(2.25), ())
