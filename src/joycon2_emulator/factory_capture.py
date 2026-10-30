"""Read-only capture of four allowlisted factory blocks from an owned Joy-Con 2.

No SMP pairing, Nintendo pairing command, flash write, firmware update, key read
or generic arbitrary-address command is exposed by this tool.
"""

import asyncio
import json
import os
import struct

from bumble.core import UUID
from bumble.device import Device, DeviceConfiguration, Peer
from bumble.hci import Address, OwnAddressType
from bumble.transport import open_transport

from .memory import CALIBRATION_BASES


def read_request(base):
    if base not in CALIBRATION_BASES:
        raise ValueError("Factory address is not allowlisted")
    return bytes.fromhex("0291010400080000407e0000") + struct.pack("<I", base)


def read_response(packet, base):
    if (len(packet) != 80 or packet[:4] != bytes.fromhex("02010104")
            or packet[5] != 0x78 or packet[8:12] != b"\x40\x00\x00\x00"
            or int.from_bytes(packet[12:16], "little") != base):
        raise ValueError("Unexpected factory-read response")
    return packet[16:]


async def capture(peer_address, output, transport):
    if output.exists():
        raise ValueError("Output already exists; choose a new private filename")
    regions = {}
    async with await open_transport(transport) as hci:
        config = DeviceConfiguration()
        config.name = "JoyCon2 read-only factory reader"
        config.classic_enabled = False
        device = Device.from_config_with_hci(config, hci.source, hci.sink)
        await device.power_on()
        print("Connecting directly to the cycling Joy-Con; no pairing will be requested.", flush=True)
        connection = await asyncio.wait_for(
            device.connect(Address(peer_address, Address.PUBLIC_DEVICE_ADDRESS),
                           own_address_type=OwnAddressType.PUBLIC), 20)
        try:
            peer = Peer(connection)
            await peer.request_mtu(185)
            services = await peer.discover_service("ab7de9be-89fe-49ad-828f-118f09df7fd0")
            if len(services) != 1:
                raise ValueError("Joy-Con command service not found")
            characteristics = await peer.discover_characteristics(service=services[0])
            command = next(c for c in characteristics if c.uuid == UUID("649d4ac9-8eb7-4e6c-af44-1ea54fe5f005"))
            response = next(c for c in characteristics if c.uuid == UUID("c765a961-d9d8-4d36-a20a-5315b111836a"))
            replies = asyncio.Queue()
            await peer.subscribe(response, lambda packet: replies.put_nowait(bytes(packet)))
            for base in CALIBRATION_BASES:
                await peer.write_value(command, read_request(base), with_response=False)
                packet = await asyncio.wait_for(replies.get(), 5)
                regions[f"{base:06x}"] = read_response(packet, base).hex()
                print(f"Read 64 bytes at 0x{base:06x}; contents withheld from log.", flush=True)
        finally:
            try:
                await asyncio.wait_for(connection.disconnect(), 5)
            except Exception:
                pass
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"version": 1, "regions": regions}, stream)
    print("Saved 256 factory/calibration bytes privately; no pairing-key or firmware regions requested.", flush=True)
