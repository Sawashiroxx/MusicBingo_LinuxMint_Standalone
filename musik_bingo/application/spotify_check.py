"""Spotify-Test: Prüfliste und Wahl des Testsongs – ohne GTK und D-Bus testbar."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from musik_bingo.domain.links import is_spotify
from musik_bingo.domain.models import Song

AUTOPLAY_HINT = ("In Spotify unter Einstellungen → Autoplay ausschalten, sonst laufen nach jedem Song "
                 "ähnliche Titel weiter")


def count_spotify_links(songs: Iterable[Song]) -> int:
    return sum(1 for song in songs if is_spotify(song.link))


NO_TEST_SONG_NOTE = ("Kein Titel abgespielt: Die Runde läuft schon, und weder der aktuelle noch ein bereits "
                     "gezogener Song hat einen Spotify-Link. Ein noch nicht gezogener Song wird nicht angespielt, "
                     "damit die Gäste ihn nicht vorab hören.")
NO_REPLY_NOTE = ("Spotify reagiert nicht – die App läuft, antwortet aber nicht. Spotify beenden, "
                 "neu starten und den Test wiederholen.")


def pick_test_song(current: Song | None, songs: Iterable[Song], drawn: Sequence[Song] = ()) -> Song | None:
    """Song, den „Spotify testen“ anspielen darf.

    Vor Spielbeginn (nichts gezogen): der erste Song mit Spotify-Link. Läuft die Runde, nur der aktuelle
    oder ein bereits gezogener Song (der zuletzt gezogene zuerst) – nie ein noch nicht gezogener,
    den die Gäste sonst vorab hören würden. Kein passender Song → None (Test ohne Abspielen).
    """
    if current is not None and is_spotify(current.link):
        return current
    if current is not None or drawn:
        return next((song for song in reversed(list(drawn)) if is_spotify(song.link)), None)
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


def report(items: list[tuple[bool, str]], notes: Sequence[str] = ()) -> str:
    lines = [("✓ " if ok else "✗ ") + text for ok, text in items]
    extra = "".join(f"\n\n{note}" for note in notes)
    return "\n".join(lines) + extra + "\n\nHinweis: " + AUTOPLAY_HINT
