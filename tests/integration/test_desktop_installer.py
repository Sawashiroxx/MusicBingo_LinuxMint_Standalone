import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DesktopInstallerTests(unittest.TestCase):
    def test_installs_launcher_and_icon_with_current_project_path(self):
        with tempfile.TemporaryDirectory() as data_home:
            environment = os.environ.copy()
            environment["XDG_DATA_HOME"] = data_home
            subprocess.run(
                ["bash", str(PROJECT_ROOT / "scripts" / "install-desktop.sh")],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            desktop_file = Path(data_home) / "applications" / "musik-bingo.desktop"
            contents = desktop_file.read_text(encoding="utf-8")
            icons = Path(data_home) / "icons" / "hicolor"
            self.assertTrue((icons / "scalable" / "apps" / "musik-bingo.svg").is_file())
            for size in (16, 24, 32, 48, 64, 128, 256, 512):
                png = icons / f"{size}x{size}" / "apps" / "musik-bingo.png"
                self.assertTrue(png.is_file(), png)
                self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            if shutil.which("desktop-file-validate"):
                subprocess.run(["desktop-file-validate", str(desktop_file)], check=True)

        self.assertIn(f'Exec=/bin/bash "{PROJECT_ROOT}/scripts/starten.sh"', contents)
        self.assertIn(f"Path={PROJECT_ROOT}", contents)
        self.assertIn("Name=Musik Bingo", contents)
        self.assertIn("Icon=musik-bingo", contents)

    def test_starter_scripts_have_valid_syntax(self):
        for script in ("starten.sh", "install-desktop.sh"):
            with self.subTest(script=script):
                subprocess.run(["bash", "-n", str(PROJECT_ROOT / "scripts" / script)], check=True)


if __name__ == "__main__":
    unittest.main()
