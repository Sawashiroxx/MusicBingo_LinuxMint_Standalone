import re

from .links import normalize_link
from .models import Song


_SEPARATOR = re.compile(r"\s+[–—-]\s+")
_DASH = re.compile(r"\s+[–—]\s+")
_LINK_SUFFIX = re.compile(r"\s+\|\s+(\S+)\s*$")


def parse_song_line(line: str) -> Song | None:
    """Eine Zeile „Titel – Interpret“ mit optionalem „ | Link“ am Ende."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    link = ""
    match = _LINK_SUFFIX.search(line)
    if match:
        normalized = normalize_link(match.group(1))
        if normalized:
            link = normalized
            line = line[: match.start()].strip()
    # Das eigene Format trennt mit Gedankenstrich „ – “. Ist einer vorhanden, gilt der
    # letzte; so bleiben Bindestriche im Titel erhalten („Song - 1984 Version – Band“).
    dashes = list(_DASH.finditer(line))
    if dashes:
        last = dashes[-1]
        title, artist = line[: last.start()].strip(), line[last.end():].strip()
    else:
        parts = _SEPARATOR.split(line, maxsplit=1)
        title = parts[0].strip()
        artist = parts[1].strip() if len(parts) > 1 else ""
    if not title:
        return None
    return Song(title[:300], artist[:300], link)


def parse_songs(text: str) -> list[Song]:
    """Liest pro Zeile einen Titel und optional Interpret und Link ein.

    Leere Zeilen und Zeilen, die mit # beginnen, werden übersprungen.
    Doppelte Titel/Interpreten werden ohne Groß-/Kleinschreibung entfernt.
    """
    songs: list[Song] = []
    seen: set[str] = set()
    for line in text.splitlines():
        song = parse_song_line(line)
        if song is not None and song.key not in seen:
            songs.append(song)
            seen.add(song.key)
    return songs


def format_song(song: Song) -> str:
    return f"{song.display_name} | {song.link}" if song.link else song.display_name


def format_songs(songs: list[Song]) -> str:
    return "\n".join(format_song(song) for song in songs)
