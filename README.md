# JoyCon2-Emulator

An experimental Joy-Con 2 BLE emulator for Linux and USB-passthrough virtual
machines, including Apple Silicon Macs. The goal is one software stack for
pairing, waking, reconnecting, and sending controller input to a Nintendo Switch 2.

**Early research milestone, NOT a working gameplay controller yet.**
Do not buy hardware on the assumption that this will work. Keep an existing
controller/NXBT setup available. No Nintendo firmware, flash dumps, personal
Bluetooth captures, or pairing keys are distributed.

## Status

| Component | Current state |
| --- | --- |
| Nintendo discovery/reconnect/wake advertisement encoding | Implemented, unit tested |
| Right Joy-Con 2 button/stick report encoding | Implemented, unit tested; not console validated |
| Nintendo command framing and pairing challenge/response | Implemented, known-vector tested |
| Vendor GATT database with expected attribute handles | Implemented on Bumble; layout tested |
| Bounded Linux BLE peripheral lab | Implemented; hardware results in docs/HARDWARE.md |
| Console discovery and initial command exchange | Console connected at 15 ms; accepted documented 07/01 response |
| Stock USB adapter sleep wake | Local prototype and revised connectable/three-burst test both woke one console |
| Reliable sleep wake after physical Joy-Con docking | Old prototype regressed; revised test passed once, repeat reliability unproven |
| 5 ms connection interval on Realtek RTL8761BU | Unverified; possible hardware/firmware blocker |
| Console initialization, calibration/flash responses | First 07/01 handled; next request is 64 bytes at 0x13000, not implemented |
| Bond reload, reliable reconnect, LTK interoperability | Not validated; bond reload not implemented |
| Live gamepad/WebHID relay, left/right combined controller | Not implemented |
| Gyro, mouse, rumble, NFC, firmware updates | Not implemented |

This is **not a port of XD2Joy firmware to a USB dongle** and is not an NXBT fork.
It uses [Bumble](https://github.com/google/bumble) for the BLE host/GATT engine.
Protocol research and inspiration are credited in [CREDITS.md](CREDITS.md).

## Install And Run Tests

Python 3.10+ is required. On Debian/Ubuntu, install `python3-venv`, `bluez`,
and `usbutils` using your package manager first. No hardware is needed for tests.

```sh
git clone https://github.com/coopermeyer465-prog/JoyCon2-Emulator.git
cd JoyCon2-Emulator
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
joycon2-emulator doctor
joycon2-emulator advertisement --side right
```

`advertisement` only prints hex; it does not transmit. `doctor` performs
read-only checks. Normal macOS CoreBluetooth APIs are not this project's backend.
For the HCI-socket backend on a Mac, run inside Linux with a dedicated USB
Bluetooth adapter passed through. Never pass through the Mac's internal radio.

## Experimental Peripheral Lab

**This cannot control games yet.** It is intended to collect the next missing
initialization steps and determine whether the adapter can hold a BLE link.
Use the adapter's own address, NOT the address of a physical Joy-Con.

1. Make sure your USB adapter has working Linux firmware and appears in `hciconfig -a`.
2. Stop software using that adapter. The example below assumes systemd and the
   optional `nxbt-web` service; adapt service names for your installation.
3. Open Controllers > Change Grip/Order on the console only when testing discovery.
4. Run the lab for at most 60 seconds. Unknown initialization commands are logged
   and deliberately not acknowledged as implemented.

```sh
sudo bash
trap 'systemctl start bluetooth; systemctl start nxbt-web 2>/dev/null || true' EXIT
systemctl stop nxbt-web 2>/dev/null || true
systemctl stop bluetooth
hciconfig hci0 down
.venv/bin/joycon2-emulator serve --experimental --address AD:AP:TE:RS:MA:CC --seconds 60
exit
```

Replace `AD:AP:TE:RS:MA:CC` with the actual adapter address (the placeholder is
deliberately invalid). Do not run wake, NXBT, or a second emulator simultaneously
on the same adapter. The experimental backend handles one right Joy-Con only.
It stores newly finalized pairing material under `.state/bond.json` with owner-only
permissions, but reconnecting from a saved bond is a future milestone.

## Wake Prototype And Regression

The separately developed local prototype uses an RTL8761BU USB adapter to replay
a captured wake advertisement with the originating controller's public address.
An initial test woke the console, but a later test after attaching the physical
Joy-Con to the console did not. A fresh capture matched the original exactly.
Changing to connectable advertisements in three short bursts woke the console
in a subsequent user-confirmed test. This changed two variables and does not
isolate the cause or prove long-term reliability. Docking
must not be assumed to rotate the address, keys, or packet without evidence.
This repo currently includes advertisement inspection/encoding, not the original
machine-specific wake launcher or its private capture.

To inspect an existing local capture produced by the prototype:

```sh
joycon2-emulator inspect-capture /private/path/to/capture.json
```

Keep captures private. Next, repeat sleep/wake cycles with docking/undocking and
host restarts, then isolate advertising PDU type from burst timing. Wake success
alone does not prove that full controller emulation works.

## Development

See [architecture and milestones](docs/ARCHITECTURE.md),
[hardware evidence](docs/HARDWARE.md), and [contribution guidelines](CONTRIBUTING.md).
Code is GPL-3.0-only. Dependencies retain their own licenses. Nintendo and Joy-Con
are Nintendo trademarks; this project is unofficial and unaffiliated.
