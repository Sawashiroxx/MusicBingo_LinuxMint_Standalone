"""Startet einen simulierten MPRIS-Player als eigenen Prozess (für E2E-Tests).

Aufruf: python3 fake_player_process.py <statusdatei> [art] [verzögerung_s]
Arten: spotify, youtube, spotify-ohne-openuri, spotify-ignoriert (OpenUri ohne Wirkung),
spotify-pausiert (Titel wird geladen, bleibt aber pausiert).
Mit Verzögerung meldet sich der Player erst nach so vielen Sekunden am Bus (wie eine startende App).
Schreibt laufend {"calls": [...], "pos": n, "status": …} in die Statusdatei.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gi.repository import GLib  # noqa: E402

from tests.support.fake_mpris import TRACKS, YOUTUBE_TRACKS, FakePlayer  # noqa: E402

EXTRA = {"mpris:trackid": "/com/spotify/track/7vQbuQcyTflfCIOu3Uzzya", "xesam:title": "Highway to Hell",
         "xesam:artist": ["AC/DC"]}
KINDS = {
    "spotify": ("org.mpris.MediaPlayer2.spotify", "Spotify", TRACKS + [EXTRA]),
    "youtube": ("org.mpris.MediaPlayer2.firefox.instance_1_23", "Mozilla Firefox", YOUTUBE_TRACKS),
}
for variant in ("spotify-ohne-openuri", "spotify-ignoriert", "spotify-pausiert"):
    KINDS[variant] = KINDS["spotify"]
OPEN_MODES = {"spotify-ignoriert": "ignore", "spotify-pausiert": "paused"}


def main() -> None:
    log = Path(sys.argv[1])
    kind = sys.argv[2] if len(sys.argv) > 2 else "spotify"
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    bus_name, identity, tracks = KINDS[kind]
    time.sleep(delay)
    fake = FakePlayer(os.environ["DBUS_SESSION_BUS_ADDRESS"], bus_name, list(tracks), True, identity)
    fake.reject_open_uri = kind == "spotify-ohne-openuri"
    fake.open_mode = OPEN_MODES.get(kind, "play")

    def dump() -> bool:
        temporary = log.with_suffix(".tmp")
        temporary.write_text(json.dumps({"calls": fake.calls, "pos": fake.position, "status": fake.status}))
        temporary.replace(log)
        return True

    GLib.timeout_add(50, dump)
    print("ready", flush=True)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
