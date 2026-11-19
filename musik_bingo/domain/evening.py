"""Ablauf des Abends: Runden, Gewinnstufen, Gewinnerliste, Titel der Feier.

Klassischer Ablauf pro Runde (die Ziehung läuft dabei weiter):
1 Reihe → 2 Reihen → Volle Karte. Danach beginnt eine neue Runde mit neu
gemischter Ziehung und wieder „1 Reihe“. Dieselben gedruckten Karten bleiben gültig.
"""
import csv
import io
import unicodedata
from dataclasses import dataclass

from .forecast import WIN_TARGET_LABELS, WIN_TARGETS

MAX_TITLE_LENGTH = 60
MAX_NAME_LENGTH = 60
MAX_WINNERS = 1000
DEFAULT_TITLE = "Musik Bingo"


def clean_text(value: str, limit: int) -> str:
    """Text für Anzeige und Druck: ohne Steuer-/Formatzeichen, Leerraum vereinheitlicht, begrenzt."""
    if not isinstance(value, str):
        raise ValueError("Text erwartet.")
    kept = "".join(" " if char.isspace() else char for char in value
                   if char.isspace() or unicodedata.category(char)[0] != "C")
    return " ".join(kept.split())[:limit]


def clean_event_title(value: str) -> str:
    return clean_text(value, MAX_TITLE_LENGTH) or DEFAULT_TITLE


def next_stage(target: str) -> tuple[str, bool]:
    """(nächstes Gewinnziel, beginnt eine neue Runde?)."""
    if target not in WIN_TARGETS:
        raise ValueError("Unbekanntes Gewinnziel.")
    index = WIN_TARGETS.index(target)
    if index + 1 < len(WIN_TARGETS):
        return WIN_TARGETS[index + 1], False
    return WIN_TARGETS[0], True


def next_stage_label(target: str) -> str:
    following, new_round = next_stage(target)
    return "Neue Runde (neu mischen)" if new_round else f"Weiter: {WIN_TARGET_LABELS[following]}"


@dataclass(frozen=True)
class Winner:
    round: int
    target: str
    card: int
    name: str
    song_count: int  # nach wie vielen gezogenen Songs gewonnen

    @property
    def target_label(self) -> str:
        return WIN_TARGET_LABELS[self.target]

    def to_dict(self) -> dict:
        return {"round": self.round, "target": self.target, "card": self.card,
                "name": self.name, "song_count": self.song_count}

    @classmethod
    def from_dict(cls, data: dict, card_count: int) -> "Winner":
        if not isinstance(data, dict):
            raise ValueError("Ungültiger Gewinner im Spielstand.")
        values = [data.get(key) for key in ("round", "card", "song_count")]
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise ValueError("Gewinner: Runde, Karte und Songzahl müssen Zahlen sein.")
        round_number, card, song_count = values
        target, name = data.get("target"), data.get("name", "")
        if target not in WIN_TARGETS or not isinstance(name, str):
            raise ValueError("Gewinner: ungültiges Gewinnziel oder Name.")
        if not 1 <= round_number <= 999 or not 1 <= card <= max(1, card_count) or not 0 <= song_count <= 2000:
            raise ValueError("Gewinner: Werte außerhalb des gültigen Bereichs.")
        return cls(round_number, target, card, clean_text(name, MAX_NAME_LENGTH), song_count)


class DuplicateWinner(ValueError):
    """Die Karte hat an diesem Abend schon gewonnen."""

    def __init__(self, previous: Winner):
        super().__init__(
            f"Karte #{previous.card} hat bereits gewonnen: Runde {previous.round}, {previous.target_label}"
            + (f" ({previous.name})" if previous.name else "") + "."
        )
        self.previous = previous


def check_new_winner(winners: list[Winner], candidate: Winner, allow_repeat: bool = False) -> None:
    """Verhindert, dass dieselbe Karte doppelt gewinnt (gleiche Stufe immer, sonst nur mit Freigabe)."""
    earlier = [winner for winner in winners if winner.card == candidate.card]
    # Gleiche Stufe zuerst melden – sie ist nie erlaubt. Sonst würde die Oberfläche bei einer
    # dritten Prüfung erst „trotzdem eintragen?“ fragen und dann an dieser Stufe scheitern.
    for winner in earlier:
        if winner.round == candidate.round and winner.target == candidate.target:
            raise DuplicateWinner(winner)
    if earlier and not allow_repeat:
        raise DuplicateWinner(earlier[-1])
    if len(winners) >= MAX_WINNERS:
        raise ValueError("Die Gewinnerliste ist voll.")


def _safe_cell(text: str) -> str:
    """Keine Formeln in Tabellenprogrammen (CSV-Injection)."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def winners_csv(winners: list[Winner], event_title: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Feier", "Runde", "Gewinnziel", "Karte", "Name", "nach Songs"])
    for winner in winners:
        writer.writerow([_safe_cell(event_title), winner.round, winner.target_label, winner.card,
                         _safe_cell(winner.name), winner.song_count])
    return buffer.getvalue()
