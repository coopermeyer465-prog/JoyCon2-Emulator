import unittest

from joycon2_emulator.protocol import Command, advertisement, decode_advertisement, left_report, pack_stick, right_report


class ProtocolTests(unittest.TestCase):
    def test_advertisement_layout(self):
        for side, pid in (("right", 0x2066), ("left", 0x2067)):
            data = advertisement(side)
            self.assertEqual(len(data), 31)
            self.assertEqual(decode_advertisement(data), {"product": pid, "wake": False,
                                                        "host": "00:00:00:00:00:00", "paired": False})

    def test_wake_requires_and_encodes_host(self):
        with self.assertRaises(ValueError):
            advertisement(wake=True)
        result = decode_advertisement(advertisement(host="02:11:22:33:44:55", wake=True))
        self.assertTrue(result["wake"])
        self.assertEqual(result["host"], "02:11:22:33:44:55")

    def test_stick_encoding(self):
        self.assertEqual(pack_stick(), bytes.fromhex("000880"))
        self.assertEqual(pack_stick(0, 4095), bytes.fromhex("00f0ff"))
        self.assertEqual(pack_stick(4095, 0), bytes.fromhex("ff0f00"))
        for value in (-1, 4096, 1.5):
            with self.assertRaises(ValueError):
                pack_stick(value, 0)

    def test_report_buttons_neutral_and_counter(self):
        data = right_report(256, ["A", "HOME"])
        self.assertEqual(len(data), 63)
        self.assertEqual(data[:8], bytes.fromhex("0024020107000880"))
        self.assertEqual(data[8:], bytes(55))
        self.assertEqual(right_report(255)[0], 255)

    def test_left_report_has_its_own_buttons(self):
        data = left_report(256, ["UP", "L", "MINUS", "CAPTURE"])
        self.assertEqual(len(data), 63)
        self.assertEqual(data[:8], bytes.fromhex("0024580107000880"))
        with self.assertRaises(KeyError):
            left_report(buttons=["A"])

    def test_command(self):
        data = bytes.fromhex("159101030001000000")
        command = Command.parse(data)
        self.assertEqual(command.subcommand, 3)
        self.assertEqual(command.payload, b"\x00")
        self.assertEqual(command.response(b"\x01"), bytes.fromhex("150101031078000001"))
        self.assertEqual(Command.parse(bytes(17) + data, True), command)

    def test_rejects_malformed_packets(self):
        for data in (b"", bytes(8), bytes.fromhex("159101030002000000")):
            with self.assertRaises(ValueError):
                Command.parse(data)
        with self.assertRaises(ValueError):
            decode_advertisement(bytes(31))


if __name__ == "__main__":
    unittest.main()
