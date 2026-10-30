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

## Console Connection Test

With Controllers > Change Grip/Order open, the console connected to the Bumble
peripheral and sent 07/01. Initially this command retried because it had no handler.
After adding its documented response, the console advanced to 02/04: a 64-byte
memory read at 0x13000. That read is deliberately left unimplemented until the
factory configuration/calibration format is supplied correctly.

The diagnostic run reported an initial connection interval of 15.0 ms, zero
peripheral latency and a 2000 ms supervision timeout. No disconnect was reported
during the bounded exchange, but this is NOT a sustained gameplay/stability test,
and says nothing yet about a later switch to a 5 ms interval. Pairing/encryption
was not completed. Thirteen unit tests pass with the new command dispatcher.

## Extended Initialization Test

Later tests on the same adapter advanced through generated factory metadata,
virtual firmware version 0.1.0/right-half information, documented opaque queries,
Nintendo 15/01 -> 15/04 -> 15/02 -> 15/03 pairing, and 03/07 -> 03/09 secondary
host-key storage. The secondary address received a different LTK, so per-address
key persistence was implemented. Bumble reported link encryption active, and a
later process restarted from private saved keys and re-established encryption.

After read-only capture of four calibration/factory blocks from the owned physical
right Joy-Con, subsequent emulator connections reported a **5.0 ms** connection
interval (zero peripheral latency, 2000 ms supervision timeout) with active
encryption. The console accepted the imported 0x13080 block, erased virtual
user-calibration data at 0x1FC040, and generated metadata at 0x13040. These are
bounded initialization tests, NOT sustained gameplay or broad hardware certification.

The private reader captured only 256 bytes at 0x13080/0x130C0/0x13100/0x13140,
with no pairing/flash-write commands. No captures or keys were published. The
calibration fields and some opaque factory bytes are not fully understood.

With those blocks loaded, generated opaque factory fields, erased user calibration
and the additional documented query responses, a later bounded run completed every
initialization request observed so far: through feature-enable 0C/04 and the
01/0C power/status query, with no unhandled command in that run. That is not proof
that every initialization path is implemented. Neutral stick coordinates are
derived from the imported primary factory calibration to avoid midpoint drift.
Visible console registration and actual button effects still need confirmation.

## Registration Confirmed

An instrumented neutral run queued 6894 reports after the console subscribed and
enabled buttons/stick features. A later opt-in 250 ms SL+SR pulse was followed by
another player-LED command, and the user confirmed that a new single right Joy-Con
registered on Change Grip/Order. This verifies a real console-visible effect from
the emulator's button report, not just advertising or a successful BLE connection.

The link used 15 ms for that registration run; earlier calibrated/encrypted runs
used 5 ms. Both intervals have been observed on this adapter, but sustained gameplay,
input latency, additional buttons, full stick range and a second Joy-Con remain
untested. Thirty-seven unit tests pass, including bounded test-pulse release.

The subsequent HOME test had a console-visible effect, but the user clarified
that it opened the hold/Quick Settings menu rather than going HOME. The HOME
pulse is now scheduled for 50 ms instead of 250 ms, with explicit release tests;
short-tap behavior on the console is not yet verified. Join remains 250 ms.

## Command API Test

Forty-five unit tests pass on guest Python 3.10, including calibrated asymmetric
stick ranges, timed commands/sequences, invalid-input rejection, neutral release,
Unix-socket permissions and preservation of existing non-socket files.
The Mac wrapper started a transient command service, reconnected with the saved
bond, and reported encrypted/initialized input readiness. One 150 ms half-right
stick movement and one 50 ms HOME tap were accepted through that service. Status
after the stick command showed neutral coordinates and no queued steps.
Console-visible movement and short-HOME interpretation still require user
confirmation; server acceptance alone is not proof of either.
The user reported no clear visible effect with the console already on HOME.
That screen does not provide a decisive right-stick or short-HOME test.
A subsequent 50 ms HOME command from System Settings also had no visible effect,
according to the user. Short-HOME control is therefore not validated. Transition
logging was added at the BLE notification call to distinguish queued command
state from reports actually submitted to the transport; neither proves console
acceptance.
