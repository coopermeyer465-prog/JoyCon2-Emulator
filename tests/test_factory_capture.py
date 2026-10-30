import unittest

from joycon2_emulator.factory_capture import read_request, read_response


class FactoryCaptureTests(unittest.TestCase):
    def test_allowlisted_read_only_request(self):
        self.assertEqual(read_request(0x13080), bytes.fromhex("0291010400080000407e000080300100"))
        for base in (0x13000, 0x1FA000, 0):
            with self.assertRaises(ValueError):
                read_request(base)

    def test_response_validation(self):
        packet = bytes.fromhex("02010104107800004000000080300100") + bytes(64)
        self.assertEqual(read_response(packet, 0x13080), bytes(64))
        for data, base in ((packet[:-1], 0x13080), (packet, 0x130C0), (bytes(80), 0x13080)):
            with self.assertRaises(ValueError):
                read_response(data, base)
