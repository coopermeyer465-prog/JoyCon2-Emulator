import json
import os
from pathlib import Path
import tempfile
import unittest

from joycon2_emulator.pairing import PairingSession


class PairingTests(unittest.TestCase):
    def session(self):
        session = PairingSession("02:00:00:00:00:01")
        response = session.handle(1, bytes.fromhex("0002554433221102574433221102"))
        self.assertEqual(response, bytes.fromhex("010401010000000002"))
        return session

    def test_published_challenge_vector(self):
        session = self.session()
        session.handle(4, b"\x00" + bytes.fromhex("3503e92982877124bea80c664615834b"))
        response = session.handle(2, b"\x00" + bytes.fromhex("6fc6df8ad8fedf15bb8c15e91f320544"))
        self.assertEqual(response.hex(), "01134c97f511b9b6dd4d86fd40f536e9ed")
        self.assertEqual(session.handle(3, b"\x00"), b"\x01")

    def test_ordering_and_lengths(self):
        session = PairingSession("02:00:00:00:00:01")
        for subcommand, payload in ((4, bytes(17)), (2, bytes(17)), (3, b"\x00"), (1, b"\x00\x02")):
            with self.subTest(subcommand=subcommand), self.assertRaises(ValueError):
                session.handle(subcommand, payload)
        with self.assertRaises(NotImplementedError):
            session.handle(255, b"")

    def test_bond_permissions_and_state(self):
        session = self.session()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bond.json"
            with self.assertRaises(ValueError):
                session.save(path)
            session.handle(4, bytes(17))
            session.handle(2, bytes(17))
            session.handle(3, b"\x00")
            session.save(path)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())["version"], 1)
            session.handle(1, bytes.fromhex("0001554433221102"))
            self.assertIsNone(session.ltk)
            self.assertFalse(session.finalized)


if __name__ == "__main__":
    unittest.main()
