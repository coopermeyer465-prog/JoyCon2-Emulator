"""Bumble GATT peripheral for a single experimental right Joy-Con 2.

No firmware/calibration dumps are shipped. Unsupported initialization commands
are logged, not falsely acknowledged as successfully implemented.
"""

import asyncio
import logging

from bumble.device import Device, DeviceConfiguration
from bumble.gatt import Characteristic, CharacteristicValue, Descriptor, Service
from bumble.hci import Address, OwnAddressType
from bumble.transport import open_transport

from .pairing import PairingSession
from .protocol import Command, advertisement, right_report


LOG = logging.getLogger(__name__)
P = Characteristic.Properties
R = Characteristic.READABLE
W = Characteristic.WRITEABLE
RATE_DESCRIPTOR = "679d5510-5a24-4dee-9557-95df80486ecb"
UNKNOWN_DESCRIPTOR = "b746df8c-f358-495b-9cd2-e3bbeda4f979"


def install_services(device, on_command):
    def char(uuid, properties, value=b"", descriptor=None):
        result = Characteristic(uuid, properties, R | (W if properties & (P.WRITE | P.WRITE_WITHOUT_RESPONSE) else 0), value)
        if properties & P.NOTIFY:
            result.descriptors = [Descriptor("2902", R | W, device.gatt_server.make_descriptor_value(result))]
        if descriptor:
            result.descriptors = [*result.descriptors, Descriptor(descriptor, R | W, b"\x00\x00")]
        return result

    def writer(combined=False):
        return CharacteristicValue(write=lambda connection, data: on_command(connection, data, combined))

    config = Service("00c5af5d-1964-4e30-8f51-1956f96bd280", [
        char("00c5af5d-1964-4e30-8f51-1956f96bd281", P.READ, bytes.fromhex("04000500010100")),
        char("00c5af5d-1964-4e30-8f51-1956f96bd282", P.WRITE, CharacteristicValue(write=lambda *_: None)),
        char("00c5af5d-1964-4e30-8f51-1956f96bd283", P.READ, b"\x00"),
    ])
    common = char("ab7de9be-89fe-49ad-828f-118f09df7fd2", P.READ | P.NOTIFY, bytes(63), RATE_DESCRIPTOR)
    inputs = char("d5a9e01e-2ffc-4cca-b20c-8b67142bf442", P.READ | P.NOTIFY, right_report(), RATE_DESCRIPTOR)
    response = char("c765a961-d9d8-4d36-a20a-5315b111836a", P.NOTIFY, descriptor=UNKNOWN_DESCRIPTOR)
    response2 = char("640ca58e-0e88-410c-a7f3-426faf2b690b", P.NOTIFY, descriptor=UNKNOWN_DESCRIPTOR)
    main = Service("ab7de9be-89fe-49ad-828f-118f09df7fd0", [
        common, inputs,
        char("fa19b0fb-cd1f-46a7-84a1-bbb09e00c149", P.WRITE_WITHOUT_RESPONSE, CharacteristicValue(write=lambda *_: None)),
        char("649d4ac9-8eb7-4e6c-af44-1ea54fe5f005", P.WRITE_WITHOUT_RESPONSE, writer()),
        char("65a724b3-f1e7-4a61-8078-a342376b27ff", P.WRITE_WITHOUT_RESPONSE, writer(True)),
        # Firmware update is deliberately rejected rather than executed.
        char("4147423d-fdae-4df7-a4f7-d23e5df59f8d", P.WRITE_WITHOUT_RESPONSE,
             CharacteristicValue(write=lambda *_: LOG.warning("Firmware update not supported"))),
        response, response2,
        char("d3bd69d2-841c-4241-ab15-f86f406d2a80", P.NOTIFY, descriptor=UNKNOWN_DESCRIPTOR),
        char("ab7de9be-89fe-49ad-828f-118f09df7fde", P.READ | P.NOTIFY, bytes(1), RATE_DESCRIPTOR),
        char("ab7de9be-89fe-49ad-828f-118f09df7fdf", P.WRITE_WITHOUT_RESPONSE, CharacteristicValue(write=lambda *_: None)),
    ])
    gap = Service("1800", [char("2a00", P.READ, b"Joy-Con 2 (R)"), char("2a01", P.READ, b"\xc4\x03")])
    device.add_services([config, main, gap, Service("1801", [])])
    expected = [(config, 1), (main, 8), (common, 0xA), (inputs, 0xE),
                (response, 0x1A), (response2, 0x1E), (gap, 0x2B)]
    for attribute, handle in expected:
        if attribute.handle != handle:
            raise RuntimeError(f"GATT layout mismatch: {attribute.handle:04x} != {handle:04x}")
    return inputs, response


async def serve(address, transport, bond_file, seconds):
    async with await open_transport(transport) as hci:
        config = DeviceConfiguration()
        config.name = "Joy-Con 2 (R)"
        config.address = Address(address)
        config.gap_service_enabled = config.gatt_service_enabled = False
        config.classic_enabled = False
        device = Device.from_config_with_hci(config, hci.source, hci.sink)
        pairing = PairingSession(address)
        pending = set()

        async def process_command(connection, data, combined):
            try:
                request = Command.parse(data, combined)
                LOG.info("Command %02x/%02x (%d bytes)", request.command, request.subcommand, len(request.payload))
                if request.command != 0x15:
                    LOG.warning("Initialization command not implemented: %02x/%02x", request.command, request.subcommand)
                    return
                response = pairing.handle(request.subcommand, request.payload)
                if pairing.finalized:
                    pairing.save(bond_file)
                await device.notify_subscribers(response_characteristic, request.response(response))
            except (ValueError, NotImplementedError) as error:
                LOG.warning("Rejected command: %s", error)

        def on_command(connection, data, combined):
            task = asyncio.create_task(process_command(connection, data, combined))
            pending.add(task)
            task.add_done_callback(pending.discard)

        inputs, response_characteristic = install_services(device, on_command)

        async def provide_ltk(handle, rand, ediv):
            connection = device.lookup_connection(handle)
            if connection and pairing.finalized:
                peer = bytes(connection.peer_address)
                if peer in pairing.hosts:
                    return pairing.ltk
            return None

        device.host.long_term_key_provider = provide_ltk

        def connected(connection):
            LOG.info("BLE link established; console compatibility is NOT yet verified")
            connection.on("disconnection", lambda reason: LOG.info("Disconnected: %s", reason))

        device.on("connection", connected)
        await device.power_on()
        if bytes(device.public_address) != bytes(Address(address)):
            raise ValueError("--address must match this adapter's own public address; do not clone a Joy-Con")
        await device.start_advertising(own_address_type=OwnAddressType.PUBLIC,
                                       advertising_data=advertisement(), scan_response_data=b"",
                                       auto_restart=True)
        LOG.warning("LAB ONLY: advertising right Joy-Con 2 for %d seconds; playable initialization is incomplete", seconds)
        try:
            # Neutral reports only. External gamepad/WebHID input is a later milestone.
            for counter in range(seconds * 100):
                if pairing.finalized:
                    await device.notify_subscribers(inputs, right_report(counter))
                await asyncio.sleep(0.01)
        finally:
            await device.stop_advertising()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
