"""Install the NXBT web overlay, preserving existing files in a dated backup."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil


def install(root, project, python, pythonpath, address, config_path):
    root, project, python, config_path = map(Path, (root, project, python, config_path))
    if not all(path.is_absolute() for path in (root, project, python, config_path)):
        raise ValueError("Use absolute paths")
    if not (root / "nxbt/web/app.py").is_file() or not (project / "src/joycon2_emulator").is_dir():
        raise ValueError("NXBT or JoyCon2 project not found")
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", address):
        raise ValueError("Expected adapter's own six-byte address")
    overlay = Path(__file__).parent / "web"
    backup = root / ".joycon2-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup.mkdir(parents=True, mode=0o700)
    exclude = root / ".git/info/exclude"
    if exclude.is_file() and ".joycon2-backups/" not in exclude.read_text().splitlines():
        with exclude.open("a") as stream:
            stream.write("\n.joycon2-backups/\n")
    for source in overlay.rglob("*"):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        relative = source.relative_to(overlay)
        target = root / "nxbt/web" / relative
        if target.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if config_path.exists():
        shutil.copy2(config_path, backup / "previous-config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_name(config_path.name + ".new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"project": str(project), "python": str(python),
                   "pythonpath": pythonpath, "address": address}, stream)
    os.replace(temporary, config_path)
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nxbt-root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--pythonpath", default="")
    parser.add_argument("--address", required=True)
    parser.add_argument("--config", type=Path, default=Path("/etc/nxbt-joycon2.json"))
    args = parser.parse_args()
    print("Previous files saved at", install(args.nxbt_root, args.project, args.python,
                                            args.pythonpath, args.address, args.config))
