"""Bounded, opt-in button pulse for hardware verification, not a gamepad relay."""


class ButtonPulse:
    OPTIONS = {"join": ("SL", "SR"), "home": ("HOME",), "a": ("A",), "b": ("B",)}

    def __init__(self, name):
        if name not in self.OPTIONS:
            raise ValueError("Unsupported test pulse")
        self.buttons = self.OPTIONS[name]

    def at(self, seconds):
        return self.buttons if 2.0 <= seconds < 2.25 else ()
