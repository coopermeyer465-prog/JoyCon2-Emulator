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
            controller.handle(Command(2, 5, b""))
        with self.assertRaises(ValueError):
            controller.handle(Command(7, 1, b"\x00"))

    def test_dispatches_pairing(self):
        controller = Controller("02:00:00:00:00:01")
        response = controller.handle(Command(0x15, 1, b""))
        self.assertEqual(response, bytes.fromhex("010401010000000002"))

    def test_generated_factory_read_and_virtual_version(self):
        controller = Controller("02:00:00:00:00:01")
        response = controller.handle(Command(2, 4, bytes.fromhex("407e000000300100")))
        self.assertEqual(len(response), 72)
        self.assertEqual(response[8:10], b"\x01\x00")
        version = controller.handle(Command(0x10, 1, b""))
        self.assertEqual(version[:4], bytes([0, 1, 0, 1]))
        self.assertEqual(len(version), 12)
        self.assertEqual(controller.handle(Command(1, 0xC, b"")), bytes.fromhex("64126810"))
        with self.assertRaises(ValueError):
            controller.handle(Command(0x10, 1, b"\x00"))

    def test_documented_opaque_query_responses(self):
        controller = Controller("02:00:00:00:00:01")
        self.assertEqual(controller.handle(Command(0x16, 1, b"")), bytes(24))
        self.assertEqual(controller.handle(Command(0x11, 1, b"")), b"\x01\x00\x00\x00")
        self.assertEqual(len(controller.handle(Command(0x11, 3, b""))), 29)
        self.assertEqual(controller.handle(Command(0x13, 1, b"")), b"\x01\x00\x00\x00")
        self.assertEqual(controller.handle(Command(0x13, 2, b"")), b"\x01" + bytes(7))
        self.assertEqual(controller.handle(Command(0x13, 3, b"")), b"\x01" + bytes(7))
        with self.assertRaises(ValueError):
            controller.handle(Command(0x16, 1, b"\x00"))

    def test_virtual_vibration_sample(self):
        controller = Controller("02:00:00:00:00:01")
        self.assertEqual(controller.handle(Command(0xA, 2, b"\x03\x00\x00\x00")), b"")
        self.assertEqual(controller.vibration_sample, 3)
        self.assertEqual(controller.handle(Command(0xA, 8, bytes(20))), b"")
        self.assertEqual(controller.vibration_data, bytes(20))
        with self.assertRaises(ValueError):
            controller.handle(Command(0xA, 8, bytes(19)))
        for payload in (b"", b"\xff\x00\x00\x00"):
            with self.assertRaises(ValueError):
                controller.handle(Command(0xA, 2, payload))

    def test_virtual_led_pattern_forms(self):
        controller = Controller("02:00:00:00:00:01")
        self.assertEqual(controller.handle(Command(9, 7, b"\x01\x00\x00\x00")), b"")
        self.assertEqual(controller.player_led_pattern, 1)
        controller.handle(Command(9, 7, bytes.fromhex("0300000001000000")))
        self.assertEqual(controller.player_led_pattern, 3)
        self.assertEqual(controller.player_led_reserved, bytes.fromhex("00000001000000"))
        with self.assertRaises(ValueError):
            controller.handle(Command(9, 7, bytes(5)))
