import struct
import json
from pathlib import Path
import tempfile
import unittest

from joycon2_emulator.memory import VirtualMemory
from joycon2_emulator.protocol import pack_stick


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.memory = VirtualMemory("02:00:00:00:00:01")

    def test_metadata_identity(self):
        data = self.memory.read(0x13000, 64)
        self.assertEqual(len(data), 64)
        self.assertTrue(data[2:18].startswith(b"J2E"))
        self.assertEqual(struct.unpack_from("<HH", data, 18), (0x057E, 0x2066))
        self.assertEqual(VirtualMemory("02:00:00:00:00:01").read(0x13000, 64), data)
        self.assertNotEqual(VirtualMemory("02:00:00:00:00:02").read(0x13002, 16), data[2:18])

    def test_wire_response_and_subrange(self):
        request = bytes.fromhex("407e000000300100")
        response = self.memory.handle_read(request)
        self.assertEqual(response[:8], bytes.fromhex("4000000000300100"))
        self.assertEqual(response[8:], self.memory.read(0x13000, 64))
        self.assertEqual(self.memory.read(0x13012, 4), bytes.fromhex("7e056620"))

    def test_rejects_unknown_private_and_out_of_range_regions(self):
        for address, length in ((0x13050, 16), (0x1FA000, 64), (0x12FFF, 2), (0x1303F, 2)):
            with self.subTest(address=address), self.assertRaises(NotImplementedError):
                self.memory.read(address, length)
        for address, length in ((0x13000, 0), (0x13000, 80), (-1, 1), (0x200000, 1)):
            with self.subTest(address=address, length=length), self.assertRaises(ValueError):
                self.memory.read(address, length)

    def test_validates_memory_request(self):
        for payload in (b"", bytes(8), bytes.fromhex("407e00000030010000")):
            with self.assertRaises(ValueError):
                self.memory.handle_read(payload)

    def test_private_calibration_import_is_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "factory.json"
            path.write_text(json.dumps({"version": 1, "regions": {"013080": "00" * 64}}))
            self.memory.load_calibration(path)
            self.assertEqual(self.memory.read(0x13080, 64), bytes(64))
            for base, data in (("01fa000", "00" * 64), ("013000", "00" * 64), ("013080", "00")):
                path.write_text(json.dumps({"version": 1, "regions": {base: data}}))
                with self.assertRaises(ValueError):
                    self.memory.load_calibration(path)

    def test_no_virtual_user_calibration(self):
        self.assertEqual(self.memory.read(0x1FC040, 64), bytes([0xFF]) * 64)
        self.assertEqual(self.memory.read(0x1FC060, 64), bytes([0xFF]) * 64)
        with self.assertRaises(NotImplementedError):
            self.memory.read(0x1FA000, 64)

    def test_opaque_factory_tag_is_generated_and_stable(self):
        tag = self.memory.read(0x13040, 16)
        self.assertEqual(len(tag), 16)
        self.assertEqual(tag, VirtualMemory("02:00:00:00:00:01").read(0x13040, 16))
        self.assertNotEqual(tag, VirtualMemory("02:00:00:00:00:02").read(0x13040, 16))
        self.assertEqual(self.memory.read(0x13060, 32), bytes.fromhex("4c090000") + bytes(28))

    def test_neutral_uses_imported_center(self):
        self.assertEqual(self.memory.primary_center(), (2048, 2048))
        self.memory.regions[0x13080] = bytes(40) + pack_stick(2100, 1950) + bytes(21)
        self.assertEqual(self.memory.primary_center(), (2100, 1950))
        self.memory.regions[0x13080] = bytes(64)
        with self.assertRaises(ValueError):
            self.memory.primary_center()
