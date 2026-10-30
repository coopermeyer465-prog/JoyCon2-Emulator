import unittest

from joycon2_emulator.controller import Controller
from joycon2_emulator.protocol import Command


class ControllerTests(unittest.TestCase):
    def test_initialization_known_response(self):
        request = Command.parse(bytes.fromhex("0791010100000000"))
        response = Controller("02:00:00:00:00:01").handle(request)
        self.assertEqual(request.response(response), bytes.fromhex("070101011078000000"))

    def test_rejects_unknown_commands_and_bad_payload(self):
        controller = Controller("02:00:00:00:00:01")
        with self.assertRaises(NotImplementedError):
            controller.handle(Command(2, 4, b""))
        with self.assertRaises(ValueError):
            controller.handle(Command(7, 1, b"\x00"))

    def test_dispatches_pairing(self):
        controller = Controller("02:00:00:00:00:01")
        response = controller.handle(Command(0x15, 1, b""))
        self.assertEqual(response, bytes.fromhex("010401010000000002"))
