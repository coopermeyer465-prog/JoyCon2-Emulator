"""Nintendo command 0x15 exchange, separate from standard Bluetooth SMP."""

import json
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .protocol import address_bytes


CONTROLLER_KEY = bytes.fromhex("5cf6ee792cdf05e1ba2b6325c41a5f10")


class PairingSession:
    def __init__(self, controller_address):
        self.controller_address = address_bytes(controller_address)
        self.hosts = []
        self.ltk = None
        self.confirmed = False
        self.finalized = False
        self.pending_direct = []
        self.host_keys = {}

    def handle_direct(self, subcommand, payload):
        if subcommand == 7:
            if len(payload) != 22:
                raise ValueError("Expected a host address and 16-byte LTK")
            host, key = payload[:6], payload[6:]
            entries = [(address, ltk) for address, ltk in self.pending_direct if address != host]
            if len(entries) == 2:
                raise ValueError("At most two pending host entries are supported")
            self.pending_direct = [*entries, (host, key)]
            return b""
        if subcommand == 9:
            if payload or not self.pending_direct:
                raise ValueError("Expected staged pairing information and empty commit payload")
            hosts = list(self.hosts) if self.finalized else []
            for host, _ in self.pending_direct:
                if host not in hosts:
                    hosts.append(host)
            if len(hosts) > 2:
                raise NotImplementedError("More than two host entries are unsupported")
            self.hosts = hosts
            keys = dict(self.host_keys) if self.finalized else {}
            keys.update(self.pending_direct)
            self.host_keys = keys
            self.ltk = keys[hosts[0]]
            self.confirmed = self.finalized = True
            self.pending_direct = []
            return b""
        raise NotImplementedError("Unsupported direct pairing subcommand")

    def handle(self, subcommand, payload):
        if subcommand == 1:
            if payload:
                if len(payload) < 2 or payload[0] != 0 or not 1 <= payload[1] <= 2:
                    raise ValueError("Invalid host address exchange")
                if len(payload) != 2 + payload[1] * 6:
                    raise ValueError("Truncated host addresses")
                self.hosts = [payload[i:i + 6] for i in range(2, len(payload), 6)]
                self.ltk = None
                self.confirmed = self.finalized = False
                self.pending_direct = []
                self.host_keys = {}
            return b"\x01\x04\x01" + self.controller_address
        if subcommand == 4:
            self._block(payload)
            if not self.hosts:
                raise ValueError("Exchange host addresses before keys")
            self.ltk = bytes(a ^ b for a, b in zip(payload[1:], CONTROLLER_KEY))
            self.confirmed = self.finalized = False
            return b"\x01" + CONTROLLER_KEY
        if subcommand == 2:
            self._block(payload)
            if self.ltk is None:
                raise ValueError("Exchange keys before confirming")
            cipher = Cipher(algorithms.AES(self.ltk[::-1]), modes.ECB()).encryptor()
            result = cipher.update(payload[1:][::-1]) + cipher.finalize()
            self.confirmed = True
            return b"\x01" + result
        if subcommand == 3:
            if payload != b"\x00" or not self.confirmed:
                raise ValueError("Confirm the challenge before finalizing")
            self.finalized = True
            self.host_keys = dict.fromkeys(self.hosts, self.ltk)
            return b"\x01"
        raise NotImplementedError(f"Pairing subcommand {subcommand:02x}")

    @staticmethod
    def _block(payload):
        if len(payload) != 17 or payload[0] != 0:
            raise ValueError("Expected a 16-byte key/challenge with zero prefix")

    def save(self, path):
        if not self.finalized:
            raise ValueError("Pairing is not finalized")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".bond-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"version": 2, "controller_le": self.controller_address.hex(),
                           "hosts_le": [host.hex() for host in self.hosts],
                           "keys_le": {host.hex(): key.hex() for host, key in self.host_keys.items()}}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, path):
        path = Path(path)
        if path.is_symlink() or path.stat().st_mode & 0o077 or path.stat().st_size > 4096:
            raise ValueError("Bond file must be small, owner-only and not a symlink")
        data = json.loads(path.read_text())
        if data.get("version") not in (1, 2):
            raise ValueError("Unsupported bond version")
        hosts = [bytes.fromhex(host) for host in data["hosts_le"]]
        if not 1 <= len(hosts) <= 2 or len(set(hosts)) != len(hosts) or any(len(host) != 6 for host in hosts):
            raise ValueError("Invalid stored host addresses")
        if data["version"] == 2:
            if data["controller_le"] != self.controller_address.hex():
                raise ValueError("Bond belongs to a different controller identity")
            keys = {bytes.fromhex(host): bytes.fromhex(key) for host, key in data["keys_le"].items()}
        else:
            keys = dict.fromkeys(hosts, bytes.fromhex(data["ltk_le"]))
        if set(keys) != set(hosts) or any(len(key) != 16 for key in keys.values()):
            raise ValueError("Invalid stored key records")
        self.hosts, self.host_keys, self.ltk = hosts, keys, keys[hosts[0]]
        self.confirmed = self.finalized = True
        self.pending_direct = []
