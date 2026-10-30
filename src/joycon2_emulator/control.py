"""Private local command socket and bounded, replaceable controller sequences."""

import asyncio
import json
import math
import os
from pathlib import Path
import socket
import stat
import time

from .protocol import RIGHT_BUTTONS


def number(value, minimum, maximum, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return float(value)


def step(value):
    if not isinstance(value, dict) or set(value) - {"buttons", "x", "y", "duration", "orientation"}:
        raise ValueError("Step accepts buttons, x, y, duration and orientation only")
    buttons = value.get("buttons", [])
    if not isinstance(buttons, list) or len(buttons) > len(RIGHT_BUTTONS):
        raise ValueError("buttons must be a short list")
    if any(not isinstance(button, str) or button not in RIGHT_BUTTONS for button in buttons):
        raise ValueError("Unsupported right Joy-Con button")
    x = number(value.get("x", 0), -1, 1, "x")
    y = number(value.get("y", 0), -1, 1, "y")
    orientation = value.get("orientation", "raw")
    if orientation not in ("raw", "sideways-right"):
        raise ValueError("Unknown stick orientation")
    if orientation == "sideways-right":
        x, y = -y, x
    return {"buttons": tuple(sorted(set(buttons))), "x": x, "y": y,
            "duration": number(value.get("duration", 0.05), 0.02, 10, "duration")}


class InputState:
    def __init__(self):
        self.ready = False
        self.connected = False
        self.stopping = False
        self.registering = False
        self.steps = []
        self.started = 0
        self.generation = 0
        self.mouse_supported = False
        self.mouse_enabled = False
        self.pending_mouse = None
        self.mouse_contact_until = 0
        self.mouse_surface = 255
        self.mouse_only = False
        self.mouse_click_until = 0

    def clear_mouse(self):
        self.pending_mouse = None
        self.mouse_contact_until = 0
        self.mouse_surface = 255
        self.mouse_click_until = 0

    def release(self):
        self.steps = []
        self.clear_mouse()
        self.generation += 1

    def take_mouse(self, now):
        """Consume one relative movement, never repeat it as a held state."""
        pending, self.pending_mouse = self.pending_mouse, None
        if not self.mouse_supported or not self.mouse_enabled:
            self.clear_mouse()
            return None
        if not self.ready or self.registering or self.stopping:
            self.clear_mouse()
            return (0, 0, 255)
        if pending is not None and now < pending[1]:
            self.mouse_surface = pending[0][2]
            self.mouse_contact_until = pending[1] if self.mouse_surface != 255 else 0
            return pending[0]
        return (0, 0, self.mouse_surface if now < self.mouse_contact_until else 255)

    def snapshot(self, now):
        if self.mouse_only and now < self.mouse_click_until:
            return ("R",), 0.0, 0.0
        elapsed = now - self.started
        for value in self.steps:
            if elapsed < value["duration"]:
                return value["buttons"], value["x"], value["y"]
            elapsed -= value["duration"]
        self.steps = []
        return (), 0.0, 0.0

    def execute(self, request, now=None):
        now = time.monotonic() if now is None else now
        if not isinstance(request, dict):
            raise ValueError("Expected a JSON object")
        operation = request.get("op")
        allowed = {"set": {"op", "state"}, "sequence": {"op", "steps"},
                   "release": {"op"}, "status": {"op"}, "stop": {"op"},
                   "mouse": {"op", "dx", "dy", "lifted", "surface"},
                   "mouse_click": {"op"}}
        if not isinstance(operation, str) or operation not in allowed or set(request) - allowed[operation]:
            raise ValueError("Unknown operation or request fields")
        if operation == "mouse_click":
            if (not self.mouse_only or not self.ready or self.registering or self.stopping
                    or not self.mouse_supported or not self.mouse_enabled or now < self.mouse_click_until):
                raise ValueError("Native mouse click is not ready")
            self.mouse_click_until = now + 0.08
        elif operation == "mouse":
            if (not self.ready or self.registering or self.stopping
                    or not self.mouse_supported or not self.mouse_enabled):
                raise ValueError("Experimental mouse is not enabled by the console")
            dx, dy = request.get("dx", 0), request.get("dy", 0)
            if any(type(value) is not int or not -32768 <= value <= 32767 for value in (dx, dy)):
                raise ValueError("Mouse deltas must be signed 16-bit integers")
            lifted = request.get("lifted", False)
            if type(lifted) is not bool or (lifted and (dx or dy)):
                raise ValueError("Lifted mouse must have zero movement")
            surface = request.get("surface", 0)
            if type(surface) is not int or not 0 <= surface <= 254 or (lifted and "surface" in request):
                raise ValueError("Raw surface must be 0..254 and cannot accompany lifted")
            if self.pending_mouse is not None and now < self.pending_mouse[1]:
                raise ValueError("A mouse movement is already pending")
            self.pending_mouse = ((dx, dy, 255 if lifted else surface), now + 0.25)
        elif operation in ("set", "sequence"):
            if not self.ready or self.registering or self.stopping or self.mouse_only:
                raise ValueError("Controller is not ready; no input was queued")
            values = [request.get("state")] if operation == "set" else request.get("steps")
            if not isinstance(values, list) or not 1 <= len(values) <= 256:
                raise ValueError("Expected 1 to 256 sequence steps")
            validated = [step(value) for value in values]
            if sum(value["duration"] for value in validated) > 300:
                raise ValueError("Sequence exceeds 300 seconds")
            self.steps, self.started = validated, now
            self.generation += 1
        elif operation in ("release", "stop"):
            self.release()
            if operation == "stop":
                self.stopping = True
        buttons, x, y = self.snapshot(now)
        return {"ok": True, "right_only": True, "connected": self.connected,
                "ready": self.ready and not self.registering, "registering": self.registering,
                "stopping": self.stopping,
                "generation": self.generation, "buttons": list(buttons), "x": x, "y": y,
                "experimental_mouse": self.mouse_supported, "mouse_enabled": self.mouse_enabled,
                "mouse_pending": bool(self.pending_mouse and now < self.pending_mouse[1]),
                "queued_steps": len(self.steps)}


class ControlServer:
    def __init__(self, path, state):
        self.path, self.state = Path(path), state
        self.server = None
        self.inode = None

    async def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("Control path must not be a symlink")
        if self.path.exists():
            info = self.path.stat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                raise ValueError("Refusing to replace control path")
            probe = socket.socket(socket.AF_UNIX)
            probe.settimeout(0.5)
            try:
                probe.connect(str(self.path))
            except ConnectionRefusedError:
                self.path.unlink()
            else:
                raise ValueError("A control server is already active")
            finally:
                probe.close()
        self.server = await asyncio.start_unix_server(self.handle, path=str(self.path), limit=65536)
        self.path.chmod(0o600)
        self.inode = self.path.stat().st_ino

    async def handle(self, reader, writer):
        try:
            raw = await asyncio.wait_for(reader.readline(), 3)
            if not raw:
                writer.close()
                await writer.wait_closed()
                return
            if not raw.endswith(b"\n") or len(raw) > 65536:
                raise ValueError("Expected one bounded JSON line")
            result = self.state.execute(json.loads(raw))
        except (ValueError, TypeError, asyncio.TimeoutError):
            result = {"ok": False, "error": "Invalid request, unsupported input, or controller not ready"}
        try:
            writer.write(json.dumps(result).encode() + b"\n")
            await asyncio.wait_for(writer.drain(), 3)
        except ConnectionError:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def close(self):
        self.state.release()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            try:
                info = self.path.lstat()
            except FileNotFoundError:
                return
            if stat.S_ISSOCK(info.st_mode) and info.st_ino == self.inode:
                self.path.unlink()


async def send(path, request):
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(path), limit=8192), 3)
    try:
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()
        result = json.loads(await asyncio.wait_for(reader.readline(), 3))
        return result
    finally:
        writer.close()
        await writer.wait_closed()
