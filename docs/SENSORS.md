# Experimental Sensor Inputs

## Status

- Native relative optical-mouse fields in right report `0x08`: implemented,
  command-driven, opt-in, software-tested. Console feature enablement was observed,
  but **no cursor appeared** in the console's mouse tutorial. Not usable yet.
- Desktop pointer capture/browser mouse mapping: not implemented. The removed
  mouse-to-stick mode remains removed.
- Gyroscope/accelerometer: offline `common_motion()` encoder only, for the
  documented 18-byte IMU block in common report `0x05`. It is not connected to
  the BLE stream and is not a usable console gyro input.
- Compact `0x08` motion data: not implemented. IMU feature bit 2 stays disabled.
- Existing buttons/stick and default feature negotiation remain unchanged.

The optical surface byte is incompletely documented. Our experimental convention
uses `0` for contact and `255` for lifted, as demonstrated in XD2Joy; it is not
calibrated height, surface quality or confirmed Switch behavior.

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
returns to zero movement/lifted. Undelivered movement expires after 250 ms.
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
address. The tool enables runtime buttons/stick/IMU/mouse features, subscribes to
common/right input reports, then disables those features and disconnects. It
does not request pairing, flash access, calibration changes or firmware updates.
Duration is limited to 1..15 seconds and at most 512 reports. Captures are written
owner-only and existing files/symlinks are refused. Keep them in gitignored
`.state`; do not publish captured report arrays. This reader's software tests
do not establish that every physical firmware permits unpaired sensor streaming.

## References

- [ndeadly HID report layouts](https://github.com/ndeadly/switch2_controller_research/blob/master/hid_reports.md)
- [ndeadly feature commands](https://github.com/ndeadly/switch2_controller_research/blob/master/commands.md#command-0x0c---feature-select)
- [XD2Joy source](https://github.com/desktopsetup/XD2Joy/blob/main/firmware/src/main.c)
