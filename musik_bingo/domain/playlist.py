"""Playlists einlesen (CSV, M3U, Text) und als Playlist ausgeben.

Unterstützt u. a. CSV-Exporte von Spotify-Playlists (Exportify, TuneMyMusic,
Soundiiz), kopierte YouTube-Titel („Interpret - Titel (Official Video)“) und
M3U-Playlists aus VLC, Rhythmbox oder Audacious. Keine Netzwerkzugriffe.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath

from .links import normalize_link
from .models import Song
from .text import clean_title, strip_leading_number

ORDER_AUTO = "auto"
ORDER_TITLE_ARTIST = "titel_interpret"
ORDER_ARTIST_TITLE = "interpret_titel"
ORDERS = (ORDER_AUTO, ORDER_TITLE_ARTIST, ORDER_ARTIST_TITLE)

MAX_IMPORT_SONGS = 2000

_URL = re.compile(r"(?:https?://\S+|spotify:track:[A-Za-z0-9]+)")
_EN_DASH = re.compile(r"\s+[–—]\s+")
_HYPHEN = re.compile(r"\s+-\s+")

_TITLE_COLUMNS = ("track name", "titel", "title", "song", "songtitel", "track", "name", "song name")
_ARTIST_COLUMNS = ("artist name(s)", "artist name", "artist", "artists", "interpret", "künstler", "kuenstler", "band")
_LINK_COLUMNS = ("track uri", "spotify uri", "uri", "spotify id", "url", "link", "youtube url", "spotify url")


@dataclass
class ImportResult:
    songs: list[Song] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    duplicates: int = 0
    format_name: str = ""


def _split(text: str, order: str) -> tuple[str, str]:
    """Trennt „A – B“ bzw. „A - B“ je nach Reihenfolge in (Titel, Interpret)."""
    if order == ORDER_AUTO:
        # Eigenes Format nutzt den Gedankenstrich („Titel – Interpret“),
        # YouTube und fast alle Exporte „Interpret - Titel“.
        if _EN_DASH.search(text):
            parts = _EN_DASH.split(text, maxsplit=1)
            return parts[0].strip(), parts[1].strip()
        order = ORDER_ARTIST_TITLE
    pattern = re.compile(r"\s+[–—-]\s+")
    parts = pattern.split(text, maxsplit=1)
    if len(parts) == 1:
        return text.strip(), ""
    first, second = parts[0].strip(), parts[1].strip()
    return (first, second) if order == ORDER_TITLE_ARTIST else (second, first)


def _make_song(title: str, artist: str, link: str = "") -> Song | None:
    title = clean_title(title.strip().strip('"').strip())
    artist = artist.strip().strip('"').strip()
    if artist.casefold().endswith(" - topic"):
        artist = artist[: -len(" - topic")].strip()
    if not title:
        return None
    return Song(title[:300], artist[:300], normalize_link(link))


class _Collector:
    def __init__(self, format_name: str):
        self.result = ImportResult(format_name=format_name)
        self.seen: set[str] = set()

    def add(self, song: Song | None, raw: str) -> None:
        if song is None:
            if raw.strip():
                self.result.skipped.append(raw.strip()[:120])
            return
        if song.key in self.seen:
            self.result.duplicates += 1
            return
        if len(self.result.songs) >= MAX_IMPORT_SONGS:
            self.result.skipped.append(f"{song.display_name} (mehr als {MAX_IMPORT_SONGS} Songs)")
            return
        self.seen.add(song.key)
        self.result.songs.append(song)


def parse_text(text: str, order: str = ORDER_AUTO) -> ImportResult:
    """Eine Zeile pro Song; Links (Spotify/YouTube) irgendwo in der Zeile werden übernommen."""
    if order not in ORDERS:
        raise ValueError("Unbekannte Reihenfolge für Titel und Interpret.")
    collector = _Collector("Textliste")
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        link = ""
        for match in _URL.finditer(line):
            candidate = normalize_link(match.group(0).rstrip(".,;)"))
            if candidate and not link:
                link = candidate
        line = _URL.sub("", line).strip(" |\t")
        line = strip_leading_number(line).strip()
        if not line:
            collector.add(None, raw)  # nur ein Link ohne Titel: offline nicht auflösbar
            continue
        title, artist = _split(line, order)
        collector.add(_make_song(title, artist, link), raw)
    return collector.result


def _find_column(header: list[str], names: tuple[str, ...]) -> int | None:
    lowered = [column.strip().strip("﻿").casefold() for column in header]
    for name in names:
        if name in lowered:
            return lowered.index(name)
    return None


def parse_csv(text: str) -> ImportResult:
    """CSV mit Kopfzeile (Spalten z. B. „Track Name“, „Artist Name(s)“, „Track URI“)."""
    text = text.lstrip("﻿")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = list(csv.reader(io.StringIO(text), dialect))
    except csv.Error as error:
        raise ValueError(f"Die CSV-Datei ist beschädigt oder ungewöhnlich aufgebaut: {error}") from error
    collector = _Collector("CSV")
    if not rows:
        return collector.result
    header = rows[0]
    title_col = _find_column(header, _TITLE_COLUMNS)
    artist_col = _find_column(header, _ARTIST_COLUMNS)
    link_col = _find_column(header, _LINK_COLUMNS)
    if title_col is None:
        raise ValueError(
            "In der CSV-Datei wurde keine Titelspalte gefunden "
            "(erwartet z. B. „Track Name“, „Titel“ oder „Title“)."
        )
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        def cell(index: int | None) -> str:
            return row[index] if index is not None and index < len(row) else ""
        artist = cell(artist_col)
        # Exportify trennt mehrere Interpreten mit Komma; für die Karte reicht das so.
        song = _make_song(cell(title_col), artist, cell(link_col))
        collector.add(song, ";".join(row))
    return collector.result


def parse_m3u(text: str, order: str = ORDER_ARTIST_TITLE) -> ImportResult:
    """M3U/M3U8: #EXTINF-Angaben, sonst Dateinamen „Interpret - Titel.mp3“."""
    collector = _Collector("M3U-Playlist")
    pending: str | None = None
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line == "#EXTM3U":
            continue
        if line.upper().startswith("#EXTINF:"):
            info = line.split(",", 1)
            pending = info[1].strip() if len(info) > 1 else ""
            continue
        if line.startswith("#"):
            continue
        link = normalize_link(line)
        if pending:
            title, artist = _split(pending, order)
        else:
            if link:
                collector.add(None, raw)  # reine URL ohne Titelangabe
                continue
            path = PureWindowsPath(line) if "\\" in line else PurePosixPath(line)
            title, artist = _split(path.stem, order)
        pending = None
        collector.add(_make_song(title, artist, link), raw)
    return collector.result


