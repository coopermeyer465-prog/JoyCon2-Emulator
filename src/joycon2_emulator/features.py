"""Feature-mask state; native mouse is an explicit experimental opt-in."""


class Features:
    SUPPORTED = 3

    def __init__(self, mouse=False, sensor_replay=False):
        self.supported = self.SUPPORTED | (0x10 if mouse else 0) | (4 if sensor_replay else 0)
        self.mask = None
        self.enabled = 0

    def handle(self, subcommand, payload):
        if len(payload) != 4:
            raise ValueError("Feature command requires a four-byte mask")
        flags = int.from_bytes(payload, "little")
        if subcommand == 1:
            info = bytearray(12)
            info[4] = 7 if flags & 1 else 0
            info[5] = 7 if flags & 2 else 0
            info[6] = 3 if flags & self.supported & 4 else 0
            info[8] = 3 if flags & self.supported & 0x10 else 0
            return bytes(info)
        if subcommand == 2:
            self.mask = flags & self.supported
            self.enabled &= self.mask
        elif subcommand == 3:
            self.mask = None
            self.enabled = 0
        elif subcommand in (4, 5):
            if self.mask is None:
                raise ValueError("Set the feature mask before enabling/disabling")
            selected = flags & self.mask
            if subcommand == 4:
                self.enabled |= selected
            else:
                self.enabled &= ~selected
        else:
            raise NotImplementedError("Unsupported feature configuration command")
        return bytes(4)
