from dataclasses import dataclass, field

from .links import normalize_link


@dataclass(frozen=True)
class Song:
    """Ein Song. Gleichheit hängt nur an Titel und Interpret, nicht am Link."""

    title: str
    artist: str = ""
    # Optionaler Verweis auf die Quelle (spotify:track:… oder YouTube-URL).
    # compare=False: derselbe Song mit/ohne Link bleibt derselbe Bingo-Song.
    link: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        # Nur bekannte, vereinheitlichte Links (Spotify-Track, YouTube-Video) zulassen.
        normalized = normalize_link(self.link) if self.link else ""
        if normalized != self.link:
            object.__setattr__(self, "link", normalized)

    @property
    def display_name(self) -> str:
        return f"{self.title} – {self.artist}" if self.artist else self.title

    @property
    def key(self) -> str:
        return self.display_name.casefold()

    def to_dict(self) -> dict[str, str]:
        data = {"title": self.title, "artist": self.artist}
        if self.link:
            data["link"] = self.link
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Song":
        if not isinstance(data, dict):
            raise ValueError("Ungültiger Song im Spielstand.")
        title = data.get("title", "")
        artist = data.get("artist", "")
        link = data.get("link", "")
        if not isinstance(title, str) or not isinstance(artist, str) or not isinstance(link, str):
            raise ValueError("Songtitel, Interpret und Link müssen Text sein.")
        title = title.strip()
        artist = artist.strip()
        if not title:
            raise ValueError("Ein Song im Spielstand hat keinen Titel.")
        if len(title) > 300 or len(artist) > 300:
            raise ValueError("Ein Songtitel oder Interpret im Spielstand ist zu lang.")
        return cls(title, artist, normalize_link(link))


@dataclass
class BingoCard:
    songs: list[Song]

    def to_dict(self) -> dict:
        return {"songs": [song.to_dict() for song in self.songs]}

    @classmethod
    def from_dict(cls, data: dict) -> "BingoCard":
        if not isinstance(data, dict) or not isinstance(data.get("songs"), list):
            raise ValueError("Ungültige Bingokarte im Spielstand.")
        return cls([Song.from_dict(song) for song in data["songs"]])
