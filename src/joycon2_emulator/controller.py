"""Only dispatch commands with implemented, documented behavior."""

from .pairing import PairingSession


class Controller:
    def __init__(self, address):
        self.pairing = PairingSession(address)

    def handle(self, request):
        if request.command == 0x15:
            return self.pairing.handle(request.subcommand, request.payload)
        if (request.command, request.subcommand) == (7, 1):
            if request.payload:
                raise ValueError("Initialization 07/01 expects no payload")
            # First initialization response observed/documented by ndeadly.
            return b"\x00"
        raise NotImplementedError(f"Command {request.command:02x}/{request.subcommand:02x}")
