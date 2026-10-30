# Changelog

## 2026-10-30

### Input Diagnostics And Mapping

- Verified A/B/X/Y, R/ZR, PLUS, stick click and SL/SR in the Switch's own
  controller-button test, observed through Elgato. HOME and four-direction menu
  navigation were also checked; C/GameChat was deliberately not opened.
- Added an on-screen tap for every right-half button and four 150 ms direction
  controls. Fixed keyboard stick clicks and the reversed R/ZR key mapping.
- Added an independent printed/sideways face-button selector. Printed X confirms
  and printed A goes Back when the half is sideways; conventional sideways A/B
  can now be selected without changing raw CLI/JSON button names.
- Hid Pro-only keyboard rows in right-half mode and added browser keyboard
  regression tests to CI. Published the input matrix and console test screenshot.
- Verification: 59 Python tests, seven mocked web tests and two JavaScript tests
  passed. The console blocks stick calibration while held horizontally, so full
  analog-range/diagonal behavior remains software-tested, not visually certified.

### Combined Interface

- Published a combined NXBT web overlay with Pro Controller / Joy-Con 2 (R)
  backend selection, isolated BLE process, session ownership and adapter handoff.
- Preserved the existing keyboard, browser Gamepad and Lic2 WebHID input paths.
- Added a selectable single-stick source, raw/sideways orientation, explicit
  SL/SR and C/GameChat controls; keyboard mappings are `-`, `=` and `0`.
- Added automatic SL+SR registration after a two-second initialization grace,
  with input blocked until the 250 ms pulse releases. Registration was observed
  through the owner's Elgato capture after reconnecting.
- Added an input refresh lease, bounded JSON sequences and orderly backend stop.
- Published wake scanner/replay/configuration helpers without personal captures,
  addresses, keys or firmware; documented adapter-specific risks and recovery.
- Updated setup, hardware evidence, architecture, licensing and provenance.
- Removed a temporary mouse-to-stick mode at the owner's request. Native Joy-Con
  2 optical-mouse reports remain unimplemented future work.
- Verification: 55 core/bridge unit tests and six mocked web-handler tests passed
  in the existing Linux VM. Real console tests cover registration, A/B/HOME and
  movement, not all controls or sustained gameplay.

## 2026-10-29

- Established experimental right-half pairing, private calibration import,
  encrypted bond reload and observed 5 ms / 15 ms connections on one RTL8761BU.
- Added timed CLI input, calibrated stick coordinates, local owner-only command
  socket, JSON sequences and the Mac-to-Vagrant `scripts/j2` wrapper.
- Added HCI transmit-queue draining after delayed HOME delivery was interpreted
  as a hold. A subsequent 50 ms HOME tap returned from Settings to HOME.
