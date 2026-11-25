from dataclasses import dataclass, field, replace

from musik_bingo.application.song_timer import SongTimer

from musik_bingo.domain.caller import Caller
from musik_bingo.domain.card_generator import generate_cards, required_songs, winning_lines
from musik_bingo.domain.models import BingoCard, Song
from musik_bingo.domain.forecast import (
    WIN_TARGETS, Forecast, Guarantee, card_status, forecast, guarantee, missing_to_target, reached_at, target_reached,
)
from musik_bingo.domain.evening import (
    DEFAULT_TITLE, MAX_NAME_LENGTH, MAX_WINNERS, Winner, check_new_winner, clean_event_title, clean_text, next_stage,
)
from musik_bingo.domain.links import parse_user_link
from musik_bingo.domain.song_list import format_songs, parse_songs, set_links_in_text

# Obergrenze pro Runde – identisch mit der Prüfung beim Laden, sonst ließe sich ein
# Spielstand speichern, der beim nächsten Start nicht mehr geladen werden kann.
MAX_GAME_SONGS = 2000
PLAYBACK_TARGETS = ("lokal", "spotify", "youtube")
# Spielstände aus 2.4.x: YouTube Music gibt es nicht mehr → normales YouTube
LEGACY_TARGETS = {"ytmusic": "youtube"}


