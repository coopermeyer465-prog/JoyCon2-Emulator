# Architecture And Milestones

## Boundaries

- `protocol.py`: pure advertisement/command/report encoders; no hardware writes.
- `pairing.py`: explicit address -> key -> challenge -> finalize state machine;
  AES delegated to PyCA. Finalized records are written atomically with mode 0600.
- `controller.py`: dispatches implemented commands; handles documented initialization
  queries, virtual player-LED/vibration state and delegates pairing, memory and
  feature masks, while rejecting unknown commands.
- `memory.py`: generated virtual metadata, limited private calibration import,
  opaque compatibility fields and erased virtual user-calibration slots. Never
  responds with pairing keys or Nintendo firmware.
- `features.py`: explicit buttons/stick feature enable/mask state. Sensors are not
  advertised as implemented and reports wait for feature enablement.
- `factory_capture.py`: direct BLE client, read-only four-block allowlist, no SMP
  pairing or arbitrary flash/address commands. Output is private and gitignored.
- `input_test.py`: allowlisted, opt-in pulse (HOME 50 ms, others 250 ms) with explicit release.
  Not a live gamepad source; default hardware runs remain neutral.
- `control.py`: owner-only Unix socket, validated timed input sequences, replacement
  and release. Input requires an encrypted, initialized, subscribed connection.
- `backend.py`: Bumble HCI-socket transport, vendor GATT services, pairing notifications,
  neutral reports and opt-in command input. The adapter keeps its own public identity.
- `scripts/j2`: Mac-to-Vagrant command wrapper and transient systemd service lifecycle;
  restores classic Bluetooth services on exit. Private configuration stays in `.state`.
- `cli.py`: read-only diagnostics, local capture inspection and opt-in lab startup.
- `tests/`: packet validation, known challenge vector, persistence permissions and
  exact GATT layout. Unit tests do not certify compatibility with a console.

## Next Milestones

1. Extend the observed 5 ms encrypted link to sustained input/stability tests.
   A 5 ms link on one stock RTL8761BU has now been observed. Do not patch kernel limits
   or flash experimental firmware without a separate recovery plan.
2. Handle the console initialization command sequence, report-mode/feature changes,
   and required memory reads using legitimately obtained/generated calibration.
   Do not pretend unsupported commands have succeeded.
   Hardware testing has advanced through generated metadata, firmware info,
   Nintendo key exchange, encryption, virtual LEDs and factory calibration reads.
3. Extend verified custom pairing/encryption/per-process bond reload to host/console
   restart tests. Version-2 private records bind to the controller identity and
   support separate keys for both console addresses.
4. Validate command-driven right-stick/buttons, timed sequences and neutral-on-disconnect
   behavior on the console. The private command API is implemented; a gamepad relay is not.
   Reuse the existing measured
   Lic2 WebHID decoder only after auditing its provenance and adding tests.
5. Implement a left half and decide whether one controller supports two peripheral
   connections at the required interval. One combined gamepad is not assumed.
6. Integrate wake/reconnect under the emulator's own identity, rather than borrowing
   the physical Joy-Con's wake identity. Test after dock/undock, reboot and sleep.

## Current Limitations

The lab supplies generated metadata and optional privately read calibration blocks,
but does not respond to arbitrary initialization commands or provide a live
gamepad relay. Some opaque query responses are documented compatibility constants,
not implementations of their unknown underlying features. It must not be used as
a replacement for a normal controller yet.
Stock BLE support in a USB adapter is not proof of Nintendo's below-standard timing.
