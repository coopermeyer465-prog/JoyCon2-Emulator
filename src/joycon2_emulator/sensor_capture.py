"""Bounded private input-report capture from an owned right Joy-Con 2.

Only runtime feature selection is sent. No SMP/Nintendo pairing, flash access,
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
    # Buttons, stick, IMU and optical mouse; no rumble/NFC/firmware access.
    return bytes((0x0C, 0x91, 1, subcommand, 0, 4, 0, 0, 0x17, 0, 0, 0))


def input_frame(kind, packet, elapsed):
    if kind not in ("common", "right") or len(packet) != 63:
        raise ValueError("Expected a 63-byte common/right input report")
    return {"kind": kind, "elapsed": round(elapsed, 6), "data": bytes(packet).hex()}


async def capture(peer_address, output, transport, seconds=5):
    if type(seconds) is not int or not 1 <= seconds <= 15:
        raise ValueError("Capture duration must be 1..15 seconds")
    if output.exists() or output.is_symlink():
        raise ValueError("Output exists; choose a new private filename")
    frames = []
    started = None

    def record(kind, packet):
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
            Address(peer_address, Address.PUBLIC_DEVICE_ADDRESS), own_address_type=OwnAddressType.PUBLIC), 20)
        peer = Peer(connection)
        command = None
        try:
            await peer.request_mtu(185)
            services = await peer.discover_service("ab7de9be-89fe-49ad-828f-118f09df7fd0")
            if len(services) != 1:
                raise ValueError("Joy-Con input service not found")
            chars = await peer.discover_characteristics(service=services[0])

            def characteristic(uuid):
                return next(c for c in chars if c.uuid == UUID(uuid))

            command = characteristic("649d4ac9-8eb7-4e6c-af44-1ea54fe5f005")
            response = characteristic("c765a961-d9d8-4d36-a20a-5315b111836a")
            replies = asyncio.Queue(maxsize=16)

            def reply(packet):
                if not replies.full():
                    replies.put_nowait(bytes(packet))

            await peer.subscribe(response, reply)
            await peer.subscribe(characteristic("ab7de9be-89fe-49ad-828f-118f09df7fd2"),
                                 lambda packet: record("common", packet))
            await peer.subscribe(characteristic("d5a9e01e-2ffc-4cca-b20c-8b67142bf442"),
                                 lambda packet: record("right", packet))
            for subcommand in (2, 4):
                await peer.write_value(command, feature_request(subcommand), with_response=False)
                packet = await asyncio.wait_for(replies.get(), 5)
                if len(packet) < 8 or packet[:4] != bytes((0x0C, 1, 1, subcommand)) or packet[5] != 0x78:
                    raise ValueError("Unexpected feature response; capture stopped")
            started = time.monotonic()
            print(f"Recording sensor input for {seconds} seconds (maximum {MAX_FRAMES} frames).", flush=True)
            await asyncio.sleep(seconds)
        finally:
            if command is not None:
                try:
                    await asyncio.wait_for(peer.write_value(command, feature_request(5), with_response=False), 2)
                except Exception:
                    pass
            try:
                await asyncio.wait_for(connection.disconnect(), 5)
            except Exception:
                pass
    if not frames:
        raise ValueError("No valid input reports received; no capture written")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"version": 1, "frames": frames}, stream)
    print(f"Saved {len(frames)} input reports privately; no addresses, keys or flash regions requested.", flush=True)
