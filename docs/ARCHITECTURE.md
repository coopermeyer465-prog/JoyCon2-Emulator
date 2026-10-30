# Architecture And Milestones

## Boundaries

- `protocol.py`: pure advertisement/command/report encoders; no hardware writes.
- `pairing.py`: explicit address -> key -> challenge -> finalize state machine;
  AES delegated to PyCA. Finalized records are written atomically with mode 0600.
- `controller.py`: dispatches implemented commands; handles documented initialization
  07/01 and delegates pairing, while rejecting unknown commands.
- `backend.py`: Bumble HCI-socket transport, vendor GATT services, pairing notifications,
  and a bounded neutral-report lab. The adapter keeps its own public identity.
- `cli.py`: read-only diagnostics, local capture inspection and opt-in lab startup.
- `tests/`: packet validation, known challenge vector, persistence permissions and
  exact GATT layout. Unit tests do not certify compatibility with a console.

## Next Milestones

1. Measure real controller/console connection negotiation. Determine whether the
   USB controller and firmware accept a 5 ms link. Do not patch kernel limits
   or flash experimental firmware without a separate recovery plan.
2. Handle the console initialization command sequence, report-mode/feature changes,
   and required memory reads using legitimately obtained/generated calibration.
   Do not pretend unsupported commands have succeeded.
   Hardware testing has advanced past 07/01 to a 64-byte read at 0x13000.
3. Validate custom Nintendo pairing, link encryption, private key persistence,
   bond reload and reconnect across host/console restarts.
4. Add user input with neutral-on-disconnect behavior. Reuse the existing measured
   Lic2 WebHID decoder only after auditing its provenance and adding tests.
5. Implement a left half and decide whether one controller supports two peripheral
   connections at the required interval. One combined gamepad is not assumed.
6. Integrate wake/reconnect under the emulator's own identity, rather than borrowing
   the physical Joy-Con's wake identity. Test after dock/undock, reboot and sleep.

## Current Limitations

The lab exposes protocol structure, but does not synthesize Nintendo factory data,
respond to arbitrary initialization commands, implement full input activation, or
restore bonds. It must not be used as a replacement for a normal controller yet.
Stock BLE support in a USB adapter is not proof of Nintendo's below-standard timing.
