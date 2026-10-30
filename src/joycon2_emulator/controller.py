"""Only dispatch commands with implemented, documented behavior."""

from .pairing import PairingSession
from .memory import VirtualMemory
from .features import Features


OPAQUE_RESPONSES = {(7, 1): b"\x00", (0x16, 1): bytes(24),
                    (0x11, 1): b"\x01\x00\x00\x00",
                    (0x13, 1): b"\x01\x00\x00\x00",
                    (0x13, 2): b"\x01" + bytes(7),
                    (0x13, 3): b"\x01" + bytes(7),
                    # Published protocol response; semantics remain unknown.
                    (0x11, 3): bytes.fromhex("01200300000ae81c3b797d8b3a0ae89c4258a00b420ae89c4158a00b41")}


class Controller:
    def __init__(self, address, mouse=False):
        self.pairing = PairingSession(address)
        self.memory = VirtualMemory(address)
        self.vibration_sample = None
        self.vibration_data = None
        self.player_led_pattern = 0
        self.player_led_reserved = b""
        self.features = Features(mouse=mouse)

    def handle(self, request):
        if request.command == 0x15:
            return self.pairing.handle(request.subcommand, request.payload)
        if request.command == 3 and request.subcommand in (7, 9):
            return self.pairing.handle_direct(request.subcommand, request.payload)
        if request.command == 0x0C:
            return self.features.handle(request.subcommand, request.payload)
        if (request.command, request.subcommand) == (2, 4):
            return self.memory.handle_read(request.payload)
        if (request.command, request.subcommand) == (0x0A, 2):
            if len(request.payload) != 4 or request.payload[0] > 7:
                raise ValueError("Expected a four-byte vibration sample request")
            self.vibration_sample = request.payload[0]
            return b""
        if (request.command, request.subcommand) == (0x0A, 8):
            if len(request.payload) != 20:
                raise ValueError("Expected a 20-byte virtual rumble update")
            self.vibration_data = bytes(request.payload)
            return b""
        if (request.command, request.subcommand) == (9, 7):
            # This console sends four bytes; the documented form has eight.
            if len(request.payload) not in (4, 8):
                raise ValueError("Expected a four/eight-byte LED pattern")
            self.player_led_pattern = request.payload[0] & 15
            self.player_led_reserved = request.payload[1:]
            return b""
        if (request.command, request.subcommand) == (0x10, 1):
            if request.payload:
                raise ValueError("Firmware information expects no payload")
            # Virtual implementation 0.1.0, right half, no BT/DSP firmware image.
            return bytes.fromhex("0001000100000000ffffffff")
        if (request.command, request.subcommand) == (1, 0x0C):
            if request.payload:
                raise ValueError("Power/status query expects no payload")
            # Virtual USB-powered device: 100%, compatibility flags, 4200 mV.
            return bytes.fromhex("64126810")
        if (request.command, request.subcommand) in OPAQUE_RESPONSES:
            if request.payload:
                raise ValueError("Opaque initialization query expects no payload")
            # Documented wire responses; underlying unknown features are not claimed.
            return OPAQUE_RESPONSES[request.command, request.subcommand]
        raise NotImplementedError(f"Command {request.command:02x}/{request.subcommand:02x}")
