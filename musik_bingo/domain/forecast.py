"""Spielprognose und Gewinngarantie.

Beantwortet vor dem Spiel: Nach wie vielen Songs gibt es den ersten Gewinner
(1 Reihe, 2 Reihen, volle Karte)? Und ist garantiert, dass überhaupt jemand
gewinnen kann?

Schneller Ansatz: Für einen zufälligen Spielverlauf kennt man die Ziehposition
jedes Songs. Eine Linie ist voll, sobald ihr zuletzt gezogenes Feld kommt
(Maximum der Positionen). So lässt sich ein ganzer Abend mit 150 Karten in
Millisekunden simulieren – ohne Song für Song nachzuprüfen.
"""
import random
import statistics
from dataclasses import dataclass

from .card_generator import required_songs
from .models import BingoCard, Song

WIN_TARGETS = ("reihe", "zwei_reihen", "volle_karte")
WIN_TARGET_LABELS = {"reihe": "1 Reihe", "zwei_reihen": "2 Reihen", "volle_karte": "Volle Karte"}


@dataclass(frozen=True)
class StageForecast:
    median: int     # typischer Song, bei dem der erste Gewinner feststeht
    early: int      # 10 % der Spiele sind schon hier entschieden
    late: int       # 90 % der Spiele sind spätestens hier entschieden
    worst: int      # spätester beobachteter Fall
    winners: float  # Ø Anzahl gleichzeitiger Gewinner


@dataclass(frozen=True)
class Forecast:
    pool_size: int
    stages: dict[str, StageForecast]


@dataclass(frozen=True)
class Guarantee:
    ok: bool
    problems: tuple[str, ...]


def _lines(size: int, diagonals: bool) -> list[list[int]]:
    lines = [[row * size + col for col in range(size)] for row in range(size)]
    lines += [[row * size + col for row in range(size)] for col in range(size)]
    if diagonals:
        lines.append([i * size + i for i in range(size)])
        lines.append([i * size + size - 1 - i for i in range(size)])
    return lines


def _cell_keys(card: BingoCard, size: int, free_space: bool) -> list[str | None]:
    """Song-Schlüssel je Feld; None = Freifeld."""
    free = free_space and size % 2 == 1
    songs = iter(card.songs)
    return [None if free and index == size * size // 2 else next(songs).key for index in range(size * size)]


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1) + 0.5))]


def forecast(cards: list[BingoCard], pool: list[Song], size: int, free_space: bool,
             diagonals: bool = False, runs: int = 300, rng: random.Random | None = None) -> Forecast:
    """Simuliert ``runs`` zufällige Spielverläufe und fasst die Gewinnzeitpunkte zusammen."""
    if not cards or not pool:
        raise ValueError("Für eine Prognose werden Karten und ein Songpool benötigt.")
    if not isinstance(runs, int) or isinstance(runs, bool) or not 1 <= runs <= 10_000:
        raise ValueError("Die Zahl der Simulationsläufe muss zwischen 1 und 10000 liegen.")
    randomizer = rng or random.Random()  # noqa: S311 – Simulation, keine Sicherheitsfunktion
    keys = [song.key for song in pool]
    lines = _lines(size, diagonals)
    layouts = [_cell_keys(card, size, free_space) for card in cards]
    firsts: dict[str, list[int]] = {target: [] for target in WIN_TARGETS}
    winners: dict[str, list[int]] = {target: [] for target in WIN_TARGETS}
    for _ in range(runs):
        order = keys[:]
        randomizer.shuffle(order)
        position = {key: index + 1 for index, key in enumerate(order)}
        per_card = {target: [] for target in WIN_TARGETS}
        for layout in layouts:
            times = [0 if key is None else position.get(key, len(keys) + 1) for key in layout]
            line_times = sorted(max(times[cell] for cell in line) for line in lines)
            per_card["reihe"].append(line_times[0])
            per_card["zwei_reihen"].append(line_times[1])
            per_card["volle_karte"].append(max(times))
        for target, values in per_card.items():
            first = min(values)
            firsts[target].append(first)
            winners[target].append(values.count(first))
    stages = {
        target: StageForecast(
            median=int(statistics.median(firsts[target])),
            early=_percentile(firsts[target], 0.1),
            late=_percentile(firsts[target], 0.9),
            worst=max(firsts[target]),
            winners=round(statistics.mean(winners[target]), 1),
        )
        for target in WIN_TARGETS
    }
    return Forecast(len(keys), stages)


