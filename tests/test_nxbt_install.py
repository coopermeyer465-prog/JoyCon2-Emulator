import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


FILE = Path(__file__).resolve().parents[1] / "integrations/nxbt/install.py"
spec = importlib.util.spec_from_file_location("nxbt_install", FILE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_preserves_private_mouse_capture_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "nxbt"
            project = Path(directory) / "project"
            config = Path(directory) / "config.json"
            (root / "nxbt/web").mkdir(parents=True)
            (root / "nxbt/web/app.py").write_text("old")
            (project / "src/joycon2_emulator").mkdir(parents=True)
            capture = project / ".state/mouse-motion.json"
            config.write_text(json.dumps({"mouse_capture": str(capture)}))
            installer.install(root, project, Path("/usr/bin/python3"), "/deps",
                              "00:11:22:33:44:55", config)
            self.assertEqual(json.loads(config.read_text())["mouse_capture"], str(capture))


if __name__ == "__main__":
    unittest.main()
