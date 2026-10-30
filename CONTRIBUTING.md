# Contributing

Run `python -m unittest discover -s tests -v` before submitting changes.
Separate simulator/unit-test results from physical-console results. Include a
small reproducible procedure and relevant versions for hardware claims.

Never commit pairing keys, personal Bluetooth addresses, captures, Nintendo
firmware/flash dumps, Wi-Fi credentials, virtual-machine images, or authentication
tokens. Redact addresses and command payloads from issue logs. The lab logs only
command identifiers and lengths, not pairing payloads.

Protocol work should cite its primary source and test byte order, truncated
packets, state transitions and failure recovery. Preserve upstream notices and
licenses when adapting source. Unknown commands should fail explicitly.

This project is GPL-3.0-only. Contributions are accepted under that license.
