"""Bumble GATT peripheral for a single experimental right Joy-Con 2.

No firmware/calibration dumps are shipped. Unsupported initialization commands
are logged, not falsely acknowledged as successfully implemented.
"""

import asyncio
import logging
import time

from bumble.device import Device, DeviceConfiguration
from bumble.gatt import Characteristic, CharacteristicValue, Descriptor, Service
from bumble.hci import Address, OwnAddressType
from bumble.transport import open_transport

from .controller import Controller
from .protocol import Command, advertisement, right_report
from .input_test import ButtonPulse
from .control import InputState, ControlServer


LOG = logging.getLogger(__name__)
P = Characteristic.Properties
R = Characteristic.READABLE
W = Characteristic.WRITEABLE
RATE_DESCRIPTOR = "679d5510-5a24-4dee-9557-95df80486ecb"
UNKNOWN_DESCRIPTOR = "b746df8c-f358-495b-9cd2-e3bbeda4f979"


async def notify_input(device, connection, characteristic, report):
    queue = device.host.get_data_packet_queue(connection.handle)
    if queue is None:
        raise RuntimeError("No transmit queue for input connection")
    await device.notify_subscribers(characteristic, report)
    # Notification submission alone does not wait for HCI packet completion.
    await queue.drain(connection.handle)


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


