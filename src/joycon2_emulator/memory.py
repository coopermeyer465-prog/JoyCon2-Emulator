"""Generated virtual controller metadata, not a Nintendo flash dump.

Field offsets follow ndeadly's memory_layout.md. Unknown regions are deliberately
unavailable rather than silently returning invented firmware/calibration bytes.
"""

import hashlib
import json
from pathlib import Path
import struct

from .protocol import address_bytes, PRODUCTS

CALIBRATION_BASES = (0x13080, 0x130C0, 0x13100, 0x13140)


class VirtualMemory:
    def __init__(self, address, side="right"):
        if side not in PRODUCTS:
            raise ValueError("Expected left or right Joy-Con side")
        metadata = bytearray(64)
        metadata[:2] = b"\x01\x00"
        serial = "J2E" + hashlib.sha256(address_bytes(address)).hexdigest()[:11].upper()
        metadata[2:18] = serial.encode("ascii").ljust(16, b"\x00")
        struct.pack_into("<HH", metadata, 18, 0x057E, PRODUCTS[side])
        metadata[22:25] = bytes.fromhex("010601")
        # Arbitrary virtual colors, not copied from a physical controller.
        metadata[25:37] = bytes.fromhex("20a090202020d0d0d0303030")
        # Erased user-calibration slots mean this virtual device has no custom
        # calibration; the console should use the imported factory values.
        tag = hashlib.sha256(b"joycon2-emulator-factory-tag" + address_bytes(address)).digest()[:16]
        self.regions = {0x13000: bytes(metadata), 0x13040: tag,
                        # Published factory-field example; meaning is unknown.
                        0x13060: bytes.fromhex("4c090000") + bytes(28),
                        0x1FC000: bytes([0xFF]) * 0x100}

    def load_calibration(self, path):
        data = json.loads(Path(path).read_text())
        if data.get("version") != 1 or not isinstance(data.get("regions"), dict):
            raise ValueError("Unsupported calibration format")
        regions = {int(base, 16): bytes.fromhex(value) for base, value in data["regions"].items()}
        if not regions or any(base not in CALIBRATION_BASES or len(value) != 64 for base, value in regions.items()):
            raise ValueError("Only the allowlisted 64-byte factory/calibration blocks may be imported")
        self.regions.update(regions)

    def read(self, address, length):
        if not 0 <= address < 0x200000 or not 1 <= length <= 0x4F:
            raise ValueError("Invalid Bluetooth memory read range")
        for base, data in self.regions.items():
            offset = address - base
            if 0 <= offset and offset + length <= len(data):
                return data[offset:offset + length]
        raise NotImplementedError(f"Virtual memory region 0x{address:06x}+{length}")

    def primary_center(self):
        try:
            packed = self.read(0x130A8, 3)
        except NotImplementedError:
            return 2048, 2048
        x = packed[0] | ((packed[1] & 15) << 8)
        y = (packed[1] >> 4) | (packed[2] << 4)
        if not 0 < x < 4095 or not 0 < y < 4095:
            raise ValueError("Invalid primary-stick factory center")
        return x, y

    def logical_stick(self, x, y):
        center = self.primary_center()
        try:
            packed = self.read(0x130AB, 6)
        except NotImplementedError:
            positive, negative = (2047, 2047), (2048, 2048)
        else:
            def axes(data):
                return data[0] | ((data[1] & 15) << 8), (data[1] >> 4) | (data[2] << 4)
            positive, negative = axes(packed[:3]), axes(packed[3:])
        result = []
        for value, midpoint, high, low in zip((x, y), center, positive, negative):
            if high <= 0 or low <= 0 or midpoint + high > 4095 or midpoint - low < 0:
                raise ValueError("Invalid factory stick range")
            result.append(round(midpoint + value * (high if value >= 0 else low)))
        return tuple(result)

    def handle_read(self, payload):
        if len(payload) != 8 or payload[1:4] != b"\x7e\x00\x00":
            raise ValueError("Invalid memory-read request")
        length = payload[0]
        address = int.from_bytes(payload[4:8], "little")
        data = self.read(address, length)
        return struct.pack("<B3xI", len(data), address) + data
