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
