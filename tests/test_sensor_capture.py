from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bumble.core import UUID

from joycon2_emulator.sensor_capture import capture, feature_request, input_frame


class SensorCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_mocked_capture_only_sends_runtime_commands_and_saves_private_reports(self):
        callbacks = {}
        chars = [SimpleNamespace(uuid=UUID(uuid)) for uuid in (
            "649d4ac9-8eb7-4e6c-af44-1ea54fe5f005",
            "c765a961-d9d8-4d36-a20a-5315b111836a",
            "ab7de9be-89fe-49ad-828f-118f09df7fd2",
            "d5a9e01e-2ffc-4cca-b20c-8b67142bf442")]
        sent = []

        async def subscribe(characteristic, callback):
            callbacks[characteristic.uuid] = callback

        async def write(characteristic, data, with_response):
            self.assertIs(characteristic, chars[0])
            self.assertFalse(with_response)
            sent.append(data)
            callbacks[chars[1].uuid](bytes((12, 1, 1, data[3], 16, 0x78, 0, 0)) + bytes(4))

        async def sample(seconds):
            self.assertEqual(seconds, 1)
            callbacks[chars[2].uuid](bytes(63))
            callbacks[chars[3].uuid](bytes(63))

        connection = SimpleNamespace(disconnect=AsyncMock())
        device = SimpleNamespace(power_on=AsyncMock(), connect=AsyncMock(return_value=connection))
        peer = SimpleNamespace(request_mtu=AsyncMock(), discover_service=AsyncMock(return_value=[object()]),
                               discover_characteristics=AsyncMock(return_value=chars),
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
            await capture("00:11:22:33:44:55", output, "mock", 1)
            result = json.loads(output.read_text())
            self.assertEqual(result["version"], 1)
            self.assertEqual([frame["kind"] for frame in result["frames"]], ["common", "right"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(output.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(sent, [feature_request(subcommand) for subcommand in (2, 4, 5)])
        connection.disconnect.assert_awaited_once()

    def test_only_fixed_runtime_feature_commands(self):
        for subcommand in (2, 4, 5):
            self.assertEqual(feature_request(subcommand),
                             bytes((0x0C, 0x91, 1, subcommand, 0, 4, 0, 0, 0x17, 0, 0, 0)))
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
            output.write_text("preserve")
            with self.assertRaises(ValueError):
                await capture("unused", output, "unused")
            self.assertEqual(output.read_text(), "preserve")
            link = Path(directory) / "link.json"
            link.symlink_to(Path(directory) / "missing")
            with self.assertRaises(ValueError):
                await capture("unused", link, "unused")