def guarantee(cards: list[BingoCard], pool: list[Song], size: int, free_space: bool) -> Guarantee:
    """Prüft, dass jedes Gewinnziel spätestens nach dem letzten Song erreicht wird.

    Das gilt genau dann, wenn jeder Song auf jeder Karte auch im Pool (= der
    Playlist, die gespielt wird) steht und die Karten vollständig sind. Dann ist
    spätestens nach dem letzten Song jede Karte voll – es gibt immer einen Gewinner.
    """
    problems: list[str] = []
    if not cards:
        problems.append("Es gibt keine Karten.")
    pool_keys = {song.key for song in pool}
    needed = required_songs(size, free_space)
    for number, card in enumerate(cards, start=1):
        if len(card.songs) != needed:
            problems.append(f"Karte #{number} hat {len(card.songs)} statt {needed} Songs.")
        missing = [song.display_name for song in card.songs if song.key not in pool_keys]
        if missing:
            problems.append(f"Karte #{number}: nicht in der Playlist: {', '.join(missing[:3])}")
        if len(problems) >= 20:
            break
    return Guarantee(not problems, tuple(problems))


def card_status(card: BingoCard, size: int, free_space: bool, drawn: list[Song],
                diagonals: bool = False) -> tuple[int, bool]:
    """(Anzahl vollständiger Linien, Karte komplett voll?) für die Bingo-Prüfung."""
    drawn_keys = {song.key for song in drawn}
    marked = [key is None or key in drawn_keys for key in _cell_keys(card, size, free_space)]
    complete = sum(1 for line in _lines(size, diagonals) if all(marked[cell] for cell in line))
    return complete, all(marked)


def missing_to_target(card: BingoCard, size: int, free_space: bool, drawn: list[Song], target: str,
                      diagonals: bool = False) -> int:
    """Wie viele Songs dieser Karte fehlen mindestens noch bis zum Gewinnziel? 0 = erreicht.

    „1 Reihe“: die Linie mit den wenigsten offenen Feldern. „2 Reihen“: das Linienpaar mit den wenigsten
    offenen Feldern zusammen (Kreuzungsfelder zählen einmal). „Volle Karte“: alle offenen Felder.
    """
    if target not in WIN_TARGETS:
        raise ValueError("Unbekanntes Gewinnziel.")
    drawn_keys = {song.key for song in drawn}
    open_cells = {index for index, key in enumerate(_cell_keys(card, size, free_space))
                  if key is not None and key not in drawn_keys}
    if target == "volle_karte":
        return len(open_cells)
    open_lines = [open_cells.intersection(line) for line in _lines(size, diagonals)]
    if target == "reihe":
        return min(len(cells) for cells in open_lines)
    return min(len(first | second) for index, first in enumerate(open_lines) for second in open_lines[index + 1:])


def reached_at(card: BingoCard, size: int, free_space: bool, drawn: list[Song], target: str,
               diagonals: bool = False) -> int | None:
    """Bei welchem gezogenen Song (1, 2, …) hat diese Karte das Gewinnziel erreicht? None = noch nicht.

    Damit lässt sich ein echter Gleichstand (gleicher Song) von einem übersehenen früheren Gewinn unterscheiden.
    """
    if target not in WIN_TARGETS:
        raise ValueError("Unbekanntes Gewinnziel.")
    position = {song.key: index for index, song in enumerate(drawn, start=1)}
    times = [0 if key is None else position.get(key) for key in _cell_keys(card, size, free_space)]
    if target == "volle_karte":
        return None if None in times else max(times)
    done = sorted(max(times[cell] for cell in line) for line in _lines(size, diagonals)
                  if all(times[cell] is not None for cell in line))
    needed = 1 if target == "reihe" else 2
    return done[needed - 1] if len(done) >= needed else None


def target_reached(target: str, complete_lines: int, full: bool) -> bool:
    if target not in WIN_TARGETS:
        raise ValueError("Unbekanntes Gewinnziel.")
    return {"reihe": complete_lines >= 1, "zwei_reihen": complete_lines >= 2, "volle_karte": full}[target]


def recommend_pool_size(target_minutes: int, minutes_per_song: float = 1.0) -> int:
    """Faustregel aus der Simulation (5×5 mit Freifeld): „Volle Karte“ fällt nach ≈ 84 % des Pools."""
    if target_minutes <= 0 or minutes_per_song <= 0:
        raise ValueError("Spieldauer und Songlänge müssen positiv sein.")
    return max(24, round(target_minutes / minutes_per_song / 0.84))
