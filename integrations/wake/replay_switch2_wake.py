"""Replay a captured, paired Joy-Con 2 wake advert, then restore the adapter.

Run inside the Linux VM with nxbt-web and bluetooth services stopped.
Address configuration: Dark Mentor's RTL8761B config research.
Wake advertising approach: Bill-git1/Switch2-RPI-Wake (wake-v4.sh).
"""

import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import time

from capture_switch2_wake import command, open_hci
from realtek_wake_config import override_address


CONFIG = Path("/lib/firmware/rtl_bt/rtl8761bu_config.bin")


def read_address():
    # HCIGETDEVINFO: dev_id (u16), name (8 bytes), then bdaddr (6 bytes).
    hci = open_hci()
    try:
        info = bytearray(256)
        fcntl.ioctl(hci.fileno(), 0x800448D3, info, True)
        return ":".join(f"{byte:02X}" for byte in info[10:16][::-1])
    finally:
        hci.close()


def choose_wake(reports):
    for report in reversed(reports):
        data = bytes.fromhex(report["advertisement"])
        if (report["address_type"] == 0 and len(data) == 31
                and data[:7] == bytes.fromhex("0201061bff5305")
                and data[10:12] == bytes.fromhex("7e05")
                and data[12:14] in (b"\x66\x20", b"\x67\x20", b"\x69\x20")
                and data[16] == 0x81 and data[17:23] != bytes(6)):
            return report["address"], data
    raise ValueError("No public-address, paired Switch 2 wake advertisement in capture")


def reset_to(expected):
    subprocess.run(["usbreset", "2357:0604"], check=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            actual = read_address()
        except (OSError, RuntimeError, TimeoutError):
            actual = ""
        if actual == expected.upper():
            print(f"Adapter address verified: {actual}", flush=True)
            return
        time.sleep(0.25)
    raise RuntimeError(f"Adapter did not initialize at expected address {expected}")


def replay(reports):
    source, advert = choose_wake(reports)
    original_address = read_address()
    original_config = CONFIG.read_bytes()
    override = override_address(original_config, source)
    print(f"Temporary wake identity: {source}; original: {original_address}", flush=True)
    try:
        CONFIG.write_bytes(override)
        reset_to(source)
        # Restore the on-disk config before transmitting, even if later interrupted.
        CONFIG.write_bytes(original_config)
        subprocess.run(["hciconfig", "hci0", "up"], check=True)
        hci = open_hci()
        try:
            command(hci, 0x200A, b"\x00")
            # Match the real Joy-Con's ADV_IND PDU type, not ADV_NONCONN_IND.
            command(hci, 0x2006, bytes.fromhex("200040000000000000000000000700"))
            command(hci, 0x2008, bytes([len(advert)]) + advert)
            for burst in range(3):
                command(hci, 0x200A, b"\x01")
                print(f"Connectable wake burst {burst + 1}/3 enabled.", flush=True)
                time.sleep(1)
                command(hci, 0x200A, b"\x00")
                time.sleep(0.2)
        finally:
            try:
                command(hci, 0x200A, b"\x00")
            finally:
                hci.close()
    finally:
        CONFIG.write_bytes(original_config)
        reset_to(original_address)
    print("Wake transmission finished; original adapter identity restored.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    replay(json.loads(args.capture.read_text()))
