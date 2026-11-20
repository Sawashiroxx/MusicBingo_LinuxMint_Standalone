"""Spotify-Test: Prüfliste und Wahl des Testsongs – ohne GTK und D-Bus testbar."""
from __future__ import annotations

from collections.abc import Iterable

from musik_bingo.domain.links import is_spotify
from musik_bingo.domain.models import Song

AUTOPLAY_HINT = ("In Spotify unter Einstellungen → Autoplay ausschalten, sonst laufen nach jedem Song "
                 "ähnliche Titel weiter")


def count_spotify_links(songs: Iterable[Song]) -> int:
    return sum(1 for song in songs if is_spotify(song.link))


def pick_test_song(current: Song | None, songs: Iterable[Song]) -> Song | None:
    """Der aktuelle Song, wenn er einen Spotify-Link hat – sonst der erste der Runde mit Link."""
    if current is not None and is_spotify(current.link):
        return current
    return next((song for song in songs if is_spotify(song.link)), None)


def checklist(found: bool, can_control: bool, started: bool, paused: bool,
              with_link: int, total: int) -> list[tuple[bool, str]]:
    return [
        (found, "Spotify gefunden"),
        (found and can_control, "Steuerung möglich"),
        (started, "Titel gestartet"),
        (paused, "Pause funktioniert"),
        (total > 0 and with_link == total, f"{with_link} von {total} Songs mit Spotify-Link"),
    ]


def report(items: list[tuple[bool, str]]) -> str:
    lines = [("✓ " if ok else "✗ ") + text for ok, text in items]
    return "\n".join(lines) + "\n\nHinweis: " + AUTOPLAY_HINT
