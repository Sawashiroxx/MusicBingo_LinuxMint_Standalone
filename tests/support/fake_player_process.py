"""Startet einen simulierten MPRIS-Player als eigenen Prozess (für E2E-Tests).

Aufruf: python3 fake_player_process.py <statusdatei> [spotify|ytmusic|spotify-ohne-openuri]
Schreibt laufend {"calls": [...], "pos": n} in die Statusdatei.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gi.repository import GLib  # noqa: E402

from tests.support.fake_mpris import TRACKS, YTMUSIC_TRACKS, FakePlayer  # noqa: E402

EXTRA = {"mpris:trackid": "/com/spotify/track/7vQbuQcyTflfCIOu3Uzzya", "xesam:title": "Highway to Hell",
         "xesam:artist": ["AC/DC"]}
KINDS = {
    "spotify": ("org.mpris.MediaPlayer2.spotify", "Spotify", TRACKS + [EXTRA]),
    "ytmusic": ("org.mpris.MediaPlayer2.youtube-music", "YouTube Music", YTMUSIC_TRACKS),
}
KINDS["spotify-ohne-openuri"] = KINDS["spotify"]


def main() -> None:
    log = Path(sys.argv[1])
    kind = sys.argv[2] if len(sys.argv) > 2 else "spotify"
    bus_name, identity, tracks = KINDS[kind]
    fake = FakePlayer(os.environ["DBUS_SESSION_BUS_ADDRESS"], bus_name, list(tracks), True, identity)
    fake.reject_open_uri = kind == "spotify-ohne-openuri"

    def dump() -> bool:
        temporary = log.with_suffix(".tmp")
        temporary.write_text(json.dumps({"calls": fake.calls, "pos": fake.position}))
        temporary.replace(log)
        return True

    GLib.timeout_add(50, dump)
    print("ready", flush=True)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
