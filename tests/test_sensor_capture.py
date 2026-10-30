from contextlib import redirect_stdout
import asyncio
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bumble.core import UUID
from bumble.gatt_client import DescriptorProxy
from bumble.hci import OwnAddressType

from joycon2_emulator.sensor_capture import capture, feature_request, input_frame


class SensorCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_mocked_capture_only_sends_runtime_commands_and_saves_private_reports(self):
        await self.capture_case(False)

    async def test_console_session_uses_fixed_session_rate_and_zero_output_prefix(self):
        await self.capture_case(True)

    async def test_report_storage_is_bounded_when_notifications_flood(self):
        await self.capture_case(False, burst=True)

    async def test_random_central_address_does_not_change_feature_commands(self):
        await self.capture_case(False, random_address=True)

    async def capture_case(self, console_session, burst=False, random_address=False):
        callbacks = {}
        chars = [SimpleNamespace(uuid=UUID(uuid)) for uuid in (
            "649d4ac9-8eb7-4e6c-af44-1ea54fe5f005",
            "c765a961-d9d8-4d36-a20a-5315b111836a",
            "ab7de9be-89fe-49ad-828f-118f09df7fd2",
            "d5a9e01e-2ffc-4cca-b20c-8b67142bf442",
            "65a724b3-f1e7-4a61-8078-a342376b27ff")]
        session = SimpleNamespace(uuid=UUID("00c5af5d-1964-4e30-8f51-1956f96bd282"))
        rate = DescriptorProxy(None, 0x10, UUID("679d5510-5a24-4dee-9557-95df80486ecb"))
        main_service, config_service = object(), object()
        sent = []
        runtime_setup = []

        async def subscribe(characteristic, callback):
            callbacks[characteristic.uuid] = callback

        async def write(characteristic, data, with_response):
            if characteristic is session or characteristic is rate:
                self.assertTrue(console_session)
                self.assertTrue(with_response)
                runtime_setup.append((characteristic, data))
                return
            self.assertIs(characteristic, chars[4] if console_session else chars[0])
            self.assertFalse(with_response)
            sent.append(data)
            if console_session:
                self.assertEqual(data[:17], bytes(17))
                data = data[17:]
            callbacks[chars[1].uuid](bytes((data[0], 1, 1, data[3], 16, 0x78, 0, 0)) + bytes(4))

        async def sample(seconds):
            if seconds == 0.5:
                return
            self.assertEqual(seconds, 1)
            for _ in range(600 if burst else 1):
                callbacks[chars[3 if console_session else 2].uuid](bytes(63))
            self.assertNotIn(chars[2 if console_session else 3].uuid, callbacks)

        connection = SimpleNamespace(disconnect=AsyncMock(), on=Mock(), parameters="mock parameters")
        device = SimpleNamespace(power_on=AsyncMock(), connect=AsyncMock(return_value=connection))
        peer = SimpleNamespace(request_mtu=AsyncMock(), discover_service=AsyncMock(side_effect=lambda uuid: [
                                   config_service if uuid.startswith("00c5") else main_service]),
                               discover_characteristics=AsyncMock(side_effect=lambda service: chars if service is main_service else [session]),
                               discover_descriptors=AsyncMock(return_value=[rate]),
                               read_value=AsyncMock(side_effect=ValueError("not readable")),
                               subscribe=AsyncMock(side_effect=subscribe), write_value=AsyncMock(side_effect=write))
        hci = SimpleNamespace(source=object(), sink=object())
        context = Mock(__aenter__=AsyncMock(return_value=hci), __aexit__=AsyncMock(return_value=False))
        with tempfile.TemporaryDirectory() as directory, \
                patch("joycon2_emulator.sensor_capture.open_transport", new_callable=AsyncMock, return_value=context), \
                patch("joycon2_emulator.sensor_capture.Device.from_config_with_hci", return_value=device), \
                patch("joycon2_emulator.sensor_capture.Peer", return_value=peer), \
                patch("joycon2_emulator.sensor_capture.asyncio.sleep", side_effect=sample), \
                redirect_stdout(io.StringIO()):
            output = Path(directory) / "private" / "sensors.json"
            kind = "right" if console_session else "common"
            await capture("00:11:22:33:44:55", output, "mock", 1, kind, console_session, random_address)
            result = json.loads(output.read_text())
            self.assertEqual(result["version"], 1)
            self.assertEqual([frame["kind"] for frame in result["frames"]], [kind] * (512 if burst else 1))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(output.parent.stat().st_mode & 0o777, 0o700)
        prefix = bytes(17) if console_session else b""
        expected = [prefix + feature_request(subcommand) for subcommand in (2, 4, 5)]
        if console_session:
            expected.insert(0, prefix + bytes.fromhex("0791010100000000"))
        self.assertEqual(sent, expected)
        self.assertEqual(runtime_setup, [(session, b"\x01\x00"), (rate, b"\x85\x00")] if console_session else [])
        connection.disconnect.assert_awaited_once()
        self.assertEqual(device.connect.call_args.kwargs["own_address_type"],
                         OwnAddressType.RANDOM if random_address else OwnAddressType.PUBLIC)

    async def test_disconnected_gatt_cancellation_reports_reason_and_skips_double_disconnect(self):
        events = {}
        connection = SimpleNamespace(disconnect=AsyncMock(), parameters="mock", on=lambda name, callback: events.update({name: callback}))

        async def dropped(_):
            events["disconnection"](19)
            raise asyncio.CancelledError()

        device = SimpleNamespace(power_on=AsyncMock(), connect=AsyncMock(return_value=connection))
        peer = SimpleNamespace(request_mtu=AsyncMock(side_effect=dropped))
        context = Mock(__aenter__=AsyncMock(return_value=SimpleNamespace(source=None, sink=None)),
                       __aexit__=AsyncMock(return_value=False))
        with tempfile.TemporaryDirectory() as directory, \
                patch("joycon2_emulator.sensor_capture.open_transport", new_callable=AsyncMock, return_value=context), \
                patch("joycon2_emulator.sensor_capture.Device.from_config_with_hci", return_value=device), \
                patch("joycon2_emulator.sensor_capture.Peer", return_value=peer), \
                redirect_stdout(io.StringIO()):
            output = Path(directory) / "sensors.json"
            with self.assertRaisesRegex(ConnectionError, "reason 19"):
                await capture("00:11:22:33:44:55", output, "mock")
            self.assertFalse(output.exists())
        connection.disconnect.assert_not_awaited()

    def test_only_fixed_runtime_feature_commands(self):
        for subcommand in (2, 4, 5):
            self.assertEqual(feature_request(subcommand),
                             bytes((0x0C, 0x91, 1, subcommand, 0, 4, 0, 0, 0xFF, 0, 0, 0)))
        for subcommand in (0, 1, 3, 6, 0x0D):
            with self.assertRaises(ValueError):
                feature_request(subcommand)

    def test_input_report_allowlist_and_no_device_identity(self):
        for kind in ("common", "right"):
            frame = input_frame(kind, bytes(63), 1.23456789)
            self.assertEqual(set(frame), {"kind", "elapsed", "data"})
            self.assertEqual(frame["elapsed"], 1.234568)
            self.assertEqual(len(bytes.fromhex(frame["data"])), 63)
        for kind, packet in (("command", bytes(63)), ("right", bytes(62)), ("common", bytes(64))):
            with self.assertRaises(ValueError):
                input_frame(kind, packet, 0)

    async def test_rejects_duration_existing_file_or_symlink_before_radio_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture.json"
            for seconds in (0, 16, True, 1.5):
                with self.assertRaises(ValueError):
                    await capture("unused", output, "unused", seconds)
            with self.assertRaises(ValueError):
                await capture("unused", output, "unused", report_kind="unknown")
            with self.assertRaises(ValueError):
                await capture("unused", output, "unused", console_session=True)
            output.write_text("preserve")
            with self.assertRaises(ValueError):
                await capture("unused", output, "unused")
            self.assertEqual(output.read_text(), "preserve")
            link = Path(directory) / "link.json"
            link.symlink_to(Path(directory) / "missing")
            with self.assertRaises(ValueError):
                await capture("unused", link, "unused")
