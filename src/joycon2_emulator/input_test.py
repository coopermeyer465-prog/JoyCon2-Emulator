"""Bounded, opt-in button pulse for hardware verification, not a gamepad relay."""


class ButtonPulse:
    OPTIONS = {"join": ("SL", "SR"), "home": ("HOME",), "a": ("A",), "b": ("B",)}

    def __init__(self, name):
        if name not in self.OPTIONS:
            raise ValueError("Unsupported test pulse")
        self.buttons = self.OPTIONS[name]
        self.duration_ms = 50 if name == "home" else 250

    def at(self, seconds):
        return self.buttons if 2.0 <= seconds < 2.0 + self.duration_ms / 1000 else ()
