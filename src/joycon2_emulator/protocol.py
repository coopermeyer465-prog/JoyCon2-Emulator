"""Wire-format facts from ndeadly/switch2_controller_research; see CREDITS.md."""

from dataclasses import dataclass
import re
import struct


PRODUCTS = {"right": 0x2066, "left": 0x2067}


def address_bytes(address):
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", address):
        raise ValueError("Expected a six-byte colon-separated Bluetooth address")
    return bytes.fromhex(address.replace(":", ""))[::-1]


def advertisement(side="right", host=None, wake=False):
    if wake and host is None:
        raise ValueError("Wake requires a paired host address")
    data = bytearray.fromhex("0201061bff53050100037e0500000001000000000000000f00000000000000")
    struct.pack_into("<H", data, 12, PRODUCTS[side])
    data[16] = 0x81 if wake else 0
    data[17:23] = address_bytes(host) if host else bytes(6)
    return bytes(data)


def decode_advertisement(data):
    if len(data) != 31 or data[:7] != bytes.fromhex("0201061bff5305"):
        raise ValueError("Not a 31-byte Nintendo advertisement")
    product = int.from_bytes(data[12:14], "little")
    host = ":".join(f"{byte:02X}" for byte in data[17:23][::-1])
    return {"product": product, "wake": data[16] == 0x81,
            "host": host, "paired": data[17:23] != bytes(6)}


@dataclass(frozen=True)
class Command:
    command: int
    subcommand: int
    payload: bytes

    @classmethod
    def parse(cls, data, combined=False):
        if combined:
            data = data[17:]
        if len(data) < 8:
            raise ValueError("Truncated command header")
        if data[1:3] != b"\x91\x01" or data[6:8] != b"\x00\x00":
            raise ValueError("Expected a Bluetooth host command")
        if len(data) != 8 + data[5]:
            raise ValueError("Command payload length mismatch")
        return cls(data[0], data[3], data[8:])

    def response(self, payload):
        return bytes([self.command, 1, 1, self.subcommand, 0x10, 0x78, 0, 0]) + payload


def pack_stick(x=2048, y=2048):
    if not all(type(value) is int and 0 <= value <= 4095 for value in (x, y)):
        raise ValueError("Stick axes must be integers from 0 to 4095")
    return bytes([x & 255, (x >> 8) | ((y & 15) << 4), y >> 4])


RIGHT_BUTTONS = {"B": 0, "A": 1, "Y": 2, "X": 3, "R": 4, "ZR": 5,
                 "PLUS": 6, "STICK": 7, "HOME": 8, "C": 12, "SR": 14, "SL": 15}


def right_report(counter=0, buttons=(), x=2048, y=2048, mouse=None):
    """Encode report 0x08 without its USB report ID; IMU remains disabled.

    Optional mouse is (signed delta X, signed delta Y, raw surface byte).
    The surface byte's meaning is not fully documented; 0/255 contact/lift
    follows XD2Joy's experimental convention, not a calibrated distance.
    """
    bits = 0
    for name in buttons:
        bits |= 1 << RIGHT_BUTTONS[name]
    report = bytearray(63)
    report[0] = counter & 255
    report[1] = 9 << 2
    struct.pack_into("<H", report, 2, bits)
    report[4] = 7
    report[5:8] = pack_stick(x, y)
    if mouse is not None:
        dx, dy, surface = mouse
        for value, low, high in ((dx, -32768, 32767), (dy, -32768, 32767), (surface, 0, 255)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Invalid native mouse field")
        struct.pack_into("<hhB", report, 9, dx, dy, surface)
    return bytes(report)
