"""Startet einen simulierten Spotify-Player als eigenen Prozess (für E2E-Tests).

Aufruf: python3 fake_spotify_process.py <statusdatei>
Schreibt laufend {"calls": [...], "pos": n} in die Statusdatei.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gi.repository import GLib  # noqa: E402

from tests.support.fake_mpris import TRACKS, FakePlayer  # noqa: E402

EXTRA = {"mpris:trackid": "/com/spotify/track/7vQbuQcyTflfCIOu3Uzzya", "xesam:title": "Highway to Hell",
         "xesam:artist": ["AC/DC"]}


def main() -> None:
    log = Path(sys.argv[1])
    fake = FakePlayer(os.environ["DBUS_SESSION_BUS_ADDRESS"], "org.mpris.MediaPlayer2.spotify",
                      TRACKS + [EXTRA], True)

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
