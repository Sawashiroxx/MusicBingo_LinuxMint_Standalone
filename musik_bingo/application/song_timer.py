"""Song-Timer: Nach einstellbaren Sekunden kurz auflösen und zum nächsten Song.

Reine Zustandslogik ohne GTK; die Oberfläche ruft einmal pro Sekunde tick() auf
und reagiert auf das zurückgegebene Ereignis.
"""
from dataclasses import dataclass

MAX_SECONDS = 600
MAX_REVEAL = 30

IDLE, PLAYING, REVEAL = "aus", "läuft", "auflösung"


@dataclass
class SongTimer:
    seconds: int = 0          # Spielzeit pro Song; 0 = Timer aus
    reveal_seconds: int = 5   # Auflösung (Titel auf dem Beamer) vor dem nächsten Song
    phase: str = IDLE
    remaining: int = 0
    paused: bool = False

    def __post_init__(self) -> None:
        self.configure(self.seconds, self.reveal_seconds)

    def configure(self, seconds: int, reveal_seconds: int) -> None:
        for value, limit, name in ((seconds, MAX_SECONDS, "Spielzeit"), (reveal_seconds, MAX_REVEAL, "Auflösung")):
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= limit:
                raise ValueError(f"{name} muss zwischen 0 und {limit} Sekunden liegen.")
        self.seconds = seconds
        self.reveal_seconds = reveal_seconds
        if not self.enabled:
            self.stop()

    @property
    def enabled(self) -> bool:
        return self.seconds > 0

    def start(self) -> None:
        """Nach jedem gezogenen Song aufrufen: Countdown beginnt neu (eine alte Pause endet)."""
        if not self.enabled:
            self.stop()
            return
        self.phase, self.remaining, self.paused = PLAYING, self.seconds, False

    def stop(self) -> None:
        self.phase, self.remaining, self.paused = IDLE, 0, False

    def pause(self) -> None:
        if self.phase != IDLE:
            self.paused = True

    def resume(self) -> None:
        self.paused = False

    def tick(self) -> str | None:
        """Eine Sekunde weiter. Rückgabe: "reveal" (Titel zeigen), "next" (nächster Song) oder None."""
        if self.phase == IDLE or self.paused:
            return None
        self.remaining -= 1
        if self.remaining > 0:
            return None
        if self.phase == PLAYING and self.reveal_seconds > 0:
            self.phase, self.remaining = REVEAL, self.reveal_seconds
            return "reveal"
        self.phase, self.remaining = IDLE, 0
        return "next"

    def label(self) -> str:
        if self.phase == IDLE:
            return "Timer aus" if not self.enabled else "Timer bereit"
        prefix = "Pausiert · " if self.paused else ""
        if self.phase == REVEAL:
            return f"{prefix}Auflösung · nächster Song in {self.remaining} s"
        return f"{prefix}noch {self.remaining} s"