def parse_playlist(text: str, filename: str = "", order: str = ORDER_AUTO) -> ImportResult:
    """Wählt den passenden Leser anhand der Dateiendung bzw. des Inhalts."""
    lower = filename.casefold()
    stripped = text.lstrip("﻿").lstrip()
    if lower.endswith((".m3u", ".m3u8")) or stripped.startswith("#EXTM3U"):
        return parse_m3u(text, ORDER_ARTIST_TITLE if order == ORDER_AUTO else order)
    if lower.endswith((".csv", ".tsv")):
        return parse_csv(text)
    return parse_text(text, order)


def from_player_tracks(tracks) -> ImportResult:
    """Vom Player eingelesene Titel (Objekte mit title, artist, url) bereinigen.

    Spotify liefert Titel und Interpret getrennt. YouTube im Browser liefert
    meist „Interpret - Titel (Official Video)“ als Titel und den Kanal als
    Interpret – dann wird der Titel zerlegt und der Kanalname verworfen.
    """
    collector = _Collector("Player")
    for track in tracks:
        title, artist, url = track.title or "", track.artist or "", track.url or ""
        link = normalize_link(url)
        if not link.startswith("spotify:") and re.search(r"\s[-–—]\s", title):
            title, artist = _split(title, ORDER_ARTIST_TITLE)
        collector.add(_make_song(title, artist, link), f"{title} {artist}")
    return collector.result


# ---------------------------------------------------------------- Export


def to_text(songs: list[Song]) -> str:
    """„Interpret - Titel“ pro Zeile – das verstehen TuneMyMusic, Soundiiz & Co.
    für den Import in Spotify- oder YouTube-Playlists."""
    lines = [f"{song.artist} - {song.title}" if song.artist else song.title for song in songs]
    return "\n".join(lines) + ("\n" if lines else "")


def to_csv(songs: list[Song]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Track Name", "Artist Name(s)", "Track URI"])
    for song in songs:
        writer.writerow([song.title, song.artist, song.link])
    return buffer.getvalue()


def to_m3u(songs: list[Song], audio_files: dict[str, str]) -> tuple[str, int]:
    """M3U mit lokalen Dateien bzw. YouTube-Links. Gibt (Inhalt, Anzahl ausgelassen) zurück."""
    lines = ["#EXTM3U"]
    skipped = 0
    for song in songs:
        target = audio_files.get(song.key) or (song.link if song.link.startswith("https://") else "")
        if not target:
            skipped += 1
            continue
        label = f"{song.artist} - {song.title}" if song.artist else song.title
        lines.append(f"#EXTINF:-1,{label}")
        lines.append(target)
    return "\n".join(lines) + "\n", skipped
