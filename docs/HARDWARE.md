# Hardware Evidence

Initial research environment: Apple Silicon Mac, VirtualBox Ubuntu 22.04 ARM64,
Linux 5.15, TP-Link USB 2357:0604 (Realtek RTL8761BU), stock Linux firmware.
Commercial product names/revisions may use different chips; identify USB ID and
chip rather than assuming all adapters sold under the same name behave identically.

## Evidence Recorded 2026-10-29

- USB passthrough and firmware initialization: verified.
- Raw BLE scanning: verified; paired Joy-Con 2 wake advertisement captured privately.
- Standard BlueZ Set Public Address: rejected with Not Supported.
- RTL8761B configuration offset 0x30 address override: verified, then restored.
- Two-second raw wake advertisement: accepted by the adapter; user confirmed one wake.
- Repeat wake after physically attaching/removing the Joy-Con: user reported failure.
- Sustained Joy-Con 2 emulation, link encryption and 5 ms connection: not verified.
- Bumble 0.0.235 HCI-user-channel peripheral: started successfully on the above
  adapter, advertised the right Joy-Con 2 discovery payload for five seconds,
  stopped cleanly, and returned the radio to BlueZ/NXBT. No console pairing was
  attempted during that smoke test.
- Ten unit tests passed on Python 3.10 ARM64, including the vendor GATT handle
  layout, protocol encoders, pairing challenge vector and owner-only bond file.
- A fresh wake capture after the regression matched the original packet exactly.
  A revised connectable-advertising, three-burst test then woke the console
  (user confirmed). Repeat reliability and the exact regression cause remain
  unproven; PDU type and burst timing were changed together.

The wake prototype's success is not proof of a working gameplay controller. Any
new hardware results must record software/firmware version, procedure, expected
versus observed behavior, and restoration of the adapter to its original state.
Do not publish real adapter/console addresses or LTKs in issues or logs.
