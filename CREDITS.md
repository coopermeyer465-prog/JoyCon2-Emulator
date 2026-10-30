# Credits And Provenance

- **ndeadly / switch2_controller_research**:
  https://github.com/ndeadly/switch2_controller_research
  Primary factual reference for advertisements, GATT UUIDs/handles, command framing,
  pairing byte order, report fields, factory field offsets and opaque query
  response examples. No research document, firmware dump,
  descriptor blob, or captured controller memory is vendored here. The published
  challenge vector is used as a protocol interoperability test, not as a user's key.
- **desktopsetup / XD2Joy**:
  https://github.com/desktopsetup/XD2Joy
  GPL-3.0 firmware demonstrating Joy-Con 2 emulation on nRF52840 and documenting
  the 5 ms timing requirement. Its pairing handler was consulted to cross-check
  response framing/key byte order. No C firmware or Nintendo XData blobs are copied.
  This repository does not claim the author's hardware compatibility or features.
- **Google / Bumble**: https://github.com/google/bumble
  Apache-2.0 Bluetooth host, transport, ATT/GATT, notification and crypto integration.
  Used as a dependency, not redistributed as project-owned code.
- **Brikwerk / NXBT**: https://github.com/Brikwerk/nxbt
  Existing controller-emulation project used for the separate working Classic-BT
  control setup. Architectural inspiration; no NXBT source is included here.
- **Bill-git1 / Switch2-RPI-Wake**:
  https://github.com/Bill-git1/Switch2-RPI-Wake
  Raw HCI wake replay reference for the earlier local wake experiment.
- **alexvnesta / switch2controller**:
  https://github.com/alexvnesta/switch2controller
  Wake-beacon research and documentation that helped identify a practical wake path.
- **Dark Mentor LLC / DarkFirmware_real_i**:
  https://github.com/darkmentorllc/DarkFirmware_real_i
  Documented RTL8761B USB config offset 0x30 for an address override with stock
  firmware. Used in the separate local wake experiment, not yet this BLE backend.
- **PyCA / cryptography**: https://github.com/pyca/cryptography
  Existing AES implementation; no custom cryptographic primitive is implemented here.

The Python application in this repository is new project code. Crediting a source
does not imply endorsement or a license to redistribute its firmware/captures.
Future copied/adapted code must retain the original notices and compatible license.
