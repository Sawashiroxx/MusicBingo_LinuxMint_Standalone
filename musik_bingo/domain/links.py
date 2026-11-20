"""Links auf Spotify- und YouTube-Titel erkennen und vereinheitlichen.

Es werden nur zwei Linkarten akzeptiert, damit importierte Listen keine
beliebigen Adressen in die App tragen:

* Spotify: ``spotify:track:<ID>`` (auch aus ``open.spotify.com/…/track/<ID>``)
* YouTube: ``https://www.youtube.com/watch?v=<ID>`` (auch aus youtu.be, music.youtube.com)
"""
import re
from urllib.parse import parse_qs, quote, urlparse

_SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{22}$")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def normalize_link(value: str) -> str:
    """Gibt eine einheitliche Form des Links zurück oder "" bei unbekannten Links."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > 500:
        return ""
    lowered = value.lower()
    if lowered.startswith("spotify:track:"):
        track_id = value.split(":", 2)[2]
        return f"spotify:track:{track_id}" if _SPOTIFY_ID.match(track_id) else ""
    if not lowered.startswith(("http://", "https://")):
        return ""
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if host == "open.spotify.com":
        parts = [part for part in parsed.path.split("/") if part]
        if "track" in parts:
            index = parts.index("track")
            if index + 1 < len(parts) and _SPOTIFY_ID.match(parts[index + 1]):
                return f"spotify:track:{parts[index + 1]}"
        return ""
    video_id = ""
    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            video_id = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else ""
    if _YOUTUBE_ID.match(video_id or ""):
        return f"https://www.youtube.com/watch?v={video_id}"
    return ""


def parse_user_link(value: str) -> str:
    """Prüft einen eingefügten Link: vereinheitlichter Link, "" (= Link entfernen) oder ValueError."""
    if not isinstance(value, str):
        raise ValueError("Der Link muss Text sein.")
    value = value.strip()
    if not value:
        return ""
    normalized = normalize_link(value)
    if normalized:
        return normalized
    lowered = value.lower()
    for kind, name in (("album", "ein Album"), ("playlist", "eine Playlist"), ("artist", "einen Interpreten"),
                       ("episode", "eine Podcast-Folge"), ("show", "einen Podcast")):
        if ("spotify.com/" in lowered and f"/{kind}/" in lowered) or lowered.startswith(f"spotify:{kind}:"):
            return _reject(f"Das ist ein Link auf {name}, nicht auf einen einzelnen Titel. In Spotify per "
                           "Rechtsklick auf den Titel → Teilen → Songlink kopieren.")
    if lowered.startswith("spotify:track:") or "open.spotify.com/" in lowered:
        return _reject("Der Spotify-Link ist unvollständig – bitte den Songlink noch einmal kopieren.")
    return _reject("Kein gültiger Link. Erlaubt sind Spotify-Titel (open.spotify.com/track/… oder "
                   "spotify:track:…) und YouTube-Videos.")


def _reject(text: str) -> str:
    raise ValueError(text)


def is_spotify(link: str) -> bool:
    return link.startswith("spotify:track:")


def is_youtube(link: str) -> bool:
    return link.startswith("https://www.youtube.com/watch?v=")


def search_text(title: str, artist: str) -> str:
    return f"{artist} {title}".strip() if artist else title.strip()


def spotify_search_uri(title: str, artist: str) -> str:
    return "spotify:search:" + quote(search_text(title, artist), safe="")


def spotify_web_search_url(title: str, artist: str) -> str:
    return "https://open.spotify.com/search/" + quote(search_text(title, artist), safe="")


def youtube_search_url(title: str, artist: str) -> str:
    return "https://www.youtube.com/results?search_query=" + quote(search_text(title, artist), safe="")


