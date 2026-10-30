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
| Right Joy-Con 2 button/stick report encoding | Implemented; user confirmed SL+SR registered a single right Joy-Con; live relay still absent |
| Nintendo command framing and pairing challenge/response | Implemented; completed exchange with one console |
| Vendor GATT database with expected attribute handles | Implemented on Bumble; layout tested |
| Bounded Linux BLE peripheral lab | Implemented; hardware results in docs/HARDWARE.md |
| Console discovery and initial command exchange | Console accepted metadata/version queries and advanced through calibration reads |
| Stock USB adapter sleep wake | Local prototype and revised connectable/three-burst test both woke one console |
| Reliable sleep wake after physical Joy-Con docking | Old prototype regressed; revised test passed once, repeat reliability unproven |
| 5 ms connection interval on Realtek RTL8761BU | Observed on the test adapter, including an encrypted connection; sustained gameplay untested |
| Console initialization, calibration/flash responses | Generated metadata, allowlisted private calibration import, erased user-calibration slots; incomplete overall |
| Bond reload and LTK interoperability | Implemented per-address keys; encrypted reconnect observed after process restart; long-term reliability untested |
| Player LEDs and vibration requests | Virtual state/sink only, no physical output |
| Opt-in button smoke tests | HOME 50 ms, join/A/B 250 ms; join confirmed; old HOME pulse opened Quick Settings |
| Command-driven buttons/right stick | Implemented with timed release, sequences and a private local socket; console behavior under test |
| Live gamepad/WebHID relay, left/right combined controller | Not implemented |
| Gyro, mouse, physical rumble, NFC, firmware updates | Not implemented |

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

**This is not a full gameplay controller yet.** It is intended to collect missing
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
permissions and reloads them on startup. The console can supply different keys for
its two host addresses; these are stored separately. Do not clear this file just
to rerun the lab. Existing version-1 single-key files migrate when next saved.

By default the lab sends neutral reports only after the console subscribes and
enables the implemented input features. To send one explicit SL+SR registration
pulse, add `--test-button join` to `serve`. Alternatives are `home`, `a` and `b`.
The pulse starts two seconds after the subscribed report stream starts, lasts
50 ms for HOME or 250 ms for join/A/B, then releases. The earlier 250 ms HOME
test was interpreted as a hold and opened Quick Settings; the shorter timing
needs another physical-console test. Keep the console on the appropriate screen before starting.
This is a diagnostic input test, not the live Lic2/WebHID relay.

## Command Control

After initial pairing and private calibration import, the backend can accept
timed button/stick commands. This emulates **one right Joy-Con**, not a complete
two-stick controller. Supported buttons: `A B X Y R ZR PLUS STICK HOME C SL SR`.
There is no left stick, D-pad, L or ZL, and no video capture or power switching.

For a Mac using an existing Vagrant Linux VM, configure the wrapper once. Replace
the deliberately invalid address with the USB adapter's own address. The guest
must already have this project, its dependencies, saved bond and calibration.
The paths below are examples; use your existing guest Python environment.

```sh
./scripts/j2 configure --vm-dir /path/to/vagrant-project \
  --guest-dir /home/vagrant/JoyCon2-Emulator \
  --guest-python /home/vagrant/JoyCon2-Emulator/.venv/bin/python \
  --address AD:AP:TE:RS:MA:CC
./scripts/j2 start
./scripts/j2 status
./scripts/j2 stick --x 0.5 --y 0 --duration 0.15
./scripts/j2 press HOME --duration 0.05
./scripts/j2 release
./scripts/j2 stop
```

Wake the console and wait for `"ready": true` before sending input. An initial
registration may require Change Grip/Order and `./scripts/j2 press SL SR
--duration 0.25`. The wrapper resumes the VM if necessary, stops BlueZ/NXBT and
starts a transient `joycon2-command.service`. Stopping or exiting that service
restores BlueZ/NXBT. Local configuration is private in `.state/mac.json`.
On the original development Mac, the separate wake shortcut stops this service
before using the adapter; run `./scripts/j2 start` afterward to resume control.
The public repository does not include that machine-specific wake shortcut.

Stick coordinates are -1 to 1, positive Y is up, and imported factory calibration
maps them to report coordinates. Each command replaces the previous command or
sequence. Inputs automatically return to neutral after their duration, on loss
of readiness, and on orderly shutdown. Per-step duration is 0.02 to 10 seconds;
sequences allow up to 256 steps and 300 seconds total. These are host-side timings,
not guarantees of radio delivery or game latency. A successful reply means the
input was queued, not that the console acknowledged its visible effect.

`./scripts/j2 sequence examples/button-stick.json` sends a JSON step array with
optional `buttons`, `x`, `y` and `duration` fields. **That example presses A**;
inspect it before running it on a console. Sequences avoid one SSH round trip per
step. `release` cancels pending input immediately at the host scheduler.

For native Linux, add `--control-socket .state/control.sock --seconds 0` to
the calibrated `serve` invocation above, then use a second terminal:

```sh
sudo .venv/bin/joycon2-emulator control --socket .state/control.sock status
sudo .venv/bin/joycon2-emulator control --socket .state/control.sock press HOME --duration 0.05
sudo .venv/bin/joycon2-emulator control --socket .state/control.sock stop
```

The socket is owner-only (0600), accepts bounded local JSON requests and opens no
TCP listener. Continuous serving requires the socket; diagnostic pulses cannot
be combined with command control. Keep keys, calibration and `.state` private.

## Private Calibration Capture

Without calibration data the lab stops at the first unsupported factory read.
The optional reader connects to your owned right Joy-Con without requesting SMP
or Nintendo pairing. It issues only memory-read command 02/04 for four 64-byte
factory blocks at 0x13080, 0x130C0, 0x13100 and 0x13140. It never requests the
pairing-key region or firmware banks and exposes no flash-write operation.

Stop BlueZ/NXBT and bring hci0 down as in the lab example. Detach the physical
Joy-Con, hold SYNC until its LEDs cycle, then run these commands in that same
root shell, replacing the placeholders with real local addresses:

```sh
.venv/bin/joycon2-emulator capture-calibration --peer JO:YC:ON:AD:DR:SS --output .state/factory-calibration.json
.venv/bin/joycon2-emulator serve --experimental --address AD:AP:TE:RS:MA:CC --calibration .state/factory-calibration.json --seconds 60
```

The file is owner-only, excluded from Git and not shipped with this repo. The
reader refuses to overwrite it. The importer accepts only those four exact
blocks, so a firmware dump or pairing-key file cannot be imported through it.
The emulator retains generated serial/colors and the USB adapter's own identity.
Neutral reports use the imported primary stick center rather than assuming 2048.
Custom user-calibration slots are represented as erased; no physical calibration
is changed. The meaning of some factory fields remains unknown, so compatibility
is experimental and is not a claim of complete, faithful Joy-Con emulation.

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