@dataclass(frozen=True)
class TargetStatus:
    """Gewinnkontrolle für die Spielleitung: Welche Karten haben das aktuelle Ziel erreicht?"""
    # (Kartennummer, Song-Nr., bei dem das Ziel erreicht wurde) – noch nicht eingetragen, früheste zuerst
    reached: tuple[tuple[int, int], ...]
    entered: tuple[int, ...]       # in dieser Runde und Stufe schon als Gewinner eingetragen
    entered_open: tuple[int, ...]  # davon nach „Zurück“ nicht mehr am Ziel
    earlier: tuple[int, ...]       # Karten aus ``reached``, die schon eine andere Runde/Stufe gewonnen haben
    one_missing: int               # Karten (nicht eingetragen), denen genau noch ein Song fehlt

    @property
    def tied(self) -> tuple[int, ...]:
        """Karten, die beim frühesten Song gleichzeitig ans Ziel kamen – nur bei mehr als einer ein Gleichstand."""
        if not self.reached:
            return ()
        first = self.reached[0][1]
        cards = tuple(card for card, song in self.reached if song == first)
        return cards if len(cards) > 1 else ()


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
        # Wo wird ein gezogener Song abgespielt? lokal (GStreamer), spotify oder youtube
        self.playback_target = "lokal"
        # Folgen-Modus: Der Player (Spotify/YouTube) spielt die Playlist,
        # die App zieht automatisch den gerade laufenden Song.
        self.follow_player = False
        self.player_name = ""
        # Gewinnziel der aktuellen Runde: reihe, zwei_reihen, volle_karte
        self.win_target = "reihe"
        # Gewinnziel, mit dem eine Runde beginnt: das Ziel, das vor dem ersten Song der Runde gewählt war.
        # Neue Runden starten wieder damit – wer den Abend nur mit „Volle Karte“ spielt, muss es nicht
        # vor jeder Runde neu einstellen.
        self.round_start_target = "reihe"
        # Ablauf des Abends
        self.event_title = DEFAULT_TITLE
        self.round_number = 1
        self.winners: list[Winner] = []
        # Song-Timer (0 = aus) und Auflösungszeit für den Beamer
        self.timer_seconds = 0
        self.reveal_seconds = 5
        # Läuft die Spielzeit des Song-Timers ab, wird die Wiedergabe pausiert (Spotify/lokal)
        self.pause_after_timer = True
        # Titel auf dem Beamer aufdecken (Taste T / Auflösung des Timers). Aus: Die Gäste sehen nie einen
        # Songtitel – auch nicht in „Zuletzt“. Die Spielleitung sieht ihn weiter im Hauptfenster.
        self.beamer_reveal = True

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
        if len(songs) > MAX_GAME_SONGS:
            raise ValueError(f"Höchstens {MAX_GAME_SONGS} Songs pro Runde (die Liste hat {len(songs)}).")
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
        self._limit_audio_files()
        # Neue Karten = neuer Abend: Gewinner gehören zu den alten Karten (liegen in der Sicherung).
        self.round_number = 1
        self.win_target = "reihe"
        self.round_start_target = "reihe"
        self.winners = []
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
        """Gewinnziel von Hand wählen. Vor dem ersten Song der Runde gilt es auch als Startziel der nächsten Runden."""
        if target not in WIN_TARGETS:
            raise ValueError("Unbekanntes Gewinnziel.")
        self.win_target = target
        if self.game.caller.index < 0:
            self.round_start_target = target

    def check_win(self, card_number: int) -> tuple[bool, list[str], bool]:
        """(Gewinnziel erreicht?, vollständige Linien, Karte voll?) für eine Kartennummer."""
        lines = self.check_bingo(card_number)
        game = self.game
        complete, full = card_status(game.cards[card_number - 1], game.size, game.free_space,
                                     game.caller.drawn, game.diagonal_wins)
        return target_reached(self.win_target, complete, full), lines, full

    def target_status(self) -> TargetStatus:
        """Prüft alle Karten gegen das aktuelle Gewinnziel – nur für die Spielleitung, nicht für den Beamer."""
        game = self.game
        drawn = game.caller.drawn
        entered = {winner.card for winner in self.winners
                   if winner.round == self.round_number and winner.target == self.win_target}
        won_before = {winner.card for winner in self.winners} - entered
        reached: list[tuple[int, int]] = []
        entered_open: list[int] = []
        one_missing = 0
        for number, card in enumerate(game.cards, start=1):
            missing = missing_to_target(card, game.size, game.free_space, drawn, self.win_target, game.diagonal_wins)
            if number in entered:
                if missing:
                    entered_open.append(number)
            elif missing == 0:
                song = reached_at(card, game.size, game.free_space, drawn, self.win_target, game.diagonal_wins)
                reached.append((number, song or 0))
            elif missing == 1:
                one_missing += 1
        if not drawn:
            reached, one_missing = [], 0  # vor dem ersten Song hat niemand gewonnen (z. B. 1 Reihe durchs Freifeld)
        reached.sort(key=lambda item: (item[1], item[0]))
        earlier = tuple(number for number, _song in reached if number in won_before)
        return TargetStatus(tuple(reached), tuple(sorted(entered)), tuple(entered_open), earlier, one_missing)

    def forecast(self, runs: int = 300) -> Forecast:
        game = self.game
        return forecast(game.cards, game.songs, game.size, game.free_space, game.diagonal_wins, runs)

    def guarantee(self) -> Guarantee:
        game = self.game
        return guarantee(game.cards, game.songs, game.size, game.free_space)

    def set_event_title(self, title: str) -> str:
        self.event_title = clean_event_title(title)
        return self.event_title

    def set_timer(self, seconds: int, reveal_seconds: int) -> None:
        SongTimer(seconds, reveal_seconds)  # prüft die Grenzen
        self.timer_seconds, self.reveal_seconds = seconds, reveal_seconds

    def advance_stage(self) -> tuple[str, bool]:
        """Nächste Gewinnstufe; nach „Volle Karte“ neue Runde mit neu gemischter Ziehung.

        Die neue Runde beginnt mit dem Startziel (``round_start_target``) – üblich „1 Reihe“, bei einem Abend
        nur mit „Volle Karte“ wieder „Volle Karte“.
        """
        if not self.game.cards:
            raise ValueError("Es gibt noch keine Runde.")
        target, new_round = next_stage(self.win_target)
        if new_round:
            if self.round_number >= 999:
                raise ValueError("Maximale Rundenzahl erreicht.")
            self.game.caller.reshuffle()
            self.round_number += 1
            target = self.round_start_target
        self.win_target = target
        return target, new_round

    def restart_round(self) -> None:
        """Neu mischen mitten im Spiel = neue Runde (sonst könnte ein echter Gewinner nicht eingetragen werden)."""
        if not self.game.cards:
            raise ValueError("Es gibt noch keine Runde.")
        if self.round_number >= 999:
            raise ValueError("Maximale Rundenzahl erreicht.")
        self.game.caller.reshuffle()
        self.round_number += 1
        self.win_target = self.round_start_target

    def add_winner(self, card_number: int, name: str = "", allow_repeat: bool = False) -> Winner:
        """Trägt eine Karte als Gewinner der aktuellen Stufe ein – nur, wenn sie das Ziel wirklich erreicht hat."""
        reached, _lines, _full = self.check_win(card_number)
        if not reached:
            raise ValueError(f"Karte #{card_number} hat das Gewinnziel noch nicht erreicht.")
        winner = Winner(self.round_number, self.win_target, card_number, clean_text(name, MAX_NAME_LENGTH),
                        len(self.game.caller.drawn))
        check_new_winner(self.winners, winner, allow_repeat)
        self.winners.append(winner)
        return winner

    def remove_winner(self, index: int) -> Winner:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self.winners):
            raise ValueError("Diesen Gewinner gibt es nicht.")
        return self.winners.pop(index)

    def set_song_link(self, key: str, link: str) -> Song:
        """Setzt (oder entfernt mit "") den Link eines Songs – überall gleich. Gibt den neuen Song zurück."""
        self.set_song_links({key: link})
        return next((song for song in self.game.songs if song.key == key), None) or next(
            song for song in parse_songs(self.song_text) if song.key == key)

    def set_song_links(self, links: dict[str, str]) -> int:
        """Setzt mehrere Links (Song.key → Link) in Songliste, Runde, Karten und Ziehung.

        Alle Links werden vorher geprüft; bei einem Fehler ändert sich nichts (ValueError).
        Die Song-Identität (Titel + Interpret) bleibt gleich, Karten und Ziehung damit auch.
        Rückgabe: Zahl der Songs, deren Link sich geändert hat.
        """
        draft = {song.key: song for song in parse_songs(self.song_text)}
        active = {song.key: song for song in self.game.songs}
        wanted: dict[str, str] = {}
        for key, value in links.items():
            song = active.get(key) or draft.get(key)
            if song is None:
                raise ValueError(f"Der Song „{key}“ ist nicht in der Runde oder Songliste.")
            try:
                wanted[key] = parse_user_link(value)
            except ValueError as error:
                raise ValueError(f"{song.display_name}: {error}") from error
        changed = {key for key, link in wanted.items()
                   if (key in active and active[key].link != link) or (key in draft and draft[key].link != link)}
        if not changed:
            return 0
        self.song_text = set_links_in_text(self.song_text, {key: wanted[key] for key in changed if key in draft})

        def update(song: Song) -> Song:
            return replace(song, link=wanted[song.key]) if song.key in changed else song

        game = self.game
        game.songs = [update(song) for song in game.songs]
        for card in game.cards:
            card.songs = [update(song) for song in card.songs]
        caller = game.caller
        caller.pool = [update(song) for song in caller.pool]
        caller.order = [update(song) for song in caller.order]
        return len(changed)

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
        self._limit_audio_files()

    def merge_audio_files(self, matched: dict[str, str]) -> int:
        """Ordner-Zuordnung übernehmen; bleibt unter der Ladegrenze. Gibt die Zahl der verworfenen zurück."""
        self.audio_files.update(matched)
        return self._limit_audio_files()

    def _limit_audio_files(self) -> int:
        """Zuordnungen bleiben erhalten (auch für gerade nicht genutzte Songs) – nur bei mehr als
        MAX_GAME_SONGS fallen die weg, die weder in der Runde noch in der Songliste stehen."""
        if len(self.audio_files) <= MAX_GAME_SONGS:
            return 0
        before = len(self.audio_files)
        wanted = {song.display_name.casefold() for song in self.game.songs}
        wanted |= {song.display_name.casefold() for song in parse_songs(self.song_text)}
        kept = {key: path for key, path in self.audio_files.items() if key in wanted}
        self.audio_files = dict(list(kept.items())[:MAX_GAME_SONGS])
        return before - len(self.audio_files)

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
                "round_start_target": self.round_start_target,
                "event_title": self.event_title,
                "round_number": self.round_number,
                "timer_seconds": self.timer_seconds,
                "reveal_seconds": self.reveal_seconds,
                "pause_after_timer": self.pause_after_timer,
                "beamer_reveal": self.beamer_reveal,
            },
            "winners": [winner.to_dict() for winner in self.winners],
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
        if not isinstance(raw_songs, list) or len(raw_songs) > MAX_GAME_SONGS:
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
        if not isinstance(raw_audio_files, dict) or len(raw_audio_files) > MAX_GAME_SONGS:
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
        # Ein NUL-Zeichen schneidet den Text im GTK-Editor ab – entfernen, statt die Liste still zu kürzen
        service.song_text = song_text.replace("\x00", "")
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
        if isinstance(playback_target, str):
            playback_target = LEGACY_TARGETS.get(playback_target, playback_target)
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
        # Fehlt in Ständen bis 2.5.1: dort begann jede neue Runde mit „1 Reihe“
        round_start_target = settings.get("round_start_target", "reihe")
        if round_start_target not in WIN_TARGETS:
            raise ValueError("Ungültiges Start-Gewinnziel im Spielstand.")
        service.round_start_target = round_start_target
        title = settings.get("event_title", DEFAULT_TITLE)
        if not isinstance(title, str):
            raise ValueError("Ungültiger Titel der Feier im Spielstand.")
        service.event_title = clean_event_title(title)
        round_number = settings.get("round_number", 1)
        if not isinstance(round_number, int) or isinstance(round_number, bool) or not 1 <= round_number <= 999:
            raise ValueError("Ungültige Rundennummer im Spielstand.")
        service.round_number = round_number
        try:
            service.set_timer(settings.get("timer_seconds", 0), settings.get("reveal_seconds", 5))
        except ValueError as error:
            raise ValueError(f"Ungültige Timer-Einstellung im Spielstand: {error}") from error
        pause_after_timer = settings.get("pause_after_timer", True)
        if not isinstance(pause_after_timer, bool):
            raise ValueError("Ungültige Einstellung „Nach Ablauf pausieren“ im Spielstand.")
        service.pause_after_timer = pause_after_timer
        beamer_reveal = settings.get("beamer_reveal", True)
        if not isinstance(beamer_reveal, bool):
            raise ValueError("Ungültige Einstellung „Titel auf dem Beamer aufdecken“ im Spielstand.")
        service.beamer_reveal = beamer_reveal
        raw_winners = data.get("winners", [])
        if not isinstance(raw_winners, list) or len(raw_winners) > MAX_WINNERS:
            raise ValueError("Ungültige Gewinnerliste im Spielstand.")
        service.winners = []
        for item in raw_winners:
            winner = Winner.from_dict(item, len(cards))
            try:
                check_new_winner(service.winners, winner, allow_repeat=True)
            except ValueError as error:
                raise ValueError(f"Gewinnerliste im Spielstand: {error}") from error
            service.winners.append(winner)
        return service
