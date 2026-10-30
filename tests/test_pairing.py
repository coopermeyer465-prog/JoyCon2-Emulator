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
            self.assertEqual(json.loads(path.read_text())["version"], 2)
            restored = PairingSession("02:00:00:00:00:01")
            restored.load(path)
            self.assertEqual(restored.host_keys, session.host_keys)
            with self.assertRaises(ValueError):
                PairingSession("02:00:00:00:00:02").load(path)
            session.handle(1, bytes.fromhex("0001554433221102"))
            self.assertIsNone(session.ltk)
            self.assertFalse(session.finalized)

    def test_direct_pairing_stages_before_commit(self):
        session = PairingSession("02:00:00:00:00:01")
        host = bytes.fromhex("554433221102")
        self.assertEqual(session.handle_direct(7, host + bytes(16)), b"")
        self.assertFalse(session.finalized)
        self.assertIsNone(session.ltk)
        self.assertEqual(session.handle_direct(9, b""), b"")
        self.assertTrue(session.finalized)
        self.assertEqual(session.hosts, [host])
        self.assertEqual(session.ltk, bytes(16))

    def test_direct_pairing_rejects_malformed_payload(self):
        session = PairingSession("02:00:00:00:00:01")
        with self.assertRaises(ValueError):
            session.handle_direct(9, b"")
        with self.assertRaises(ValueError):
            session.handle_direct(7, bytes(21))
        session.handle_direct(7, bytes(22))
        with self.assertRaises(ValueError):
            session.handle_direct(9, b"\x00")

    def test_separate_host_keys_are_committed_independently(self):
        session = PairingSession("02:00:00:00:00:01")
        first, second = bytes.fromhex("554433221102"), bytes.fromhex("544433221102")
        session.handle_direct(7, first + bytes([1]) * 16)
        session.handle_direct(7, second + bytes([2]) * 16)
        self.assertEqual(session.host_keys, {})
        session.handle_direct(9, b"")
        self.assertEqual(session.host_keys, {first: bytes([1]) * 16, second: bytes([2]) * 16})
        session.handle_direct(7, second + bytes([3]) * 16)
        self.assertEqual(session.host_keys[second], bytes([2]) * 16)
        session.handle_direct(9, b"")
        self.assertEqual(session.host_keys[first], bytes([1]) * 16)
        self.assertEqual(session.host_keys[second], bytes([3]) * 16)

    def test_load_legacy_bond(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bond.json"
            path.write_text(json.dumps({"version": 1, "hosts_le": ["554433221102"], "ltk_le": "11" * 16}))
            path.chmod(0o600)
            session = PairingSession("02:00:00:00:00:01")
            session.load(path)
            self.assertTrue(session.finalized)
            self.assertEqual(session.host_keys[bytes.fromhex("554433221102")], bytes([17]) * 16)

    def test_load_rejects_exposed_or_malformed_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bond.json"
            data = {"version": 1, "hosts_le": ["554433221102"], "ltk_le": "11" * 16}
            path.write_text(json.dumps(data))
            path.chmod(0o644)
            session = PairingSession("02:00:00:00:00:01")
            with self.assertRaises(ValueError):
                session.load(path)
            path.chmod(0o600)
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                session.load(link)
            data["ltk_le"] = "11"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                session.load(path)


if __name__ == "__main__":
    unittest.main()
