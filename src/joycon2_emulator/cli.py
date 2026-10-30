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
    lab.add_argument("--experimental-mouse", action="store_true", help="Advertise native optical mouse (unverified on console)")
    recorded = lab.add_mutually_exclusive_group()
    recorded.add_argument("--experimental-sensor-replay", type=Path,
                     help="Isolated private compact sensor playback, max 30 seconds; not live gyro")
    recorded.add_argument("--experimental-motion-baseline", type=Path,
                          help="Private stationary motion baseline with command mouse, max 30 seconds; not live gyro")
    lab.add_argument("--replay-command-mouse", action="store_true",
                     help="With sensor replay, replace recorded mouse fields with socket commands")
    lab.add_argument("--calibration", type=Path, help="Private allowlisted factory-data capture")
    lab.add_argument("--test-button", choices=("join", "home", "a", "b"),
                     help="Send one pulse after subscribed input starts (HOME 50 ms, others 250 ms); join means SL+SR")
    capture = commands.add_parser("capture-calibration", help="Read four factory blocks; no pairing/flash writes")
    capture.add_argument("--peer", required=True)
    capture.add_argument("--output", type=Path, default=Path(".state/factory-calibration.json"))
    capture.add_argument("--transport", default="hci-socket:0")
    sensors = commands.add_parser("capture-sensors", help="Private input capture; runtime feature selection only, no pairing/flash access")
    sensors.add_argument("--peer", required=True)
    sensors.add_argument("--output", type=Path, required=True)
    sensors.add_argument("--transport", default="hci-socket:0")
    sensors.add_argument("--seconds", type=int, default=5)
    sensors.add_argument("--report", choices=("common", "right"), default="common")
    sensors.add_argument("--console-session", action="store_true", help="Runtime console channel/rate setup; use with --report right")
    sensors.add_argument("--random-address", action="store_true", help="Use a temporary random central address; no stored pairing")
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
    mouse = actions.add_parser("mouse", help="One native optical delta; requires experimental mouse and console enablement")
    mouse.add_argument("--dx", type=int, default=0)
    mouse.add_argument("--dy", type=int, default=0)
    mouse.add_argument("--lifted", action="store_true")
    mouse.add_argument("--surface", type=int, choices=range(255), metavar="0..254",
                       help="Experimental raw surface byte, not calibrated distance")
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
        if args.replay_command_mouse and not args.experimental_sensor_replay:
            parser.error("--replay-command-mouse requires --experimental-sensor-replay")
        if args.experimental_sensor_replay and (not 1 <= args.seconds <= 30 or (args.control_socket and not args.replay_command_mouse)
                                                or args.auto_join or args.test_button):
            parser.error("Sensor replay needs 1..30 seconds and no command socket, auto-join or test button")
        if args.experimental_motion_baseline and (not 1 <= args.seconds <= 30 or args.auto_join or args.test_button):
            parser.error("Motion baseline needs 1..30 seconds and no auto-join or test button")
        from .backend import serve
        logging.basicConfig(level=logging.INFO)
        asyncio.run(serve(args.address, args.transport, args.bond_file, args.seconds,
                          args.calibration, args.test_button, args.control_socket, args.auto_join,
                          args.experimental_mouse, sensor_replay=args.experimental_sensor_replay,
                          motion_baseline=args.experimental_motion_baseline,
                          replay_command_mouse=args.replay_command_mouse))
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
        elif args.action == "mouse":
            request = {"op": "mouse", "dx": args.dx, "dy": args.dy, "lifted": args.lifted}
            if args.surface is not None:
                request["surface"] = args.surface
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
    elif args.command == "capture-sensors":
        if platform.system() != "Linux":
            parser.error("Sensor capture needs the Linux HCI backend")
        from .sensor_capture import capture
        try:
            asyncio.run(capture(args.peer, args.output, args.transport, args.seconds, args.report,
                                args.console_session, args.random_address))
        except (OSError, ValueError, asyncio.TimeoutError) as error:
            parser.exit(2, f"Sensor capture unavailable: {str(error) or type(error).__name__}\n")


if __name__ == "__main__":
    main()
