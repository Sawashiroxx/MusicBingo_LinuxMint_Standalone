"""Was die Gäste auf dem Beamer sehen – reine Daten, ohne GTK.

Der Songtitel wird erst gezeigt, wenn die Spielleitung ihn aufdeckt (oder der
Timer auflöst). Frühere Songs sind ohnehin bekannt und dürfen sichtbar sein.
Ist „Titel auf dem Beamer aufdecken“ aus (``service.beamer_reveal``), bleibt jeder
Titel verborgen – auch die früheren Songs unter „Zuletzt“.
"""
from dataclasses import dataclass

from musik_bingo.domain.forecast import WIN_TARGET_LABELS


@dataclass(frozen=True)
class BeamerState:
    event_title: str
    round_line: str          # „Runde 2 · Ziel: 2 Reihen“
    song_line: str           # „Song 17“
    title: str               # Songtitel oder „♪ ♪ ♪“
    artist: str
    revealed: bool
    recent: tuple[str, ...]  # zuletzt gespielte (bereits bekannte) Songs
    timer: str               # Countdown-Text oder ""
    banner: str              # z. B. „BINGO! Karte #12 · Oma Erna“ oder ""


HIDDEN = "♪ ♪ ♪"


def build_beamer_state(service, revealed: bool, timer_text: str = "", banner: str = "") -> BeamerState:
    caller = service.game.caller
    drawn = caller.drawn
    current = caller.current
    round_line = f"Runde {service.round_number} · Ziel: {WIN_TARGET_LABELS[service.win_target]}"
    if current is None:
        song_line = "Gleich geht's los" if caller.pool else "Noch keine Runde"
        title, artist, shown = "", "", False
    else:
        song_line = f"Song {len(drawn)}"
        shown = bool(revealed) and service.beamer_reveal
        title, artist = (current.title, current.artist) if shown else (HIDDEN, "")
    # „Zuletzt“ = vorherige Songs; der aktuelle steht (aufgedeckt) groß in der Mitte oder bleibt verborgen.
    previous = drawn[:-1] if current is not None else drawn
    recent = tuple(song.display_name for song in reversed(previous[-5:])) if service.beamer_reveal else ()
    return BeamerState(service.event_title, round_line, song_line, title, artist, shown, recent, timer_text, banner)
