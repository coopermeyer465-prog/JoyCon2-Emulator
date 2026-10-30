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
    lab.add_argument("--control-socket", type=Path, help="Owner-only local command socket; permits --seconds 0")
    lab.add_argument("--auto-join", action="store_true", help="Send SL+SR once after each initialized connection")
    lab.add_argument("--calibration", type=Path, help="Private allowlisted factory-data capture")
    lab.add_argument("--test-button", choices=("join", "home", "a", "b"),
                     help="Send one pulse after subscribed input starts (HOME 50 ms, others 250 ms); join means SL+SR")
    capture = commands.add_parser("capture-calibration", help="Read four factory blocks; no pairing/flash writes")
    capture.add_argument("--peer", required=True)
    capture.add_argument("--output", type=Path, default=Path(".state/factory-calibration.json"))
    capture.add_argument("--transport", default="hci-socket:0")
    control = commands.add_parser("control", help="Send one local controller command")
    control.add_argument("--socket", type=Path, default=Path(".state/control.sock"))
    actions = control.add_subparsers(dest="action", required=True)
    for action in ("status", "release", "stop"):
        actions.add_parser(action)
    press = actions.add_parser("press", help="Timed button or chord, then release")
    press.add_argument("buttons", nargs="+")
    press.add_argument("--duration", type=float, default=0.05)
    stick = actions.add_parser("stick", help="Right stick, normalized -1..1; positive Y is up")
    stick.add_argument("--x", type=float, default=0)
    stick.add_argument("--y", type=float, default=0)
    stick.add_argument("--duration", type=float, default=0.25)
    stick.add_argument("--orientation", choices=("raw", "sideways-right"), default="raw",
                       help="raw axes or screen-oriented axes for a sideways right Joy-Con")
    sequence = actions.add_parser("sequence", help="Replace input with a bounded JSON array of steps")
    sequence.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps({"platform": platform.system(), "playable": False,
                          "usb_5ms_connection_support": "observed on one RTL8761BU; not a general compatibility guarantee",
                          "wake_reliability": "old prototype regressed; revised burst test passed once"}))
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
        if platform.system() != "Linux" or not 0 <= args.seconds <= 300 or (args.seconds == 0 and not args.control_socket):
            parser.error("Serve needs Linux; use 1..300 seconds or 0 with --control-socket")
        if (args.control_socket or args.auto_join) and args.test_button:
            parser.error("Diagnostic pulses cannot be combined with a command socket or auto-join")
        from .backend import serve
        logging.basicConfig(level=logging.INFO)
        asyncio.run(serve(args.address, args.transport, args.bond_file, args.seconds,
                          args.calibration, args.test_button, args.control_socket, args.auto_join))
    elif args.command == "control":
        from .control import send
        request = {"op": args.action}
        if args.action == "press":
            request = {"op": "set", "state": {"buttons": [button.upper() for button in args.buttons], "duration": args.duration}}
        elif args.action == "stick":
            request = {"op": "set", "state": {"x": args.x, "y": args.y, "duration": args.duration,
                                               "orientation": args.orientation}}
        elif args.action == "sequence":
            if args.file.stat().st_size > 65536:
                parser.error("Sequence file exceeds 64 KiB")
            request = {"op": "sequence", "steps": json.loads(args.file.read_text())}
        try:
            result = asyncio.run(send(args.socket, request))
        except (OSError, ValueError, asyncio.TimeoutError) as error:
            parser.exit(2, f"Control unavailable: {type(error).__name__}\n")
        print(json.dumps(result))
        if not result.get("ok"):
            parser.exit(2)
    elif args.command == "capture-calibration":
        if platform.system() != "Linux":
            parser.error("Calibration capture needs the Linux HCI backend")
        from .factory_capture import capture
        asyncio.run(capture(args.peer, args.output, args.transport))


if __name__ == "__main__":
    main()
