"""Gemeinsames Gerüst für GUI-Szenarien (laufen unter xvfb-run und dbus-run-session)."""
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TMP = Path(tempfile.mkdtemp(prefix="musik-bingo-gui-"))
os.environ["XDG_DATA_HOME"] = str(TMP / "data")
os.environ["XDG_CONFIG_HOME"] = str(TMP / "config")
sys.path.insert(0, str(ROOT))


def forbid_network() -> None:
    """Jede Python-Netzwerkaktion im App-Prozess bricht den Test ab."""
    def hook(event, _args):
        if event.startswith(("socket.connect", "socket.getaddrinfo", "urllib.Request", "http.client", "webbrowser")):
            raise RuntimeError(f"Netzwerkzugriff der App: {event}")
    sys.addaudithook(hook)


import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

RESULTS: list[tuple[str, bool]] = []
MESSAGES: list[str] = []


def check(name: str, condition) -> bool:
    RESULTS.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    return bool(condition)


def wait(predicate, timeout: float = 5.0) -> bool:
    context = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def pump(seconds: float = 0.2) -> None:
    wait(lambda: False, seconds)


def patch_dialogs() -> None:
    """Modale Rückfragen automatisch bestätigen, Meldungen nur protokollieren."""
    from musik_bingo.presentation import dialogs
    dialogs.confirm = lambda *args, **kwargs: True
    dialogs.message = lambda parent, kind, title, detail: MESSAGES.append(title)


def screenshot(widget: Gtk.Widget, path: Path) -> bool:
    window = widget.get_window()
    if window is None:
        return False
    pixbuf = Gdk.pixbuf_get_from_window(window, 0, 0, window.get_width(), window.get_height())
    path.parent.mkdir(parents=True, exist_ok=True)
    pixbuf.savev(str(path), "png", [], [])
    return path.stat().st_size > 10_000


def run(scenario) -> None:
    """Startet die App, führt scenario(window) aus und beendet mit Exit-Code."""
    from musik_bingo.presentation import gtk_app
    app = gtk_app.MusikBingoApplication()

    def start() -> bool:
        try:
            scenario(app.props.active_window)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            check("Szenario ohne Ausnahme", False)
        app.quit()
        return False

    GLib.timeout_add(500, start)
    app.run([])
    failed = [name for name, ok in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} bestanden", flush=True)
    sys.exit(1 if failed or not RESULTS else 0)
