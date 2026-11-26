"""Was die Gäste auf dem Beamer sehen – reine Daten, ohne GTK.

Der Songtitel wird erst gezeigt, wenn die Spielleitung ihn aufdeckt (oder der
Timer auflöst). Frühere Songs sind ohnehin bekannt und dürfen sichtbar sein.
Ist „Titel auf dem Beamer aufdecken“ aus (``service.beamer_reveal``), bleibt jeder
Titel verborgen – auch die früheren Songs unter „Zuletzt“. Wie viele frühere Songs
„Zuletzt“ zeigt (0–5, Standard 3) und wie groß, stellt die Spielleitung ein.
Ist „Runde auf dem Beamer zeigen“ aus (``service.beamer_round``), steht oben nur das Ziel.
"""
from dataclasses import dataclass, field

from musik_bingo.domain.forecast import WIN_TARGET_LABELS


@dataclass(frozen=True)
class BeamerState:
    event_title: str
    round_line: str          # „Runde 2 · Ziel: 2 Reihen“ (ohne Runde: „Ziel: 2 Reihen“)
    song_line: str           # „Song 17“
    title: str               # Songtitel oder „♪ ♪ ♪“
    artist: str
    revealed: bool
    recent: tuple[str, ...]  # zuletzt gespielte (bereits bekannte) Songs
    timer: str               # Countdown-Text oder ""
    banner: str              # z. B. „BINGO! Karte #12 · Oma Erna“ oder ""
    recent_scale: float = field(default=1.0)  # Schriftgröße von „Zuletzt“ (1.0 = normal)


# „Zuletzt“ auf dem Beamer: höchstens so viele Songs, Größenstufen für weit entfernte Plätze
MAX_RECENT = 5
RECENT_SIZES = {"normal": 1.0, "gross": 1.5, "sehr_gross": 2.0}
RECENT_SIZE_LABELS = {"normal": "Normal", "gross": "Groß", "sehr_gross": "Sehr groß"}


HIDDEN = "♪ ♪ ♪"


def build_beamer_state(service, revealed: bool, timer_text: str = "", banner: str = "") -> BeamerState:
    caller = service.game.caller
    drawn = caller.drawn
    current = caller.current
    target_line = f"Ziel: {WIN_TARGET_LABELS[service.win_target]}"
    round_line = f"Runde {service.round_number} · {target_line}" if service.beamer_round else target_line
    if current is None:
        song_line = "Gleich geht's los" if caller.pool else "Noch keine Runde"
        title, artist, shown = "", "", False
    else:
        song_line = f"Song {len(drawn)}"
        shown = bool(revealed) and service.beamer_reveal
        title, artist = (current.title, current.artist) if shown else (HIDDEN, "")
    # „Zuletzt“ = vorherige Songs; der aktuelle steht (aufgedeckt) groß in der Mitte oder bleibt verborgen.
    previous = drawn[:-1] if current is not None else drawn
    count = service.beamer_recent_count if service.beamer_reveal else 0
    recent = tuple(song.display_name for song in reversed(previous[-count:])) if count else ()
    return BeamerState(service.event_title, round_line, song_line, title, artist, shown, recent, timer_text, banner,
                       RECENT_SIZES[service.beamer_recent_size])
