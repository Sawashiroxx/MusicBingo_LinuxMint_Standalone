import math
import random

from .models import BingoCard, Song


class NotEnoughSongs(ValueError):
    pass


def required_songs(size: int, free_space: bool) -> int:
    if not isinstance(size, int) or isinstance(size, bool) or size not in (3, 4, 5):
        raise ValueError("Die Kartengröße muss 3, 4 oder 5 sein.")
    if not isinstance(free_space, bool):
        raise ValueError("Die Freifeld-Einstellung muss wahr oder falsch sein.")
    return size * size - int(free_space and size % 2 == 1)


def unique_card_capacity(songs: list[Song], size: int, free_space: bool) -> int:
    needed = required_songs(size, free_space)
    unique_names = {song.display_name.casefold() for song in songs}
    return math.comb(len(unique_names), needed) if len(unique_names) >= needed else 0


def _winning(
    card: BingoCard, size: int, free_space: bool, drawn_songs: list[Song], diagonal_wins: bool
) -> list[tuple[str, list[int]]]:
    if not isinstance(diagonal_wins, bool):
        raise ValueError("Die Diagonal-Regel muss wahr oder falsch sein.")
    needed = required_songs(size, free_space)
    if len(card.songs) != needed:
        raise ValueError("Die Bingokarte passt nicht zur gewählten Größe.")

    drawn = {song.display_name.casefold() for song in drawn_songs}
    marked: list[bool] = []
    song_index = 0
    free_index = size * size // 2
    has_free_space = free_space and size % 2 == 1
    for position in range(size * size):
        if has_free_space and position == free_index:
            marked.append(True)
        else:
            marked.append(card.songs[song_index].display_name.casefold() in drawn)
            song_index += 1

    lines: list[tuple[str, list[int]]] = []
    for row in range(size):
        lines.append((f"Reihe {row + 1}", [row * size + col for col in range(size)]))
    for col in range(size):
        lines.append((f"Spalte {chr(65 + col)}", [row * size + col for row in range(size)]))
    if diagonal_wins:
        lines.append(("Diagonale ↘", [i * size + i for i in range(size)]))
        lines.append(("Diagonale ↙", [i * size + size - i - 1 for i in range(size)]))
    return [(name, positions) for name, positions in lines if all(marked[p] for p in positions)]


def winning_lines(
    card: BingoCard,
    size: int,
    free_space: bool,
    drawn_songs: list[Song],
    diagonal_wins: bool = False,
) -> list[str]:
    """Gibt vollständige Reihen, Spalten und optional Diagonalen zurück."""
    return [name for name, _ in _winning(card, size, free_space, drawn_songs, diagonal_wins)]


def winning_cells(
    card: BingoCard,
    size: int,
    free_space: bool,
    drawn_songs: list[Song],
    diagonal_wins: bool = False,
) -> set[int]:
    """Positionen (0 … size²-1) aller Felder, die in einer vollständigen Linie liegen."""
    return {p for _, positions in _winning(card, size, free_space, drawn_songs, diagonal_wins) for p in positions}


def generate_cards(
    songs: list[Song], size: int, free_space: bool, count: int, rng=None
) -> list[BingoCard]:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 500:
        raise ValueError("Die Kartenanzahl muss zwischen 1 und 500 liegen.")
    needed = required_songs(size, free_space)
    unique_songs: list[Song] = []
    seen_songs: set[str] = set()
    for song in songs:
        key = song.display_name.casefold()
        if key not in seen_songs:
            unique_songs.append(song)
            seen_songs.add(key)
    if len(unique_songs) < needed:
        raise NotEnoughSongs(f"Mindestens {needed} eindeutige Songs werden benötigt.")
    capacity = math.comb(len(unique_songs), needed)
    if capacity < count:
        raise ValueError(
            f"Mit diesem Songpool sind höchstens {capacity} unterschiedliche Karten möglich."
        )
    randomizer = rng or random.SystemRandom()
    cards: list[BingoCard] = []
    used: set[tuple[str, ...]] = set()
    while len(cards) < count:
        chosen = randomizer.sample(unique_songs, needed)
        signature = tuple(sorted(song.display_name.casefold() for song in chosen))
        if signature in used:
            continue
        used.add(signature)
        cards.append(BingoCard(chosen))
    return cards
