"""Lokale Steuerung von Musikplayern über MPRIS (D-Bus-Sitzungsbus).

Spotify (Desktop-App), VLC, Rhythmbox, Firefox/Chrome (YouTube) usw. melden
sich unter Linux als ``org.mpris.MediaPlayer2.<name>`` am Sitzungsbus an.
Darüber kann die App – ausschließlich lokal auf diesem Rechner –

* den gerade laufenden Titel lesen (Folgen-Modus),
* Play/Pause/Weiter/Stopp auslösen,
* in Spotify einen bestimmten Titel starten (``OpenUri``) und
* eine Playlist durchblättern, um ihre Titel einzulesen.

Die App selbst stellt dabei keine Internetverbindung her.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gi.repository import Gio, GLib

from musik_bingo.domain.links import normalize_link
from musik_bingo.domain.matching import PlayingTrack

MPRIS_PREFIX = "org.mpris.MediaPlayer2."
MPRIS_PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
CALL_TIMEOUT_MS = 1500
# Höchstens so lange wartet list_players() insgesamt auf die Namen aller Player – auch wenn einer hängt.
IDENTITY_BUDGET_MS = 1000
NOT_RESPONDING = "keine Antwort (Zeitüberschreitung)"
BROWSER_HINTS = ("firefox", "chrom", "brave", "vivaldi", "opera", "edge", "epiphany", "librewolf", "plasma-browser")


@dataclass(frozen=True)
class PlayerInfo:
    bus_name: str
    identity: str

    @property
    def is_spotify(self) -> bool:
        return "spotify" in self.bus_name.casefold() or "spotify" in self.identity.casefold()

    @property
    def is_browser(self) -> bool:
        text = f"{self.bus_name} {self.identity}".casefold()
        return any(hint in text for hint in BROWSER_HINTS)


def session_bus() -> Gio.DBusConnection | None:
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        return None


def error_text(error: GLib.Error) -> str:
    """Fehlertext eines D-Bus-Aufrufs; eine Zeitüberschreitung (Player hängt) immer als NOT_RESPONDING."""
    if error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.TIMED_OUT):
        return NOT_RESPONDING
    return error.message


def _unpack(value):
    return value.unpack() if isinstance(value, GLib.Variant) else value


def track_from_metadata(metadata: dict | None) -> PlayingTrack | None:
    """MPRIS-Metadaten → PlayingTrack. Werbung und leere Einträge → None."""
    if not metadata:
        return None
    metadata = {key: _unpack(value) for key, value in metadata.items()}
    # Werte von fremden Programmen nie vertrauen: Typen prüfen und Länge begrenzen.
    raw_title = metadata.get("xesam:title")
    title = (raw_title if isinstance(raw_title, str) else "").strip()[:300]
    artists = metadata.get("xesam:artist") or []
    if isinstance(artists, str):
        artists = [artists]
    if not isinstance(artists, (list, tuple)):
        artists = []
    artist = ", ".join(item.strip() for item in artists[:10] if isinstance(item, str) and item.strip())[:300]
    if _is_ad(metadata) or not title:
        return None
    return PlayingTrack(title, artist, link_from_metadata(metadata))


def _ids(metadata: dict) -> tuple[str, str]:
    trackid = metadata.get("mpris:trackid")
    url = metadata.get("xesam:url")
    return (trackid[:300] if isinstance(trackid, str) else "", url[:500] if isinstance(url, str) else "")


def _is_ad(metadata: dict) -> bool:
    lowered = " ".join(_ids(metadata)).casefold()
    return ":ad:" in lowered or "/ad/" in lowered or "/com/spotify/ad" in lowered


def link_from_metadata(metadata: dict | None) -> str:
    """Vereinheitlichter Link des laufenden Eintrags (Spotify-Track oder YouTube-Video), sonst ""."""
    if not metadata:
        return ""
    metadata = {key: _unpack(value) for key, value in metadata.items()}
    if _is_ad(metadata):
        return ""
    trackid, url = _ids(metadata)
    link = normalize_link(url)
    if not link and trackid:
        # Spotify meldet z. B. „/com/spotify/track/<ID>“ oder „spotify:track:<ID>“.
        if trackid.startswith("/com/spotify/track/"):
            link = normalize_link("spotify:track:" + trackid.rsplit("/", 1)[-1])
        else:
            link = normalize_link(trackid)
    return link


def track_identity(metadata: dict | None) -> str:
    """Stabile Kennung eines Eintrags, um Titelwechsel zu erkennen."""
    if not metadata:
        return ""
    metadata = {key: _unpack(value) for key, value in metadata.items()}
    artists = metadata.get("xesam:artist")
    artist = ", ".join(str(item) for item in artists) if isinstance(artists, (list, tuple)) else str(artists or "")
    # Interpret gehört dazu: Browser melden oft eine feste trackid und keine URL – sonst wäre
    # „White Christmas“ von Bing Crosby und von Michael Bublé derselbe Eintrag.
    return "|".join(
        [*(str(metadata.get(key) or "") for key in ("mpris:trackid", "xesam:url", "xesam:title")), artist]
    )


def list_players(connection: Gio.DBusConnection | None = None,
                 budget_ms: int = IDENTITY_BUDGET_MS) -> list[PlayerInfo]:
    """Alle MPRIS-Player am Bus.

    Die Namen („Identity“) werden parallel abgefragt; ein hängender Player hält die Oberfläche höchstens
    ``budget_ms`` auf und behält dann den aus dem Busnamen abgeleiteten Namen.
    """
    connection = connection or session_bus()
    if connection is None:
        return []
    try:
        reply = connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "ListNames", None, GLib.VariantType.new("(as)"), Gio.DBusCallFlags.NONE,
            CALL_TIMEOUT_MS, None,
        )
    except GLib.Error:
        return []
    names = [name for name in sorted(reply.unpack()[0]) if name.startswith(MPRIS_PREFIX)]
    identities: dict[str, str] = {}
    pending = set(names)
    # Eigener Kontext: Die Antworten kommen nur hier an, der GTK-Hauptloop läuft dabei nicht weiter
    # (keine verschachtelten Ereignisse), und alle Abfragen laufen gleichzeitig statt nacheinander.
    context = GLib.MainContext.new()
    context.push_thread_default()
    try:
        for name in names:
            def done(conn, result, name=name):
                pending.discard(name)
                try:
                    identities[name] = str(conn.call_finish(result).unpack()[0])
                except GLib.Error:
                    pass
            connection.call(
                name, MPRIS_PATH, "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (ROOT_IFACE, "Identity")), GLib.VariantType.new("(v)"),
                Gio.DBusCallFlags.NONE, budget_ms, None, done,
            )
        while pending:  # endet spätestens nach budget_ms: Gio meldet dann eine Zeitüberschreitung
            context.iteration(True)
    finally:
        context.pop_thread_default()
    players = []
    for name in names:
        identity = identities.get(name) or name[len(MPRIS_PREFIX):].split(".")[0].capitalize()
        players.append(PlayerInfo(name, identity))
    return players


def choose_player(players: list[PlayerInfo], preferred: str = "", target: str = "") -> PlayerInfo | None:
    """Wählt einen Player passend zum Wiedergabeziel; der gespeicherte hat Vorrang, wenn er passt."""
    if target == "spotify":
        candidates = [p for p in players if p.is_spotify]
    elif target == "youtube":
        candidates = [p for p in players if p.is_browser]
    else:
        candidates = sorted(players, key=lambda p: not p.is_spotify)
    for player in candidates:
        if preferred and player.bus_name == preferred:
            return player
    return candidates[0] if candidates else None


class MprisPlayer:
    """Ein verbundener Player. Änderungen kommen über ``on_change`` an.

    Das Verbinden blockiert nie lange, auch wenn der Player hängt: Die Eigenschaften werden nicht beim
    Anlegen synchron geladen (Gio wartet dafür bis zu 25 s), sondern asynchron mit kurzem Zeitlimit
    nachgeladen (``loaded``). Bis dahin liefern metadata()/status() leere bzw. Standardwerte.
    """

    def __init__(self, info: PlayerInfo, connection: Gio.DBusConnection | None = None,
                 on_change: Callable[[], None] | None = None):
        self.info = info
        self.connection = connection or session_bus()
        if self.connection is None:
            raise RuntimeError("Keine D-Bus-Sitzung gefunden.")
        self.on_change = on_change
        self.listeners: list[Callable[[], None]] = []
        self.loaded = False
        self.closed = False
        try:
            self.proxy = Gio.DBusProxy.new_sync(
                self.connection, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, None, info.bus_name,
                MPRIS_PATH, PLAYER_IFACE, None,
            )
        except GLib.Error as error:
            raise RuntimeError(f"Player {info.identity} nicht erreichbar: {error.message}") from error
        # Ohne geladene Eigenschaften abonniert der Proxy keine Änderungen – das übernehmen wir selbst.
        self._signal = self.connection.signal_subscribe(
            self.proxy.get_name_owner() or info.bus_name, "org.freedesktop.DBus.Properties", "PropertiesChanged",
            MPRIS_PATH, PLAYER_IFACE, Gio.DBusSignalFlags.NONE, self._properties_changed,
        )
        self.connection.call(
            info.bus_name, MPRIS_PATH, "org.freedesktop.DBus.Properties", "GetAll",
            GLib.Variant("(s)", (PLAYER_IFACE,)), GLib.VariantType.new("(a{sv})"),
            Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None, self._initial_state,
        )

    def _initial_state(self, connection, result, _data=None) -> None:
        try:
            properties = connection.call_finish(result).get_child_value(0)
        except GLib.Error:
            return  # Player antwortet nicht: Befehle melden das selbst über on_error
        if self.closed:
            return
        for index in range(properties.n_children()):
            entry = properties.get_child_value(index)
            name = entry.get_child_value(0).get_string()
            if self.proxy.get_cached_property(name) is None:  # neuere Änderungssignale haben Vorrang
                self.proxy.set_cached_property(name, entry.get_child_value(1).get_variant())
        self.loaded = True
        self._changed()

    def _properties_changed(self, _connection, _sender, _path, _iface, _signal, parameters, *_data) -> None:
        if self.closed:
            return
        changed = parameters.get_child_value(1)
        for index in range(changed.n_children()):
            entry = changed.get_child_value(index)
            self.proxy.set_cached_property(entry.get_child_value(0).get_string(),
                                           entry.get_child_value(1).get_variant())
        for name in parameters.get_child_value(2).unpack():
            self.proxy.set_cached_property(name, None)
        self._changed()

    def _changed(self, *_args) -> None:
        if self.on_change:
            self.on_change()
        for listener in list(self.listeners):
            listener()

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Zusätzlich bei jeder Änderung benachrichtigen (z. B. die Abspiel-Kontrolle)."""
        self.listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        if listener in self.listeners:
            self.listeners.remove(listener)

    def close(self) -> None:
        self.closed = True
        if self._signal:
            self.connection.signal_unsubscribe(self._signal)
            self._signal = 0
        self.on_change = None
        self.listeners.clear()

    # -- Zustand
    def metadata(self) -> dict:
        value = self.proxy.get_cached_property("Metadata")
        return value.unpack() if value is not None else {}

    def refresh(self) -> dict:
        """Metadaten direkt abfragen (falls ein Player keine Änderungssignale sendet)."""
        try:
            value = self.connection.call_sync(
                self.info.bus_name, MPRIS_PATH, "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (PLAYER_IFACE, "Metadata")), GLib.VariantType.new("(v)"),
                Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None,
            )
            metadata = value.unpack()[0]
            return metadata if isinstance(metadata, dict) else {}
        except GLib.Error:
            return self.metadata()

    def fetch_metadata(self, callback: Callable[[dict], None],
                       on_error: Callable[[str], None] | None = None) -> None:
        """Wie refresh(), aber asynchron – blockiert die Oberfläche nie."""
        def done(connection, result, _data=None):
            try:
                value = connection.call_finish(result).unpack()[0]
            except GLib.Error as error:
                if on_error:
                    on_error(error_text(error))
                return
            callback(value if isinstance(value, dict) else {})
        self.connection.call(
            self.info.bus_name, MPRIS_PATH, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (PLAYER_IFACE, "Metadata")), GLib.VariantType.new("(v)"),
            Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None, done,
        )

    def fetch_state(self, callback: Callable[[dict], None],
                    on_error: Callable[[str], None] | None = None) -> None:
        """Alle Player-Eigenschaften (Metadata, PlaybackStatus, CanControl …) asynchron abfragen."""
        def done(connection, result, _data=None):
            try:
                value = connection.call_finish(result).unpack()[0]
            except GLib.Error as error:
                if on_error:
                    on_error(error_text(error))
                return
            callback(value if isinstance(value, dict) else {})
        self.connection.call(
            self.info.bus_name, MPRIS_PATH, "org.freedesktop.DBus.Properties", "GetAll",
            GLib.Variant("(s)", (PLAYER_IFACE,)), GLib.VariantType.new("(a{sv})"),
            Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None, done,
        )

    def current_track(self) -> PlayingTrack | None:
        return track_from_metadata(self.metadata())

    def status(self) -> str:
        value = self.proxy.get_cached_property("PlaybackStatus")
        return value.unpack() if value is not None else "Stopped"

    def is_playing(self) -> bool:
        """Läuft die Wiedergabe? Unbekannt (Player meldet keinen Status oder ist noch nicht geladen) zählt als „ja“."""
        value = self.proxy.get_cached_property("PlaybackStatus")
        return value is None or value.unpack() == "Playing"

    def can(self, prop: str) -> bool:
        value = self.proxy.get_cached_property(prop)
        return bool(value.unpack()) if value is not None else True

    # -- Befehle
    def _call(self, method: str, params: GLib.Variant | None = None,
              on_error: Callable[[str], None] | None = None,
              on_success: Callable[[], None] | None = None) -> None:
        def done(proxy, result, _data=None):
            try:
                proxy.call_finish(result)
            except GLib.Error as error:
                if on_error:
                    on_error(error_text(error))
                return
            if on_success:
                on_success()
        self.proxy.call(method, params, Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None, done)

    def play(self, on_error=None) -> None:
        self._call("Play", None, on_error)

    def pause(self, on_error=None) -> None:
        self._call("Pause", None, on_error)

    def play_pause(self, on_error=None) -> None:
        self._call("PlayPause", None, on_error)

    def stop(self, on_error=None) -> None:
        self._call("Stop", None, on_error)

    def next(self, on_error=None) -> None:
        self._call("Next", None, on_error)

    def open_uri(self, uri: str, on_error=None, on_success=None) -> None:
        self._call("OpenUri", GLib.Variant("(s)", (uri,)), on_error, on_success)


