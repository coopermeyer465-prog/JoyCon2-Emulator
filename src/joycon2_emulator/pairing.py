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
                json.dump({"version": 1, "hosts_le": [host.hex() for host in self.hosts],
                           "ltk_le": self.ltk.hex()}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
