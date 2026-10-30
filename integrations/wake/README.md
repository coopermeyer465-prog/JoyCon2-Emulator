# Switch 2 Sleep Wake Prototype

Published versions of the locally tested scanner, replay and configuration
helpers. This is adapter-specific: USB 2357:0604 / Realtek RTL8761BU, hci0, stock
Linux firmware. It does not use an ESP32 or the Mac's internal Bluetooth. It
wakes normal sleep, not a fully powered-off Switch. Other revisions are untested.

Only use your owned console and its paired Joy-Con. Captures contain private
Bluetooth identities and a usable wake signal. Store them outside the repository
or under its gitignored `.state/`; never attach captures to public issues.

Stop all adapter owners first. Adapt service names for your setup. These examples
run in the Linux VM from this directory and require BlueZ tools and `usbreset`.

```sh
sudo bash
trap 'systemctl start bluetooth nxbt-web' EXIT
systemctl stop joycon2-web joycon2-command 2>/dev/null || true
systemctl stop nxbt-web bluetooth
python3 capture_switch2_wake.py /private/path/wake.json --seconds 60
exit
```

Once the scanner announces it is running, put the console in normal sleep and
press HOME on its already paired, detached right Joy-Con. The scanner performs
read-only advertising capture, does not pair, and refuses to overwrite output.
The capture file is created with mode 0600. Keep it private.

For replay, put the Switch back in sleep and leave the physical Joy-Con alone:

```sh
sudo bash
trap 'systemctl start bluetooth nxbt-web' EXIT
systemctl stop joycon2-web joycon2-command 2>/dev/null || true
systemctl stop nxbt-web bluetooth
python3 replay_switch2_wake.py /private/path/wake.json
exit
```

Replay temporarily modifies the installed Realtek USB configuration to use the
capture's controller address, resets this USB device, restores the on-disk config
before transmitting three connectable one-second wake bursts, then resets back
to the adapter's original identity. No controller firmware is flashed. It writes
a privileged adapter configuration file and can interrupt every session on that
adapter; do not use it with another process owning the radio. Back up
`/lib/firmware/rtl_bt/rtl8761bu_config.bin` before the first run. Abrupt power loss
or termination can prevent cleanup; restore your backup and unplug/replug the
adapter if needed. Do not run on another adapter model without reviewing support.

The original Mac desktop shortcut additionally starts the VM, runs replay with a
local lock, restarts modified NXBT, waits for HTTP readiness and opens localhost.
Its personal filesystem paths and private capture are intentionally not shipped.
Physical Joy-Con re-pairing to another console may invalidate your capture.
Three bursts are intentional retries, not three separate shortcut launches.

Wake success has been user-confirmed, including a revised run after an earlier
docking-related regression. This does not guarantee repeated wake across every
sleep, docking or host-restart condition. See the evidence log and CREDITS.md.
