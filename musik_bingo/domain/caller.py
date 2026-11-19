import random

from .models import Song


class Caller:
    def __init__(self, pool: list[Song], order: list[Song] | None = None, index: int = -1):
        self.pool = []
        seen: set[str] = set()
        for song in pool:
            key = song.display_name.casefold()
            if key not in seen:
                self.pool.append(song)
                seen.add(key)
        self.order = list(order) if order is not None else random.SystemRandom().sample(self.pool, len(self.pool))
        if len(self.order) != len(self.pool) or set(self.order) != set(self.pool):
            raise ValueError("Die Ziehreihenfolge muss jeden Song des Pools genau einmal enthalten.")
        if not isinstance(index, int) or isinstance(index, bool) or not -1 <= index < len(self.order):
            raise ValueError("Der Ziehindex liegt außerhalb der Ziehreihenfolge.")
        # Gleiche Objekte wie im Pool verwenden, damit Links (Spotify/YouTube) erhalten bleiben.
        by_key = {song.display_name.casefold(): song for song in self.pool}
        self.order = [by_key.get(song.display_name.casefold(), song) for song in self.order]
        self.index = index

    @property
    def current(self) -> Song | None:
        return self.order[self.index] if self.index >= 0 else None

    @property
    def drawn(self) -> list[Song]:
        return self.order[: self.index + 1]

    def draw_next(self) -> Song | None:
        if self.index + 1 >= len(self.order):
            return None
        self.index += 1
        return self.current

    def draw_song(self, song: Song) -> bool:
        """Zieht genau diesen Song als nächsten (Player-Folgen-Modus).

        Der Song wird in der Reihenfolge an die nächste Position verschoben.
        Bereits gezogene oder unbekannte Songs ändern nichts (False).
        """
        key = song.display_name.casefold()
        position = next(
            (i for i, item in enumerate(self.order) if item.display_name.casefold() == key), None
        )
        if position is None or position <= self.index:
            return False
        target = self.index + 1
        self.order.insert(target, self.order.pop(position))
        self.index = target
        return True

    def is_drawn(self, song: Song) -> bool:
        key = song.display_name.casefold()
        return any(item.display_name.casefold() == key for item in self.drawn)

    def undo(self) -> Song | None:
        if self.index < 0:
            return None
        song = self.current
        self.index -= 1
        return song

    def reshuffle(self) -> None:
        self.order = random.SystemRandom().sample(self.pool, len(self.pool))
        self.index = -1
