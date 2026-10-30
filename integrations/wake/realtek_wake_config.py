"""Build a Realtek RTL8761B USB address override; never install it automatically.

Configuration format and RTL8761B address offset documented by Dark Mentor:
https://github.com/darkmentorllc/DarkFirmware_real_i/tree/master/06_RTL_Config_KaitaiStruct
"""

import argparse
from pathlib import Path
import re
import struct


def override_address(config, address):
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", address):
        raise ValueError("Expected a six-byte Bluetooth address")
    mac = bytes.fromhex(address.replace(":", ""))
    if mac[0] & 1 or mac == bytes(6):
        raise ValueError("Expected a nonzero unicast address")
    if len(config) < 6:
        raise ValueError("Truncated Realtek header")
    magic, length = struct.unpack_from("<IH", config)
    if magic != 0x8723AB55 or length != len(config) - 6:
        raise ValueError("Invalid Realtek configuration header")
    records = bytearray()
    pos = 6
    while pos < len(config):
        if pos + 3 > len(config):
            raise ValueError("Truncated record header")
        offset, size = struct.unpack_from("<HB", config, pos)
        end = pos + 3 + size
        if end > len(config):
            raise ValueError("Truncated record value")
        if offset != 0x30:
            records.extend(config[pos:end])
        pos = end
    records.extend(struct.pack("<HB", 0x30, 6) + mac[::-1])
    return struct.pack("<IH", magic, len(records)) + records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("address")
    args = parser.parse_args()
    result = override_address(args.source.read_bytes(), args.address)
    # Exclusive creation prevents accidentally overwriting an installed config.
    with args.output.open("xb") as output:
        output.write(result)
