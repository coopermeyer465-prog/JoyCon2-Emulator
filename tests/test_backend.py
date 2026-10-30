import unittest

from bumble.device import Device, DeviceConfiguration

from joycon2_emulator.backend import install_services


class BackendTests(unittest.IsolatedAsyncioTestCase):
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