class PlaylistReader:
    """Liest eine Playlist ein, indem sie im Player Titel für Titel weiterspringt.

    Ablauf: aktuellen Titel merken → „Weiter“ → asynchron warten, bis ein neuer
    Titel gemeldet wird → … Ende, wenn der erste Titel wieder auftaucht (Wiederholung),
    sich auch nach einem zweiten „Weiter“ nichts ändert (Ende ohne Wiederholung)
    oder das Limit erreicht ist. Taucht ein anderer Titel erneut auf, steht er doppelt in der
    Playlist: Er wird nur einmal übernommen und gezählt, das Einlesen läuft weiter.
    Werbung wird abgewartet, nicht übersprungen.

    ``on_done(tracks, reason, complete)``: ``complete`` ist False bei Abbruch oder
    Fehler – das Teilergebnis soll dann nicht übernommen werden.
    """

    AD_WAIT_MS = 90_000

    def __init__(self, player: MprisPlayer, on_progress: Callable[[int], None],
                 on_done: Callable[[list[PlayingTrack], str, bool], None],
                 limit: int = 500, wait_ms: int = 4000, poll_ms: int = 150):
        self.player = player
        self.on_progress = on_progress
        self.on_done = on_done
        self.limit = limit
        self.wait_ms = wait_ms
        self.poll_ms = poll_ms
        self.tracks: list[PlayingTrack] = []
        self.seen: set[str] = set()
        self.first_identity = ""
        self.second_identity = ""
        self.checking_wrap = False  # erster Titel kam wieder: Ist es der Neuanfang oder ein Duplikat?
        self.duplicates = 0
        self.repeats_in_row = 0
        self.source = 0
        self.pending = False
        self.deadline = 0
        self.retried = False
        self.in_ad = False
        self.last_identity = ""
        self.finished = False

    @staticmethod
    def _now_ms() -> int:
        return GLib.get_monotonic_time() // 1000

    def start(self) -> None:
        self.pending = True
        self.player.fetch_metadata(self._started, on_error=self._failed)

    def cancel(self) -> None:
        self._finish("Einlesen abgebrochen – nichts übernommen.", complete=False)

    def _failed(self, message: str) -> None:
        self._finish(f"Player reagiert nicht: {message}", complete=False)

    def _started(self, metadata: dict) -> None:
        self.pending = False
        if self.finished:
            return
        identity = track_identity(metadata)
        if not identity:
            self._finish("Im Player läuft gerade kein Titel. Bitte die Playlist in Spotify/YouTube starten.",
                         complete=False)
            return
        self.last_identity = identity
        if track_from_metadata(metadata) is None:  # Werbung zu Beginn: abwarten
            self.in_ad = True
            self._wait(self.AD_WAIT_MS)
            return
        self._record(identity, metadata)
        self._advance()

    def _record(self, identity: str, metadata: dict) -> None:
        if not self.first_identity:
            self.first_identity = identity
        elif not self.second_identity:
            self.second_identity = identity
        self.repeats_in_row = 0
        self.seen.add(identity)
        track = track_from_metadata(metadata)
        if track is not None:
            self.tracks.append(track)
            self.on_progress(len(self.tracks))

    def _advance(self) -> None:
        if len(self.tracks) >= self.limit:
            self._finish(f"Limit von {self.limit} Titeln erreicht.", complete=True)
            return
        self.player.next(on_error=self._failed)
        self._wait(self.wait_ms)

    def _wait(self, timeout_ms: int) -> None:
        self.deadline = self._now_ms() + timeout_ms
        if not self.source:
            self.source = GLib.timeout_add(self.poll_ms, self._tick)

    def _tick(self) -> bool:
        if self.finished:
            self.source = 0
            return False
        if not self.pending:
            self.pending = True
            self.player.fetch_metadata(self._received, on_error=self._failed)
        return True

    def _received(self, metadata: dict) -> None:
        self.pending = False
        if self.finished:
            return
        identity = track_identity(metadata)
        track = track_from_metadata(metadata)
        if identity and identity != self.last_identity:
            self.last_identity = identity
            self.retried = False
            if track is None:
                # Werbung endet von selbst. Kein „Weiter“ drücken: Endet die Werbung
                # genau dann, würde sonst der nächste echte Titel übersprungen.
                self.in_ad = True
                self.deadline = self._now_ms() + self.AD_WAIT_MS
                return
            self.in_ad = False
            if self.checking_wrap:
                self.checking_wrap = False
                if identity == self.second_identity:
                    # Erster und zweiter Titel in derselben Folge wieder → Playlist beginnt von vorn
                    self._finish("Playlist vollständig gelesen." + self._duplicate_note(), complete=True)
                    return
                self.duplicates += 1  # der erste Titel stand nur doppelt in der Playlist
            if identity == self.first_identity:
                if not self.second_identity:
                    self._finish("Playlist vollständig gelesen.", complete=True)  # nur ein Titel
                    return
                # Nicht sofort aufhören: Steht der erste Titel mitten in der Playlist noch einmal,
                # ginge sonst alles danach verloren. Erst der nächste Titel entscheidet.
                self.checking_wrap = True
                self._advance()
                return
            if identity in self.seen:
                # Doppelt in der Playlist (oder Player springt nicht zum Anfang zurück)
                self.duplicates += 1
                self.repeats_in_row += 1
                if self.repeats_in_row > len(self.seen):
                    self._finish("Nur noch bekannte Titel – Einlesen beendet." + self._duplicate_note(),
                                 complete=True)
                    return
                self._advance()
                return
            self._record(identity, metadata)
            self._advance()
            return
        if self._now_ms() < self.deadline:
            return
        if self.in_ad:
            self._finish("Werbung dauert zu lange – Einlesen beendet.", complete=bool(self.tracks))
        elif not self.retried:
            # Gleicher Titel zweimal hintereinander? Noch einmal „Weiter“ versuchen.
            self.retried = True
            self._advance()
        else:
            if self.checking_wrap:  # Playlist endete mit einer Wiederholung des ersten Titels
                self.checking_wrap = False
                self.duplicates += 1
            self._finish("Playlist-Ende erreicht." + self._duplicate_note(), complete=True)

    def _duplicate_note(self) -> str:
        if not self.duplicates:
            return ""
        times = "ein Titel kam" if self.duplicates == 1 else f"{self.duplicates} Titel kamen"
        return (f" Hinweis: {times} mehrfach (doppelt in der Playlist oder Zufallswiedergabe an) "
                "und wurde nur einmal übernommen." if self.duplicates == 1 else
                f" Hinweis: {times} mehrfach (doppelt in der Playlist oder Zufallswiedergabe an) "
                "und wurden nur einmal übernommen.")

    def _finish(self, reason: str, complete: bool) -> None:
        if self.finished:
            return
        self.finished = True
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
        self.player.pause()
        self.on_done(list(self.tracks), reason, complete)
