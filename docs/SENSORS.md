# Experimental Sensor Inputs

## Status

- Native relative optical-mouse fields in right report `0x08`: implemented,
  command-driven, opt-in, software-tested; **not console-verified**.
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

## Grip Test Pending

The owner suggested pressing **R** after connecting to register the right half
vertically instead of SL+SR. This has not yet been verified. On Change Grip/Order,
an isolated `./scripts/j2 press R --duration 0.1` can test it during allowed play
time; default automatic web registration is still SL+SR. Do not recalibrate the
physical controller or assume that R alone forms a complete two-half controller.

## References

- [ndeadly HID report layouts](https://github.com/ndeadly/switch2_controller_research/blob/master/hid_reports.md)
- [ndeadly feature commands](https://github.com/ndeadly/switch2_controller_research/blob/master/commands.md#command-0x0c---feature-select)
- [XD2Joy source](https://github.com/desktopsetup/XD2Joy/blob/main/firmware/src/main.c)