async def serve(address, transport, bond_file, seconds, calibration=None, test_button=None, control_socket=None,
                auto_join=False, experimental_mouse=False):
    async with await open_transport(transport) as hci:
        config = DeviceConfiguration()
        config.name = "Joy-Con 2 (R)"
        config.address = Address(address)
        config.gap_service_enabled = config.gatt_service_enabled = False
        config.classic_enabled = False
        device = Device.from_config_with_hci(config, hci.source, hci.sink)
        controller = Controller(address, mouse=experimental_mouse)
        if calibration is not None:
            controller.memory.load_calibration(calibration)
        pairing = controller.pairing
        if bond_file.exists():
            pairing.load(bond_file)
            LOG.info("Loaded private bond state (keys redacted)")
        pending = set()
        state = InputState()
        state.mouse_supported = experimental_mouse
        active_connection = None

        async def process_command(connection, data, combined):
            try:
                request = Command.parse(data, combined)
                LOG.info("Command %02x/%02x (%d bytes)", request.command, request.subcommand, len(request.payload))
                if (request.command, request.subcommand) == (2, 4) and len(request.payload) == 8:
                    LOG.info("Memory read: offset=0x%08x length=%d (no memory contents logged)",
                             int.from_bytes(request.payload[4:8], "little"), request.payload[0])
                response = controller.handle(request)
                if request.command == 0x0C:
                    state.mouse_enabled = bool(controller.features.enabled & 0x10)
                    if not state.mouse_enabled:
                        state.pending_mouse = None
                    LOG.info("Implemented input features enabled: 0x%02x", controller.features.enabled)
                if pairing.finalized and (request.command, request.subcommand) in ((0x15, 3), (3, 9)):
                    pairing.save(bond_file)
                await device.notify_subscribers(response_characteristic, request.response(response))
            except (ValueError, NotImplementedError) as error:
                LOG.warning("Rejected command: %s", error)

        def on_command(connection, data, combined):
            task = asyncio.create_task(process_command(connection, data, combined))
            pending.add(task)
            task.add_done_callback(command_done)

        def command_done(task):
            pending.discard(task)
            if not task.cancelled() and (error := task.exception()) is not None:
                LOG.error("Command task failed (%s); payload redacted", type(error).__name__)

        inputs, response_characteristic = install_services(device, on_command)
        center_x, center_y = controller.memory.primary_center()
        inputs.value = right_report(x=center_x, y=center_y)

        async def provide_ltk(handle, rand, ediv):
            connection = device.lookup_connection(handle)
            if connection and pairing.finalized:
                peer = bytes(connection.peer_address)
                if peer in pairing.hosts:
                    return pairing.host_keys.get(peer)
            return None

        device.host.long_term_key_provider = provide_ltk

        def connected(connection):
            nonlocal active_connection
            active_connection = connection
            state.connected = True
            LOG.info("BLE link established; console compatibility is NOT yet verified")
            LOG.info("Connection parameters: %s", connection.parameters)
            connection.on("connection_parameters_update",
                          lambda: LOG.info("Connection parameters updated: %s", connection.parameters))
            connection.on("connection_encryption_change",
                          lambda: LOG.info("Link encryption active: %s", connection.is_encrypted))
            def disconnected(reason):
                nonlocal active_connection
                if active_connection is connection:
                    active_connection = None
                    state.connected = state.ready = False
                    state.registering = False
                    state.release()
                LOG.info("Disconnected: %s; queued input released", reason)
            connection.on("disconnection", disconnected)

        device.on("connection", connected)
        await device.power_on()
        if bytes(device.public_address) != bytes(Address(address)):
            raise ValueError("--address must match this adapter's own public address; do not clone a Joy-Con")
        host_address = (":".join(f"{byte:02X}" for byte in pairing.hosts[0][::-1])
                        if pairing.finalized else None)
        await device.start_advertising(own_address_type=OwnAddressType.PUBLIC,
                                       advertising_data=advertisement(host=host_address), scan_response_data=b"",
                                       auto_restart=True)
        LOG.warning("EXPERIMENTAL: right Joy-Con 2; duration=%s", seconds or "until stopped")
        server = ControlServer(control_socket, state) if control_socket else None
        if server:
            await server.start()
            LOG.info("Private local command socket ready")
        try:
            # No input unless explicitly queued through the socket or test pulse.
            queued_reports = 0
            stream_start = None
            pulse = ButtonPulse(test_button) if test_button else None
            pulse_sent = False
            last_input = ((), 0.0, 0.0)
            active_reports = 0
            joined_connection = None
            join_until = 0
            join_pressed = False
            counter = 0
            deadline = time.monotonic() + seconds if seconds else float("inf")
            while time.monotonic() < deadline and not state.stopping:
                subscribed = any(values.get(inputs.handle, b"\x00\x00")[0] & 1
                                 for values in device.gatt_server.subscribers.values())
                was_ready = state.ready
                state.ready = bool(pairing.finalized and controller.features.enabled and subscribed
                                   and active_connection and active_connection.is_encrypted)
                if was_ready and not state.ready:
                    state.release()
                    state.registering = False
                if state.ready:
                    if auto_join and active_connection is not joined_connection:
                        joined_connection = active_connection
                        state.registering = True
                        join_until = time.monotonic() + 2.25
                        join_pressed = False
                        LOG.info("Automatic SL+SR scheduled after two-second initialization grace")
                    if state.registering and time.monotonic() >= join_until:
                        state.registering = False
                        state.release()
                        LOG.info("Automatic SL+SR released; console registration requires confirmation")
                    if queued_reports == 0:
                        stream_start = time.monotonic()
                        LOG.info("Subscribed right-report stream enabled")
                    buttons, x, y = state.snapshot(time.monotonic())
                    if state.registering:
                        pressing = time.monotonic() >= join_until - 0.25
                        if pressing and not join_pressed:
                            join_pressed = True
                            LOG.info("Automatic SL+SR registration pulse started")
                        buttons, x, y = (("SL", "SR") if pressing else ()), 0.0, 0.0
                    if pulse:
                        buttons = pulse.at(time.monotonic() - stream_start)
                    if pulse and buttons and not pulse_sent:
                        pulse_sent = True
                        LOG.info("Sending opt-in %s test pulse for %d ms", test_button, pulse.duration_ms)
                    raw_x, raw_y = controller.memory.logical_stick(x, y)
                    mouse = state.take_mouse(time.monotonic())
                    await asyncio.wait_for(notify_input(device, active_connection,
                        inputs, right_report(counter, buttons, x=raw_x, y=raw_y, mouse=mouse)), 2)
                    current_input = (buttons, x, y)
                    if current_input != last_input:
                        LOG.info("Input transition queued: generation=%d buttons=%s x=%.3f y=%.3f; "
                                 "previous state queued for %d reports (not a console acknowledgement)",
                                 state.generation, ",".join(buttons) or "neutral", x, y, active_reports)
                        last_input = current_input
                        active_reports = 0
                    active_reports += 1
                    queued_reports += 1
                counter += 1
                await asyncio.sleep(0.01)
            LOG.info("Queued %d reports; console input effects require user confirmation", queued_reports)
        finally:
            state.release()
            if state.ready:
                try:
                    await asyncio.wait_for(notify_input(device, active_connection,
                        inputs, right_report(counter, x=center_x, y=center_y,
                                             mouse=(0, 0, 255) if state.mouse_enabled else None)), 1)
                    await asyncio.sleep(0.1)
                except Exception:
                    LOG.warning("Final neutral report unavailable; closing BLE transport")
            if server:
                await server.close()
            await device.stop_advertising()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
