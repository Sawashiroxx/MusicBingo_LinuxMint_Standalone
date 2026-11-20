import re

from .links import normalize_link
from .models import Song


_SEPARATOR = re.compile(r"\s+[–—-]\s+")
_DASH = re.compile(r"\s+[–—]\s+")
_LINK_SUFFIX = re.compile(r"\s+\|\s+(\S+)\s*$")
# Kommentar: „# …“ immer; „#Wort“ nur ohne Interpret-Trenner. So bleiben „#Weihnachten“ als
# Abschnittsüberschrift und „#SELFIE – The Chainsmokers“ als Song erhalten.
_COMMENT = re.compile(r"^#(\s|#|$)")
# „Titel –“ am Zeilenende: Titel mit Bindestrich, aber ohne Interpret
_TRAILING_DASH = re.compile(r"\s+[–—]$")


def parse_song_line(line: str) -> Song | None:
    """Eine Zeile „Titel – Interpret“ mit optionalem „ | Link“ am Ende."""
    line = line.strip()
    if not line or _COMMENT.match(line):
        return None
    if line.startswith("#") and not (_SEPARATOR.search(line) or _TRAILING_DASH.search(line)):
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
    if _TRAILING_DASH.search(line):
        title, artist = _TRAILING_DASH.sub("", line).strip(), ""
    elif dashes:
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

    Leere Zeilen und Kommentare („# …“) werden übersprungen.
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


def _hyphens(text: str) -> str:
    return text.replace("–", "-").replace("—", "-")


def _reads_back(text: str, title: str, artist: str) -> bool:
    parsed = parse_song_line(text)
    return parsed is not None and (parsed.title, parsed.artist) == (title, artist)


def format_song(song: Song) -> str:
    """Eine Zeile, die parse_song_line wieder als denselben Song einliest.

    Dokumentierte Ersetzungen, wo die Zeile sonst anders gelesen würde: Gedankenstriche (– —) im
    Interpreten bzw. Titel werden als Bindestrich „-“ geschrieben (z. B. Titel „Wham! –“ mit
    Interpret), ein führendes „#“ eines Titels wie „# 1“ als „＃“ (sonst Kommentar).
    """
    title, artist = song.title, song.artist
    if _COMMENT.match(title):
        title = title.replace("#", "＃", 1)  # Titel „# 1“ wäre sonst ein Kommentar
    if artist:
        # Der letzte „ – “ trennt den Interpreten ab – im Interpreten selbst darf keiner stehen.
        candidates = [(title, _DASH.sub(lambda m: _hyphens(m.group()), artist)), (title, _hyphens(artist)), (_hyphens(title), _hyphens(artist))]
        lines = [f"{t} – {a}" for t, a in candidates]
    elif _SEPARATOR.search(title) or _TRAILING_DASH.search(title) or title.startswith("#"):
        # sonst würde „Stille Nacht - Heilige Nacht“ zerlegt bzw. „#SELFIE“ Kommentar
        candidates = [(title, ""), (_hyphens(title), "")]
        lines = [f"{t} –" for t, _a in candidates]
    else:
        candidates, lines = [(title, "")], [title]
    # Erste Schreibweise, die genau zurückgelesen wird; die letzte enthält keine Gedankenstriche mehr
    text = next((line for line, (t, a) in zip(lines, candidates) if _reads_back(line, t, a)), lines[-1])
    return f"{text} | {song.link}" if song.link else text


def format_songs(songs: list[Song]) -> str:
    return "\n".join(format_song(song) for song in songs)


def set_links_in_text(text: str, links: dict[str, str]) -> str:
    """Setzt in der Editor-Liste für die Songs (Schlüssel = Song.key) den Link bzw. entfernt ihn ("").

    Alle anderen Zeilen (Kommentare, Leerzeilen, andere Songs) bleiben unverändert.
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        song = parse_song_line(line)
        if song is not None and song.key in links:
            lines[index] = format_song(Song(song.title, song.artist, links[song.key]))
    return "\n".join(lines)
