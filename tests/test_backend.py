import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from bumble.device import Device, DeviceConfiguration

from joycon2_emulator.backend import install_services, notify_input


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_input_waits_for_adapter_completion(self):
        drained = asyncio.Event()
        queue = SimpleNamespace()

        async def drain(handle):
            self.assertEqual(handle, 7)
            await drained.wait()

        queue.drain = AsyncMock(side_effect=drain)
        device = SimpleNamespace(
            host=SimpleNamespace(get_data_packet_queue=Mock(return_value=queue)),
            notify_subscribers=AsyncMock())
        task = asyncio.create_task(notify_input(device, SimpleNamespace(handle=7), "input", b"report"))
        await asyncio.sleep(0)
        device.notify_subscribers.assert_awaited_once_with("input", b"report")
        self.assertFalse(task.done())
        drained.set()
        await task

    async def test_input_refuses_missing_transmit_queue(self):
        device = SimpleNamespace(
            host=SimpleNamespace(get_data_packet_queue=Mock(return_value=None)),
            notify_subscribers=AsyncMock())
        with self.assertRaises(RuntimeError):
            await notify_input(device, SimpleNamespace(handle=7), "input", b"report")
        device.notify_subscribers.assert_not_awaited()

    async def test_exact_gatt_handles(self):
        config = DeviceConfiguration()
        config.gap_service_enabled = config.gatt_service_enabled = False
        device = Device(config=config)
        inputs, response = install_services(device, lambda *_: None)
        self.assertEqual(inputs.handle, 0xE)
        self.assertEqual(response.handle, 0x1A)
        self.assertEqual([a.handle for a in device.gatt_server.attributes], list(range(1, 0x31)))
        self.assertEqual(device.gatt_server.attributes[-1].handle, 0x30)


if __name__ == "__main__":
    unittest.main()
