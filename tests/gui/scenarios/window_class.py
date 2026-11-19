"""Startet die App wie im Alltag (python -m musik_bingo.main) und prüft die Fensterklasse."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_ID = "de.weihnachtsfeier.musikbingo"
env = dict(os.environ, XDG_DATA_HOME=tempfile.mkdtemp(), XDG_CONFIG_HOME=tempfile.mkdtemp(), PYTHONPATH=str(ROOT))
app = subprocess.Popen([sys.executable, "-m", "musik_bingo.main"], cwd=ROOT, env=env)
try:
    window = ""
    for _ in range(60):
        result = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"], capture_output=True, text=True)
        ids = subprocess.run(["bash", "-c", "xwininfo -root -tree | grep -i 'Musik Bingo' | awk '{print $1}'"],
                             capture_output=True, text=True).stdout.split()
        if ids:
            window = ids[0]
            break
        time.sleep(0.5)
    wm_class = subprocess.run(["xprop", "-id", window, "WM_CLASS"], capture_output=True, text=True).stdout if window else ""
    ok = wm_class.count(f'"{APP_ID}"') == 2
    print(("PASS " if ok else "FAIL ") + f"WM_CLASS = {wm_class.strip() or 'kein Fenster'}")
    desktop = (ROOT / "scripts" / "install-desktop.sh").read_text()
    ok2 = f"StartupWMClass={APP_ID}" in desktop
    print(("PASS " if ok2 else "FAIL ") + "StartupWMClass im Menüeintrag passt")
    print(f"{int(ok) + int(ok2)}/2 bestanden")
finally:
    app.terminate()
    app.wait(10)
sys.exit(0 if ok and ok2 else 1)
