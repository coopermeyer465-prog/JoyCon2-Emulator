"""Local NXBT adapter for the separate Joy-Con 2 BLE process (stdlib only)."""

import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import time


def input_step(packet, stick="left", orientation="sideways-right"):
    if not isinstance(packet, dict) or stick not in ("left", "right"):
        raise ValueError("Invalid input packet or stick selection")
    if orientation not in ("raw", "sideways-right"):
        raise ValueError("Invalid orientation")
    source = packet.get("L_STICK" if stick == "left" else "R_STICK", {})
    if not isinstance(source, dict):
        raise ValueError("Invalid stick")
    axes = []
    for key in ("X_VALUE", "Y_VALUE"):
        value = source.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -100 <= value <= 100:
            raise ValueError("Invalid stick axis")
        axes.append(value / 100)
    buttons = [name for name in ("A", "B", "X", "Y", "R", "ZR", "PLUS", "HOME", "C")
               if packet.get(name) is True]
    if source.get("PRESSED") is True:
        buttons.append("STICK")
    for source_name, target in (("JCR_SL", "SL"), ("JCR_SR", "SR")):
        if packet.get(source_name) is True:
            buttons.append(target)
    return {"buttons": buttons, "x": axes[0], "y": axes[1],
            "orientation": orientation, "duration": 0.45}


class JoyCon2Bridge:
    UNIT = "joycon2-web.service"

    def __init__(self, config_path=None):
        self.config_path = Path(config_path or os.environ.get("NXBT_JOYCON2_CONFIG", "/etc/nxbt-joycon2.json"))
        self.config = None

    def load(self):
        config = json.loads(self.config_path.read_text())
        for key in ("project", "python", "pythonpath", "address"):
            if not isinstance(config.get(key), str):
                raise ValueError("Invalid Joy-Con 2 configuration")
        if not Path(config["project"]).is_absolute() or not Path(config["python"]).is_absolute():
            raise ValueError("Project and Python paths must be absolute")
        if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", config["address"]):
            raise ValueError("Invalid adapter address")
        self.config = config
        return config

    def run(self, *args, check=True):
        return subprocess.run(args, check=check, capture_output=True, text=True, timeout=20)

    def request(self, request):
        config = self.config or self.load()
        path = str(Path(config["project"]) / ".state/control.sock")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(path)
            client.sendall(json.dumps(request).encode() + b"\n")
            with client.makefile("rb") as stream:
                raw = stream.readline(8193)
            if len(raw) > 8192 or not raw.endswith(b"\n"):
                raise ValueError("Invalid backend response")
        result = json.loads(raw)
        if not result.get("ok"):
            raise ValueError(result.get("error", "Joy-Con 2 request failed"))
        return result

    def start(self):
        config = self.load()
        project = Path(config["project"])
        for filename in ("bond.json", "factory-calibration.json"):
            if not (project / ".state" / filename).is_file():
                raise ValueError("Joy-Con 2 needs existing private bond and calibration files")
        self.run("systemctl", "stop", "joycon2-command.service", check=False)
        if self.run("systemctl", "is-active", "--quiet", self.UNIT, check=False).returncode == 0:
            return self.request({"op": "status"})
        self.run("systemctl", "stop", "bluetooth")
        try:
            self.run("hciconfig", "hci0", "down")
            self.run("systemd-run", "--quiet", "--collect", "--unit=" + self.UNIT,
                     "--property=WorkingDirectory=" + str(project),
                     "--property=ExecStopPost=/usr/bin/systemctl start bluetooth",
                     "--property=KillSignal=SIGINT", "--property=TimeoutStopSec=5",
                     "/usr/bin/env", "PYTHONPATH=" + config["pythonpath"] + ":" + str(project / "src"),
                     config["python"], "-m", "joycon2_emulator.cli", "serve", "--experimental",
                     "--address", config["address"], "--calibration", ".state/factory-calibration.json",
                     "--control-socket", ".state/control.sock", "--seconds", "0", "--auto-join")
            for _ in range(40):
                try:
                    return self.request({"op": "status"})
                except (OSError, ValueError):
                    time.sleep(0.1)
            raise RuntimeError("Joy-Con 2 did not start; inspect journalctl -u joycon2-web")
        except Exception:
            self.stop()
            raise

    def stop(self):
        self.run("systemctl", "stop", "joycon2-command.service", check=False)
        self.run("systemctl", "stop", self.UNIT, check=False)
        self.run("systemctl", "start", "bluetooth")

    def status(self):
        result = self.request({"op": "status"})
        return {"state": "connected" if result["ready"] else "connecting",
                "type": "joycon2_right", "errors": []}
