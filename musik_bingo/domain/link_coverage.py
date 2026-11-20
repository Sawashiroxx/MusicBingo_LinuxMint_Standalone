"""Wie viele Songs lassen sich direkt abspielen? (Spotify-/YouTube-Links einer Songliste)"""
from dataclasses import dataclass

from .links import is_spotify, is_youtube
from .models import Song


@dataclass(frozen=True)
class LinkCoverage:
    total: int
    spotify: int
    youtube: int
    without: int
    # Songs ohne Spotify-Link in der Reihenfolge der Liste (auch die mit YouTube-Link)
    missing_spotify: tuple[Song, ...]

    @property
    def complete(self) -> bool:
        """Jeder Song hat einen Spotify-Link."""
        return self.spotify == self.total


def link_coverage(songs: list[Song]) -> LinkCoverage:
    """Zählt Songs mit Spotify-Link, mit YouTube-Link und ohne Link. Doppelte zählen einmal."""
    seen: set[str] = set()
    spotify = youtube = without = 0
    missing: list[Song] = []
    for song in songs:
        if song.key in seen:
            continue
        seen.add(song.key)
        if is_spotify(song.link):
            spotify += 1
            continue
        if is_youtube(song.link):
            youtube += 1
        else:
            without += 1
        missing.append(song)
    return LinkCoverage(len(seen), spotify, youtube, without, tuple(missing))
