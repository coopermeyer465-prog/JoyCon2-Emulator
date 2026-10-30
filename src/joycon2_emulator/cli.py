import argparse
import asyncio
import json
import logging
from pathlib import Path
import platform
import subprocess

from .protocol import advertisement, decode_advertisement


def main():
    parser = argparse.ArgumentParser(description="Experimental Joy-Con 2 BLE emulator, not yet playable")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Read-only platform/adapter checks")
    adv = commands.add_parser("advertisement", help="Generate advertisement hex without transmitting")
    adv.add_argument("--side", choices=("left", "right"), default="right")
    adv.add_argument("--host")
    adv.add_argument("--wake", action="store_true")
    inspect = commands.add_parser("inspect-capture", help="Inspect local Nintendo capture without transmitting")
    inspect.add_argument("capture", type=Path)
    lab = commands.add_parser("serve", help="EXPERIMENTAL GATT peripheral; not a playable controller")
    lab.add_argument("--experimental", action="store_true", required=True)
    lab.add_argument("--address", required=True, help="Adapter's OWN public address, not a physical Joy-Con")
    lab.add_argument("--transport", default="hci-socket:0")
    lab.add_argument("--bond-file", type=Path, default=Path(".state/bond.json"))
    lab.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps({"platform": platform.system(), "playable": False,
                          "usb_5ms_connection_support": "unverified",
                          "wake_reliability": "one successful test; repeat failure reported"}))
        if platform.system() == "Linux":
            subprocess.run(["hciconfig", "-a"], check=True)
        else:
            print("The HCI-socket backend requires Linux (a USB-passthrough VM is supported for research).")
    elif args.command == "advertisement":
        print(advertisement(args.side, args.host, args.wake).hex())
    elif args.command == "inspect-capture":
        for report in json.loads(args.capture.read_text()):
            print(json.dumps({"source": report["address"], **decode_advertisement(bytes.fromhex(report["advertisement"]))}))
    elif args.command == "serve":
        if platform.system() != "Linux" or not 1 <= args.seconds <= 300:
            parser.error("Serve needs Linux and --seconds between 1 and 300")
        from .backend import serve
        logging.basicConfig(level=logging.INFO)
        asyncio.run(serve(args.address, args.transport, args.bond_file, args.seconds))


if __name__ == "__main__":
    main()
