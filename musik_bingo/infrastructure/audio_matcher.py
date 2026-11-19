from pathlib import Path
import re
import unicodedata

from musik_bingo.domain.models import Song


AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".wav", ".opus"}


def normalize_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return "".join(char for char in without_marks if char.isalnum())


def match_audio_files(songs: list[Song], folder: Path) -> tuple[dict[str, str], list[Song]]:
    """Ordnet nur eindeutige exakte Titel-Interpret-Dateinamen automatisch zu."""
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"Audioordner nicht gefunden: {folder}")

    # Titel und Interpret werden getrennt normalisiert. So kollidieren z. B.
    # „AB – C“ und „A – BC“ nicht zu demselben zusammengesetzten Dateinamen.
    files_by_pair: dict[tuple[str, str], list[Path]] = {}
    files_by_title: dict[str, list[Path]] = {}
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.casefold() in AUDIO_SUFFIXES:
            stem = path.stem
            files_by_title.setdefault(normalize_filename(stem), []).append(path)
            # Alle Trennstellen prüfen; das lässt Bindestriche innerhalb eines
            # Titels oder Interpreten zu und bleibt bei Mehrdeutigkeit vorsichtig.
            for match in re.finditer(r"\s+[-–—]\s+", stem):
                title = normalize_filename(stem[:match.start()])
                artist = normalize_filename(stem[match.end():])
                if title and artist:
                    files_by_pair.setdefault((title, artist), []).append(path)

    title_counts: dict[str, int] = {}
    pair_counts: dict[tuple[str, str], int] = {}
    for song in songs:
        title = normalize_filename(song.title)
        pair = (title, normalize_filename(song.artist))
        title_counts[title] = title_counts.get(title, 0) + 1
        pair_counts[pair] = pair_counts.get(pair, 0) + 1

    matched: dict[str, str] = {}
    unmatched: list[Song] = []
    for song in songs:
        title_name = normalize_filename(song.title)
        artist_name = normalize_filename(song.artist)
        if artist_name:
            pair = (title_name, artist_name)
            candidates = files_by_pair.get(pair, []) if pair_counts[pair] == 1 else []
            if not candidates and title_counts[title_name] == 1:
                candidates = files_by_title.get(title_name, [])
        else:
            candidates = files_by_title.get(title_name, []) if title_counts[title_name] == 1 else []
        if len(candidates) == 1:
            matched[song.display_name.casefold()] = str(candidates[0].resolve())
        else:
            unmatched.append(song)
    return matched, unmatched
