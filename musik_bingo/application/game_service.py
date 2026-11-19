from dataclasses import dataclass, field

from musik_bingo.domain.caller import Caller
from musik_bingo.domain.card_generator import generate_cards, required_songs, winning_lines
from musik_bingo.domain.models import BingoCard, Song
from musik_bingo.domain.forecast import WIN_TARGETS, Forecast, Guarantee, card_status, forecast, guarantee, target_reached
from musik_bingo.domain.song_list import format_songs, parse_songs

PLAYBACK_TARGETS = ("lokal", "spotify", "youtube")


@dataclass
class Game:
    songs: list[Song] = field(default_factory=list)
    cards: list[BingoCard] = field(default_factory=list)
    size: int = 5
    free_space: bool = True
    card_count: int = 30
    per_page: int = 2
    diagonal_wins: bool = False
    caller: Caller = field(default_factory=lambda: Caller([]))


class GameService:
    def __init__(self, game: Game | None = None):
        self.game = game or Game()
        self.song_text = format_songs(self.game.songs)
        self.card_size = self.game.size
        self.free_space = self.game.free_space
        self.card_count = self.game.card_count
        self.per_page = self.game.per_page
        self.diagonal_wins = self.game.diagonal_wins
        self.auto_play = False
        self.audio_files: dict[str, str] = {}
        # Wo wird ein gezogener Song abgespielt? lokal (GStreamer), spotify, youtube
        self.playback_target = "lokal"
        # Folgen-Modus: Der Player (Spotify/YouTube) spielt die Playlist,
        # die App zieht automatisch den gerade laufenden Song.
        self.follow_player = False
        self.player_name = ""
        # Gewinnziel der aktuellen Runde: reihe, zwei_reihen, volle_karte
        self.win_target = "reihe"

    def set_song_text(self, text: str) -> list[Song]:
        self.song_text = text
        return parse_songs(text)

    def create_cards(
        self, size: int, free_space: bool, count: int, diagonal_wins: bool | None = None
    ) -> list[BingoCard]:
        if diagonal_wins is None:
            diagonal_wins = self.diagonal_wins
        if not isinstance(diagonal_wins, bool):
            raise ValueError("Die Diagonal-Regel muss wahr oder falsch sein.")
        songs = parse_songs(self.song_text)
        cards = generate_cards(songs, size, free_space, count)
        # Erst nach erfolgreicher Validierung den aktiven Spielstand ersetzen.
        self.game.songs = songs
        self.game.cards = cards
        self.game.size = size
        self.game.free_space = bool(free_space and size % 2)
        self.game.card_count = count
        self.game.diagonal_wins = diagonal_wins
        self.card_size = size
        self.free_space = self.game.free_space
        self.card_count = count
        self.diagonal_wins = diagonal_wins
        self.game.caller = Caller(songs)
        return cards

    def check_bingo(self, card_number: int) -> list[str]:
        if (
            not isinstance(card_number, int)
            or isinstance(card_number, bool)
            or not 1 <= card_number <= len(self.game.cards)
        ):
            raise ValueError(f"Kartennummer muss zwischen 1 und {len(self.game.cards)} liegen.")
        return winning_lines(
            self.game.cards[card_number - 1],
            self.game.size,
            self.game.free_space,
            self.game.caller.drawn,
            self.game.diagonal_wins,
        )

    def set_win_target(self, target: str) -> None:
        if target not in WIN_TARGETS:
            raise ValueError("Unbekanntes Gewinnziel.")
        self.win_target = target

    def check_win(self, card_number: int) -> tuple[bool, list[str], bool]:
        """(Gewinnziel erreicht?, vollständige Linien, Karte voll?) für eine Kartennummer."""
        lines = self.check_bingo(card_number)
        game = self.game
        complete, full = card_status(game.cards[card_number - 1], game.size, game.free_space,
                                     game.caller.drawn, game.diagonal_wins)
        return target_reached(self.win_target, complete, full), lines, full

    def forecast(self, runs: int = 300) -> Forecast:
        game = self.game
        return forecast(game.cards, game.songs, game.size, game.free_space, game.diagonal_wins, runs)

    def guarantee(self) -> Guarantee:
        game = self.game
        return guarantee(game.cards, game.songs, game.size, game.free_space)

    def draw_song(self, song: Song) -> bool:
        """Markiert einen bestimmten Song als nächsten gezogenen (Folgen-Modus)."""
        return self.game.caller.draw_song(song)

    def set_playback_target(self, target: str) -> None:
        if target not in PLAYBACK_TARGETS:
            raise ValueError("Unbekanntes Wiedergabeziel.")
        self.playback_target = target

    def audio_file_for(self, song: Song | None) -> str | None:
        if song is None:
            return None
        return self.audio_files.get(song.display_name.casefold())

    def assign_audio_file(self, song: Song, path: str) -> None:
        if song not in self.game.songs:
            raise ValueError("Der Song gehört nicht zur laufenden Runde.")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Bitte eine gültige Audiodatei auswählen.")
        self.audio_files[song.display_name.casefold()] = path

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "song_text": self.song_text,
            "settings": {
                "card_size": self.card_size,
                "free_space": self.free_space,
                "card_count": self.card_count,
                "per_page": self.per_page,
                "diagonal_wins": self.diagonal_wins,
                "auto_play": self.auto_play,
                "playback_target": self.playback_target,
                "follow_player": self.follow_player,
                "player_name": self.player_name,
                "win_target": self.win_target,
            },
            "songs": [song.to_dict() for song in self.game.songs],
            "cards": [card.to_dict() for card in self.game.cards],
            "size": self.game.size,
            "free_space": self.game.free_space,
            "card_count": self.game.card_count,
            "per_page": self.game.per_page,
            "diagonal_wins": self.game.diagonal_wins,
            "caller_order": [song.to_dict() for song in self.game.caller.order],
            "caller_index": self.game.caller.index,
            "audio_files": self.audio_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameService":
        if not isinstance(data, dict):
            raise ValueError("Der Spielstand muss ein JSON-Objekt sein.")
        version = data.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise ValueError("Diese Spielstand-Version wird nicht unterstützt.")
        raw_songs = data.get("songs", [])
        if not isinstance(raw_songs, list) or len(raw_songs) > 2000:
            raise ValueError("Ungültige Songliste im Spielstand.")
        songs = [Song.from_dict(item) for item in raw_songs]
        song_keys = [song.display_name.casefold() for song in songs]
        if len(set(song_keys)) != len(song_keys):
            raise ValueError("Die Songliste im Spielstand enthält Duplikate.")
        size = data.get("size", 5)
        if not isinstance(size, int) or isinstance(size, bool):
            raise ValueError("Ungültige Kartengröße im Spielstand.")
        if size not in (3, 4, 5):
            raise ValueError("Ungültige Kartengröße im Spielstand.")
        free_space = data.get("free_space", False)
        if not isinstance(free_space, bool):
            raise ValueError("Ungültige Freifeld-Einstellung im Spielstand.")
        raw_cards = data.get("cards", [])
        if not isinstance(raw_cards, list) or len(raw_cards) > 500:
            raise ValueError("Ungültige Kartenanzahl im Spielstand.")
        cards = [BingoCard.from_dict(item) for item in raw_cards]
        expected_cells = required_songs(size, free_space)
        song_names = {song.display_name.casefold() for song in songs}
        card_signatures: set[tuple[str, ...]] = set()
        for card in cards:
            names = [song.display_name.casefold() for song in card.songs]
            signature = tuple(sorted(names))
            if (
                len(names) != expected_cells
                or len(set(names)) != expected_cells
                or any(name not in song_names for name in names)
                or signature in card_signatures
            ):
                raise ValueError("Eine Bingo-Karte im Spielstand passt nicht zur Songliste.")
            card_signatures.add(signature)
        has_caller_order = "caller_order" in data
        raw_caller_order = data.get("caller_order")
        if has_caller_order and not isinstance(raw_caller_order, list):
            raise ValueError("Ungültige Ziehreihenfolge im Spielstand.")
        caller_order = (
            [Song.from_dict(item) for item in raw_caller_order]
            if has_caller_order
            else None
        )
        caller_index = data.get("caller_index", -1)
        if not isinstance(caller_index, int) or isinstance(caller_index, bool):
            raise ValueError("Ungültiger Ziehfortschritt im Spielstand.")
        if not -1 <= caller_index < len(songs):
            raise ValueError("Ungültiger Ziehfortschritt im Spielstand.")
        if caller_order is None:
            if caller_index != -1:
                raise ValueError("Zum Ziehfortschritt fehlt die gespeicherte Reihenfolge.")
        elif (
            len(caller_order) != len(songs)
            or len(set(caller_order)) != len(caller_order)
            or set(caller_order) != set(songs)
        ):
            raise ValueError("Die Ziehreihenfolge passt nicht zum aktiven Songpool.")
        card_count = data.get("card_count", 30)
        if not isinstance(card_count, int) or isinstance(card_count, bool) or not 1 <= card_count <= 500:
            raise ValueError("Ungültige Kartenanzahl im Spielstand.")
        per_page = data.get("per_page", 2)
        if not isinstance(per_page, int) or isinstance(per_page, bool) or per_page not in (1, 2):
            raise ValueError("Ungültiges Drucklayout im Spielstand.")
        diagonal_wins = data.get("diagonal_wins", False)
        if not isinstance(diagonal_wins, bool):
            raise ValueError("Ungültige Diagonal-Regel im Spielstand.")
        game = Game(
            songs=songs,
            cards=cards,
            size=size,
            free_space=free_space,
            card_count=card_count,
            per_page=per_page,
            diagonal_wins=diagonal_wins,
            caller=Caller(
                songs,
                caller_order,
                caller_index,
            ),
        )
        service = cls(game)
        raw_audio_files = data.get("audio_files", {})
        if not isinstance(raw_audio_files, dict) or len(raw_audio_files) > 2000:
            raise ValueError("Ungültige Audiozuordnungen im Spielstand.")
        if any(not isinstance(key, str) or not isinstance(path, str) for key, path in raw_audio_files.items()):
            raise ValueError("Audiozuordnung muss Titel und Dateipfad als Text enthalten.")
        service.audio_files = {}
        for key, path in raw_audio_files.items():
            normalized_key = key.strip().casefold()
            normalized_path = path.strip()
            if not normalized_key or not normalized_path:
                continue
            if normalized_key in service.audio_files:
                raise ValueError("Der Spielstand enthält doppelte Audiozuordnungen.")
            service.audio_files[normalized_key] = normalized_path
        song_text = data.get("song_text", format_songs(songs))
        if not isinstance(song_text, str):
            raise ValueError("Die gespeicherte Songliste muss Text sein.")
        service.song_text = song_text
        settings = data.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError("Ungültige Einstellungen im Spielstand.")
        service.card_size = settings.get("card_size", size)
        if not isinstance(service.card_size, int) or isinstance(service.card_size, bool):
            raise ValueError("Ungültige vorbereitete Kartengröße im Spielstand.")
        if service.card_size not in (3, 4, 5):
            raise ValueError("Ungültige vorbereitete Kartengröße im Spielstand.")
        prepared_free_space = settings.get("free_space", free_space)
        if not isinstance(prepared_free_space, bool):
            raise ValueError("Ungültige Freifeld-Vorbereitung im Spielstand.")
        service.free_space = prepared_free_space
        service.card_count = settings.get("card_count", game.card_count)
        if (
            not isinstance(service.card_count, int)
            or isinstance(service.card_count, bool)
            or not 1 <= service.card_count <= 500
        ):
            raise ValueError("Ungültige vorbereitete Kartenanzahl im Spielstand.")
        service.per_page = settings.get("per_page", game.per_page)
        if not isinstance(service.per_page, int) or isinstance(service.per_page, bool) or service.per_page not in (1, 2):
            raise ValueError("Ungültiges vorbereitetes Drucklayout im Spielstand.")
        prepared_diagonal_wins = settings.get("diagonal_wins", game.diagonal_wins)
        if not isinstance(prepared_diagonal_wins, bool) or not isinstance(game.diagonal_wins, bool):
            raise ValueError("Ungültige Diagonal-Regel im Spielstand.")
        service.diagonal_wins = prepared_diagonal_wins
        prepared_auto_play = settings.get("auto_play", False)
        if not isinstance(prepared_auto_play, bool):
            raise ValueError("Ungültige Autoplay-Einstellung im Spielstand.")
        service.auto_play = prepared_auto_play
        playback_target = settings.get("playback_target", "lokal")
        if playback_target not in PLAYBACK_TARGETS:
            raise ValueError("Ungültiges Wiedergabeziel im Spielstand.")
        service.playback_target = playback_target
        follow_player = settings.get("follow_player", False)
        if not isinstance(follow_player, bool):
            raise ValueError("Ungültige Player-Folgen-Einstellung im Spielstand.")
        service.follow_player = follow_player
        player_name = settings.get("player_name", "")
        if not isinstance(player_name, str) or len(player_name) > 255:
            raise ValueError("Ungültiger Playername im Spielstand.")
        service.player_name = player_name
        win_target = settings.get("win_target", "reihe")
        if win_target not in WIN_TARGETS:
            raise ValueError("Ungültiges Gewinnziel im Spielstand.")
        service.win_target = win_target
        return service
