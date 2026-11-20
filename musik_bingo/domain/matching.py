"""Zuordnung „was läuft gerade im Player“ → Song im Bingo-Pool.

Spotify liefert saubere Titel/Interpreten und eine Track-ID. YouTube im
Browser liefert oft nur „Interpret - Titel (Official Video)“ als Titel und
den Kanalnamen als Interpret. Die Zuordnung ist deshalb bewusst vorsichtig:
Lieber kein Treffer als ein falscher Song auf den Bingokarten.
"""
from dataclasses import dataclass

from .links import normalize_link
from .models import Song
from .text import artist_tokens, clean_title, normalize


@dataclass(frozen=True)
class PlayingTrack:
    title: str
    artist: str = ""
    url: str = ""  # Spotify-Track-URI oder Video-URL, falls vom Player gemeldet

    @property
    def label(self) -> str:
        return f"{self.title} – {self.artist}" if self.artist else self.title


# Interpreten, die für „jede Aufnahme“ stehen (Volkslieder): passen zu jedem gemeldeten Interpreten.
_WILDCARD_ARTISTS = {"", "traditional", "trad", "volkslied", "volksweise", "unbekannt", "various", "variousartists"}


def _is_wildcard(artist: str) -> bool:
    return normalize(artist) in _WILDCARD_ARTISTS


def _artist_matches(wanted: set[str], song_artist: str) -> bool:
    if not song_artist:
        return False
    if wanted & artist_tokens(song_artist):
        return True
    full = normalize(song_artist)
    # „The Pogues“ vs. Kanal „ThePoguesOfficial“, „Wham!“ vs. „WhamVEVO“ usw.
    return any(
        (len(token) >= 3 and token in full) or (len(full) >= 3 and full in token)
        for token in wanted
    )


class SongMatcher:
    def __init__(self, pool: list[Song]):
        self.pool = list(pool)
        self.by_link = {song.link: song for song in self.pool if song.link}
        self.by_title: dict[str, list[Song]] = {}
        for song in self.pool:
            self.by_title.setdefault(normalize(clean_title(song.title)), []).append(song)

    def _pick(self, title: str, artist_text: str) -> Song | None:
        key = normalize(clean_title(title))
        if not key:
            return None
        candidates = self.by_title.get(key, [])
        if not candidates:
            return None
        wanted = artist_tokens(artist_text) if artist_text else set()
        if not wanted:
            # Kein Interpret gemeldet: nur ein eindeutiger Titel ist sicher.
            return candidates[0] if len(candidates) == 1 else None
        exact = [song for song in candidates if _artist_matches(wanted, song.artist)]
        if exact:
            return exact[0] if len(exact) == 1 else None
        # Gemeldeter Interpret passt nicht: nur Songs ohne festen Interpreten
        # (leer/Traditional) zulassen – ein Cover eines anderen Künstlers wird NICHT gezogen.
        wildcard = [song for song in candidates if _is_wildcard(song.artist)]
        return wildcard[0] if len(wildcard) == 1 else None

    def find(self, track: PlayingTrack) -> Song | None:
        link = normalize_link(track.url)
        if link and link in self.by_link:
            return self.by_link[link]
        song = self._pick(track.title, track.artist)
        if song:
            return song
        # YouTube: „Interpret - Titel“ steckt im Titel, Interpret ist der Kanal.
        for separator in (" - ", " – ", " — ", " | "):
            if separator in track.title:
                left, right = track.title.split(separator, 1)
                for title, artist in ((right, left), (left, right)):
                    song = self._pick(title, f"{artist}, {track.artist}" if track.artist else artist)
                    if song:
                        return song
        return None


def compare_with_playlist(pool: list[Song], playlist: list[Song]) -> tuple[list[Song], list[Song]]:
    """Gibt (im Pool, aber nicht in der Playlist; in der Playlist, aber nicht im Pool) zurück."""
    matcher = SongMatcher(pool)
    found: set[str] = set()
    extra: list[Song] = []
    for item in playlist:
        song = matcher.find(PlayingTrack(item.title, item.artist, item.link))
        if song is None:
            extra.append(item)
        else:
            found.add(song.key)
    missing = [song for song in pool if song.key not in found]
    return missing, extra


def links_from_playlist(pool: list[Song], playlist: list[Song]) -> dict[str, str]:
    """Links aus einer Playlist für Songs des Pools, die noch keinen Link haben.

    Rückgabe: Song.key → Link. Zugeordnet wird wie beim Abgleich (Spotify-ID, Titel + Interpret);
    vorhandene Links (z. B. YouTube) werden nie überschrieben, unsichere Treffer nie geraten.
    """
    matcher = SongMatcher(pool)
    links: dict[str, str] = {}
    for item in playlist:
        link = normalize_link(item.link)
        if not link:
            continue
        song = matcher.find(PlayingTrack(item.title, item.artist, link))
        if song is not None and not song.link and song.key not in links:
            links[song.key] = link
    return links


def is_same_song(track: PlayingTrack | None, song: Song | None) -> bool:
    """Gleicher Song nach der Song-Identität (Titel + Interpret, ohne Groß-/Kleinschreibung).

    Für Spotifys „Relinking“: Dort kann derselbe Titel unter einer anderen Track-ID laufen.
    Bewusst streng (anders als SongMatcher), damit kein anderer Titel als „läuft“ gilt.
    """
    if track is None or song is None or not track.title.strip():
        return False
    return Song(track.title.strip(), track.artist.strip()).key == song.key
