import contextlib
import io
import unittest
from unittest.mock import AsyncMock, patch

from joycon2_emulator.cli import main


class CliTests(unittest.TestCase):
    def test_native_mouse_command_is_one_shot_not_a_stick_command(self):
        with patch("sys.argv", ["j2", "control", "mouse", "--dx", "-12", "--dy", "34"]), \
                patch("joycon2_emulator.control.send", new_callable=AsyncMock, return_value={"ok": True}) as send, \
                contextlib.redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(send.call_args.args[1], {"op": "mouse", "dx": -12, "dy": 34, "lifted": False})

    def test_serve_mouse_is_off_by_default_and_explicitly_opt_in(self):
        for extra, expected in (([], False), (["--experimental-mouse"], True)):
            with self.subTest(extra=extra), \
                    patch("sys.argv", ["j2", "serve", "--experimental", "--address", "00:11:22:33:44:55", *extra]), \
                    patch("joycon2_emulator.cli.platform.system", return_value="Linux"), \
                    patch("joycon2_emulator.backend.serve", new_callable=AsyncMock) as serve:
                main()
            self.assertEqual(serve.call_args.args[-1], expected)

    def test_mouse_raw_surface_is_forwarded(self):
        with patch("sys.argv", ["j2", "control", "mouse", "--dx", "5", "--surface", "50"]), \
                patch("joycon2_emulator.control.send", new_callable=AsyncMock, return_value={"ok": True}) as send, \
                contextlib.redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(send.call_args.args[1]["surface"], 50)
