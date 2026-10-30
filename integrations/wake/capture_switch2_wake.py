"""Capture Nintendo BLE advertisements using a Linux HCI adapter (root required)."""

import argparse
import json
import os
from pathlib import Path
import socket
import struct
import time


def nintendo_reports(packet):
    if len(packet) < 5 or packet[:2] != b"\x04\x3e" or packet[3] != 2:
        return []
    reports = []
    pos = 5
    for _ in range(packet[4]):
        if pos + 9 > len(packet):
            break
        event, address_type = packet[pos:pos + 2]
        address = ":".join(f"{b:02X}" for b in packet[pos + 2:pos + 8][::-1])
        length = packet[pos + 8]
        end = pos + 9 + length
        if end >= len(packet):
            break
        data = packet[pos + 9:end]
        field = 0
        while field < len(data):
            size = data[field]
            if not size or field + size + 1 > len(data):
                break
            if data[field + 1:field + 4] == b"\xff\x53\x05":
                reports.append({"address": address, "address_type": address_type,
                                "event": event, "advertisement": data.hex(),
                                "rssi": struct.unpack("b", packet[end:end + 1])[0]})
                break
            field += size + 1
        pos = end + 1
    return reports


def command(hci, opcode, payload):
    hci.send(b"\x01" + struct.pack("<HB", opcode, len(payload)) + payload)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            packet = hci.recv(260)
        except socket.timeout:
            continue
        if len(packet) >= 7 and packet[1] == 0x0E and int.from_bytes(packet[4:6], "little") == opcode:
            if packet[6]:
                raise RuntimeError(f"HCI {opcode:04x} failed: {packet[6]:02x}")
            return packet[7:]
    raise TimeoutError(f"No HCI response for {opcode:04x}")


def open_hci():
    hci = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
    hci.bind((0,))
    hci.settimeout(1)
    hci.setsockopt(0, 2, struct.pack("<IIIH2x", 1 << 4, (1 << 14) | (1 << 15), 1 << 30, 0))
    return hci


def capture(seconds, output):
    hci = open_hci()
    reports = {}
    try:
        command(hci, 0x200C, b"\x00\x00")
        command(hci, 0x200B, bytes.fromhex("01040004000000"))
        command(hci, 0x200C, b"\x01\x00")
        print("Scanner running: put the Switch 2 to sleep, then press HOME on its paired right Joy-Con 2.", flush=True)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                packet = hci.recv(260)
            except socket.timeout:
                continue
            for report in nintendo_reports(packet):
                key = (report["address"], report["advertisement"])
                if key not in reports:
                    reports[key] = report
                    print(json.dumps(report), flush=True)
    finally:
        try:
            command(hci, 0x200C, b"\x00\x00")
        finally:
            hci.close()
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(list(reports.values()), stream, indent=2)
    print(f"Saved {len(reports)} Nintendo advertisements to {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 180 or args.output.exists():
        parser.error("Use a new output file and duration from 1 to 180 seconds")
    capture(args.seconds, args.output)
