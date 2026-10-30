"""Bounded private input-report capture from an owned right Joy-Con 2.

Only runtime input/session configuration is sent. No SMP/Nintendo pairing, flash access,
firmware commands or controller-address cloning is exposed.
"""

import asyncio
import json
import os
import time

from bumble.core import UUID
from bumble.device import Device, DeviceConfiguration, Peer
from bumble.hci import Address, OwnAddressType
from bumble.transport import open_transport


MAX_FRAMES = 512


def feature_request(subcommand):
    if subcommand not in (2, 4, 5):
        raise ValueError("Only runtime sensor mask/enable/disable is allowed")
    # Match the demonstrated common-input session's runtime feature mask.
    # This enables reporting; no vibration/output, NFC or firmware command is sent.
    return bytes((0x0C, 0x91, 1, subcommand, 0, 4, 0, 0, 0xFF, 0, 0, 0))


def input_frame(kind, packet, elapsed):
    if kind not in ("common", "right") or len(packet) != 63:
        raise ValueError("Expected a 63-byte common/right input report")
    return {"kind": kind, "elapsed": round(elapsed, 6), "data": bytes(packet).hex()}


async def capture(peer_address, output, transport, seconds=5, report_kind="common", console_session=False,
                  random_address=False):
    if type(seconds) is not int or not 1 <= seconds <= 15:
        raise ValueError("Capture duration must be 1..15 seconds")
    if report_kind not in ("common", "right"):
        raise ValueError("Select one input format: common or right")
    if console_session and report_kind != "right":
        raise ValueError("Console session requires the right report format")
    if output.exists() or output.is_symlink():
        raise ValueError("Output exists; choose a new private filename")
    frames = []
    started = None
    seen_lengths = {"common": {}, "right": {}}

    def record(kind, packet):
        lengths = seen_lengths[kind]
        lengths[len(packet)] = lengths.get(len(packet), 0) + 1
        if started is not None and len(frames) < MAX_FRAMES:
            try:
                frames.append(input_frame(kind, packet, time.monotonic() - started))
            except ValueError:
                pass

    async with await open_transport(transport) as hci:
        config = DeviceConfiguration()
        config.name = "JoyCon2 private sensor reader"
        config.classic_enabled = False
        device = Device.from_config_with_hci(config, hci.source, hci.sink)
        await device.power_on()
        print("Connecting directly; no pairing or persistent controller writes requested.", flush=True)
        connection = await asyncio.wait_for(device.connect(
            Address(peer_address, Address.PUBLIC_DEVICE_ADDRESS),
            own_address_type=OwnAddressType.RANDOM if random_address else OwnAddressType.PUBLIC), 20)
        disconnected = asyncio.Event()
        disconnect_reason = None

        def on_disconnect(reason):
            nonlocal disconnect_reason
            disconnect_reason = reason
            disconnected.set()
            print(f"Sensor reader link disconnected (reason {reason}).", flush=True)

        connection.on("disconnection", on_disconnect)
        print(f"Sensor reader link established: {connection.parameters}", flush=True)
        peer = Peer(connection)
        command = None

        def request(subcommand):
            return (bytes(17) if console_session else b"") + feature_request(subcommand)

        try:
            await peer.request_mtu(185)
            print("Input report MTU negotiated; discovering sensor characteristics.", flush=True)
            services = await peer.discover_service("ab7de9be-89fe-49ad-828f-118f09df7fd0")
            if len(services) != 1:
                raise ValueError("Joy-Con input service not found")
            chars = await peer.discover_characteristics(service=services[0])

            def characteristic(uuid):
                return next(c for c in chars if c.uuid == UUID(uuid))

            command = characteristic("649d4ac9-8eb7-4e6c-af44-1ea54fe5f005")
            if console_session:
                command = characteristic("65a724b3-f1e7-4a61-8078-a342376b27ff")
                config_services = await peer.discover_service("00c5af5d-1964-4e30-8f51-1956f96bd280")
                if len(config_services) != 1:
                    raise ValueError("Console session service not found")
                config_chars = await peer.discover_characteristics(service=config_services[0])
                session = next(c for c in config_chars if c.uuid == UUID("00c5af5d-1964-4e30-8f51-1956f96bd282"))
                await peer.write_value(session, b"\x01\x00", with_response=True)
            response = characteristic("c765a961-d9d8-4d36-a20a-5315b111836a")
            replies = asyncio.Queue(maxsize=16)

            def reply(packet):
                if not replies.full():
                    replies.put_nowait(bytes(packet))

            await peer.subscribe(response, reply)
            if console_session:
                # Documented first initialization query; no persistent state.
                await peer.write_value(command, bytes(17) + bytes.fromhex("0791010100000000"), with_response=False)
                packet = await asyncio.wait_for(replies.get(), 5)
                if len(packet) < 8 or packet[:4] != bytes((7, 1, 1, 1)) or packet[5] != 0x78:
                    raise ValueError("Unexpected initial status response")
            report_uuid = {"common": "ab7de9be-89fe-49ad-828f-118f09df7fd2",
                           "right": "d5a9e01e-2ffc-4cca-b20c-8b67142bf442"}[report_kind]
            reports = {report_kind: characteristic(report_uuid)}
            started = time.monotonic()
            if not console_session:
                for kind, report in reports.items():
                    await peer.subscribe(report, lambda packet, kind=kind: record(kind, packet))
            for subcommand in (2, 4):
                # CommonSession in JoeGeC/joycon2android documents this init gap.
                await asyncio.sleep(0.5)
                await peer.write_value(command, request(subcommand), with_response=False)
                packet = await asyncio.wait_for(replies.get(), 5)
                if len(packet) < 8 or packet[:4] != bytes((0x0C, 1, 1, subcommand)) or packet[5] != 0x78:
                    raise ValueError("Unexpected feature response; capture stopped")
            if console_session:
                for kind, report in reports.items():
                    descriptors = await peer.discover_descriptors(characteristic=report)
                    rate = next(d for d in descriptors if d.type == UUID("679d5510-5a24-4dee-9557-95df80486ecb"))
                    await peer.write_value(rate, b"\x85\x00", with_response=True)
                    await peer.subscribe(report, lambda packet, kind=kind: record(kind, packet))
            for kind, report in reports.items():
                try:
                    packet = await asyncio.wait_for(peer.read_value(report), 2)
                    record(kind, packet)
                except Exception as error:
                    print(f"{kind} input read unavailable ({type(error).__name__}); awaiting notifications.", flush=True)
            print(f"Recording sensor input for {seconds} seconds (maximum {MAX_FRAMES} frames).", flush=True)
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            if disconnected.is_set():
                raise ConnectionError(f"Joy-Con disconnected during sensor setup (reason {disconnect_reason})") from None
            raise
        finally:
            if command is not None and not disconnected.is_set():
                try:
                    await asyncio.wait_for(peer.write_value(command, request(5), with_response=False), 2)
                except Exception:
                    pass
            if not disconnected.is_set():
                try:
                    await asyncio.wait_for(connection.disconnect(), 5)
                except Exception:
                    pass
    if not frames:
        print(f"Observed input packet lengths (no contents): {seen_lengths}", flush=True)
        raise ValueError("No valid input reports received; no capture written")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"version": 1, "frames": frames}, stream)
    print(f"Saved {len(frames)} input reports privately; no addresses, keys or flash regions requested.", flush=True)
