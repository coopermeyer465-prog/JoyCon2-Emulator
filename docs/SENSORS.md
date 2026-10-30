# Experimental Sensor Inputs

## Status

- Native relative optical-mouse fields in right report `0x08`: implemented,
  command-driven, opt-in, software-tested. Console feature enablement was observed,
  but the generated mouse-only path has not produced a cursor. A bounded private
  recorded-motion diagnostic did produce a cursor, including with command-driven
  mouse fields. This is not standalone mouse emulation yet.
- Desktop pointer capture/browser mapping: the NXBT Mouse surface supports stick
  targets and a bounded native cursor diagnostic using private recorded motion.
  See [web mouse controls](../integrations/nxbt/README.md#mouse-surface).
- Gyroscope/accelerometer: offline `common_motion()` encoder only, for the
  documented 18-byte IMU block in common report `0x05`. It is not connected to
  the BLE stream and is not a usable console gyro input.
- Generated compact `0x08` motion data: not implemented. IMU feature bit 2 stays
  disabled by default; only explicit private recorded-sensor diagnostics enable it.
- Existing buttons/stick and default feature negotiation remain unchanged.

The optical surface byte is incompletely documented. Our experimental convention
uses `0` for contact and `255` for lifted, as demonstrated in XD2Joy; it is not
calibrated height, surface quality or confirmed Switch behavior.
The CLI's optional `--surface 0..254` overrides the contact byte for experiments;
it is held only for the same 250 ms lease, with no replay of movement deltas.
It cannot be combined with `--lifted`. The default remains zero for compatibility,
not because zero has been verified as the correct contact value.

![Mouse tutorial awaiting native cursor input](images/mouse-test-pending.png)

## Command-Driven Native Mouse

Run only when testing is allowed on the console. This does not bypass play-time
limits, enable mouse in games without support, or change console settings.
After pairing, stop any existing controller session before opting in:

```sh
./scripts/j2 stop
./scripts/j2 start --experimental-mouse
./scripts/j2 status
```

For Linux `serve`, add `--experimental-mouse` to the existing calibrated command
with `--control-socket .state/control.sock`. The Mac wrapper above passes it
through to the same BLE backend. Default NXBT web startup does NOT enable it.

Both `ready` and `mouse_enabled` must be true before mouse commands are accepted.
The latter means the console selected and enabled feature bit 4; the emulator
does not force it on locally. A mouse-aware screen/game may be required. If
feature/configuration commands are rejected in the journal, save the command IDs
and lengths, not private keys or dumps, for further protocol work.

```sh
./scripts/j2 mouse --dx 12 --dy -6
./scripts/j2 mouse --lifted
./scripts/j2 release
./scripts/j2 stop
```

Deltas are raw signed 16-bit counts in native sensor axes, not screen pixels or
stick coordinates. Each accepted request is placed in one report at most, then
returns to zero movement. Surface contact lasts until 250 ms after the request;
new movements refresh that deadline, but polling does not. Explicit lift or
release clears contact immediately. Undelivered movement expires after 250 ms.
Only one movement may be pending: another is rejected rather than accumulated.
Status does not consume it, and a mouse request does not replace held buttons
or a stick sequence. Release, disconnect, registration and feature disable prevent
pending movement from being replayed. Success is a queue receipt, not a console
acknowledgement; transport failure can still lose a delta. No automatic retry.
Restart without the opt-in flag to restore the default buttons/stick-only mode.

## Gyro Work Remaining

The common-report encoder has explicit microsecond timestamps, temperature,
acceleration in g and angular velocity in degrees/second, with finite/range
checks and signed little-endian tests. It does not supply factory biases.

The console currently subscribes to compact report `0x08`, whose packed motion
format is not fully described in the primary protocol reference. XD2Joy's current
gyro implementation edits captured motion frames and quaternion fields. No
captured frames or Nintendo XData are copied here. A complete generated compact
codec, coherent timing/orientation and feature-configuration support are required
before advertising gyro or adding a live gyro command. A correct `0x05` block
alone does not prove the console will accept gyro input.

## Private Recorded-Sensor Diagnostics

The owner confirmed a cursor with the physical controller in the same tutorial.
A subsequent emulator-only replay of private recorded mouse and motion fields
also produced a cursor. Replacing recorded optical fields with command-generated
X deltas of +100 then -100, surface 50, while keeping the moving motion recording,
also produced a cursor with the physical controller untouched.

A separate experiment used a single stationary motion sample with refreshed
12-bit timestamp/interval fields and command X deltas of +5 then -5, surface 50.
That produced no visible change. These tests differ in both motion source and
delta magnitude, so they do not isolate the exact cause. Neither is a generated
motion codec or a calibrated/live gyro implementation.

The isolated Linux diagnostic accepts a private native compact capture:

```sh
joycon2-emulator serve --experimental --address ADAPTER_OWN_PUBLIC_ADDRESS \
  --calibration .state/factory-calibration.json --seconds 25 \
  --experimental-sensor-replay .state/private-compact-moving.json
```

Only optical fields and the 40-byte motion block/length are read into generated
neutral controller reports. Captured buttons, sticks, power and reserved fields
are never transmitted. At most 2048 frames / 2 MiB are accepted, startup frames
without motion are skipped, samples are consumed once without looping, and
runtime is limited to 1..30 seconds. Playback uses backend report cadence without
resampling; it is not timing-faithful physical-controller emulation. Recorded
motion timing is retained in full replay mode.

Add `--replay-command-mouse --control-socket .state/sensor-test.sock` to replace
recorded optical data with local mouse commands, for example:

```sh
joycon2-emulator control --socket .state/sensor-test.sock mouse --dx 100 --surface 50
joycon2-emulator control --socket .state/sensor-test.sock release
```

Alternatively, `--experimental-motion-baseline .state/private-compact-stationary.json`
selects the failed stationary-baseline experiment. It does not claim that the
retained opaque motion block is valid generated orientation data. Both modes
discard captured controls and reject general button/stick commands, auto-join and diagnostic
button pulses. Feature configuration commands not implemented by the backend
remain rejected, not silently acknowledged. Neither mode is enabled by default
by `j2 start` or the desktop launchers. The web UI can explicitly select the
bounded command-mouse/moving-motion diagnostic. Keep captures private; no sensor arrays
or keys are distributed with this code.

The web command-mouse mode permits a separate fixed `mouse_click` operation:
one explicit 80 ms A tap, only while the native mouse is ready. Repeated clicks
inside that interval cannot extend the hold. Release, feature disable and loss
of readiness clear it. Only the generated A bit can pass through command-mouse
playback; captured buttons and all other generated buttons remain excluded.
Full recorded-sensor playback without command mouse still sends no buttons.

## Grip Test Result

The owner suggested pressing **R** after connecting to register the right half
vertically instead of SL+SR. During the Elgato-observed test, a 150 ms R pulse
produced the upright L+R pair prompt in slot 1, but an A pulse did not finish
registration. SL+SR then registered the single horizontal half and X confirmed
normally. This does not establish usable vertical single-half operation;
default automatic web registration remains SL+SR. No calibration was changed.

## Private Sensor Capture

The next investigation compares the optical surface and motion fields with an
owned physical right Joy-Con, detached, in SYNC mode and flat on a table.
Stop the emulator and other adapter owners before running the tool in Linux:

```sh
sudo .venv/bin/joycon2-emulator capture-sensors --peer JO:YC:ON:AD:DR:SS \
  --output .state/sensors-flat.json --seconds 5
```

Use the physical controller's address for this direct reader, not the emulator's
address. The tool selects the demonstrated runtime feature mask `0xFF`, subscribes
to **one** input format (common by default), then disables reporting and
disconnects. The mask includes vibration capability, but no vibration output
command is sent. Feature commands have a 500 ms initialization gap. The tool
does not request pairing, flash access, calibration changes or firmware updates.
Duration is limited to 1..15 seconds and at most 512 reports. Captures are written
owner-only and existing files/symlinks are refused. Keep them in gitignored
`.state`; do not publish captured report arrays. This reader's software tests
do not establish that every physical firmware permits unpaired sensor streaming.

For a separate experimental compact-channel attempt, add `--report right
--console-session`. This writes the fixed runtime session-start value and report
rate descriptor, sends an initial status query, and sends feature commands through the combined channel with
a zeroed output prefix. It does not implement the console's complete initialization
sequence and is not a guarantee of streaming. On the initial unpaired common-path
attempts, the physical controller acknowledged feature commands but sent no input
notifications; direct input reads returned READ_NOT_PERMITTED. No capture file
was written. Connection failures leave the output untouched and report the
disconnect reason when available.

`--random-address` tests a temporary random central address, without cloning a
controller or storing a bond. Both public-address and random-address common
attempts, and the minimal compact-session attempt, returned no input reports on
the development Linux setup. This is a capture limitation, not proof that pairing
is required or the sensors are absent.

## Native Mac Reader

A separate native CoreBluetooth reader successfully captured 401 common input
reports from the owned right Joy-Con without requesting pairing. This avoids the
Linux/USB capture problem; it does **not** move controller emulation to macOS or
establish a working optical-mouse/gyro emulator.

The native helper requires macOS and Xcode Command Line Tools. It uses Apple's
frameworks and no downloaded packages. The wrapper compiles and ad-hoc signs the
local helper in gitignored `.state`. macOS may ask for Bluetooth permission for
the helper or calling application. It does not need Accessibility, input-monitoring,
root access, a HID driver or a device-pairing confirmation.

```sh
./scripts/capture-mac-sensors --self-test
./scripts/capture-mac-sensors --output .state/sensors-native-stationary.json --seconds 5
```

For an experimental native capture of the console's compact right-half format,
add `--report right` and choose a new output filename. This selects the `d5a9...`
input characteristic instead of the common `ab7d...fd2` characteristic; saved
frames are labeled `right` rather than `common`. The same two runtime feature
commands, bounds and private-file safeguards apply. A physical stationary
sensor-edge capture saved 405 compact reports, including 334 with nonzero motion
data and a motion length of 40. The optical surface byte varied even while
stationary; treating zero as a calibrated contact reading is not established.
This capture does not establish working emulated mouse or gyro. Common captures cannot be
used as compact frames: their mouse fields and motion encoding differ.
A subsequent physical movement capture saved 750 reports, including 679 with
40-byte motion data and 657 with nonzero optical deltas. Active surface bytes
ranged from 31 to 122; no nonzero movement coincided with a zero surface byte.
These are observations from one owned controller and surface, not calibrated
limits or proof that the optical byte alone controls cursor visibility.
An emulator-only tutorial burst with surface byte 50 and 60 accepted requests
produced no visible change. Neither the contact lease nor this surface-byte
adjustment established usable mouse emulation.

Offline checks of the compact captures found that candidate fixed gyro/sample
offsets from XD2Joy did not yield coherent stationary readings for this capture.
Their interpretation is not validated here. The normal stream contains no guessed
gyro values; explicit private recorded-sensor diagnostics are separate from it.

Put exactly one owned right Joy-Con into SYNC mode first. Discovery filters for
the right-half product and a zeroed reconnect-host field; multiple matching
controllers are refused. The reader scans for eight seconds, connects to the
common-input service, subscribes, and sends the two reporting commands 500 ms
apart. The complete run has a 45-second timeout and at most 2048 frames. It then
disables runtime reporting and disconnects. Capture files use mode 0600 and are
never overwritten; no addresses, pairing keys or firmware are recorded.
If a connection drops after valid reports arrive, those reports are retained
with `capture_complete: false` and exit code 3. Such a partial recording is
diagnostic evidence, not a successful full-duration test. Empty captures are
still not saved. The native self-test checks both the 2048-frame limit and this
partial-capture behavior without accessing Bluetooth.

Stationary data is a baseline at an **unknown tilt**, not a recalibration. For
optical samples the sensor edge must face the table as in mouse mode; laying the
controller face-up leaves the sensor away from the surface. Move it only once
the helper announces recording. The first capture contained plausible stationary
acceleration/gyro readings and lifted optical readings; optical motion and live
emulated gyro still required further tests at that stage. A later completed
10-second movement recording saved 748 reports with changing optical X/Y counters,
surface/distance fields and gyro readings. This confirms native physical sensor
acquisition, not the emulator's compact-report encoding or calibrated angular
units. Captures remain private and are not
distributed in this repository.

## References

- [ndeadly HID report layouts](https://github.com/ndeadly/switch2_controller_research/blob/master/hid_reports.md)
- [ndeadly feature commands](https://github.com/ndeadly/switch2_controller_research/blob/master/commands.md#command-0x0c---feature-select)
- [XD2Joy source](https://github.com/desktopsetup/XD2Joy/blob/main/firmware/src/main.c)
- [JoeGeC common and console input sessions](https://github.com/JoeGeC/joycon2android/blob/main/docs/protocol.md)
- [seitanmen native Mac BLE reader](https://github.com/seitanmen/Joycon2forMac)
