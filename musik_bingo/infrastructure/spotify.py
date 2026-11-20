"""Spotify-Desktop-App zuverlässig ansteuern – nur lokal (D-Bus/MPRIS, Desktop-Starter).

* ``launch_desktop_app``: Spotify starten (normales Paket, Snap oder Flatpak).
* ``NameWaiter``: asynchron warten, bis sich Spotify am Sitzungsbus meldet.
* ``PlaybackCheck``: Nach ``OpenUri`` prüfen, ob wirklich der richtige Titel läuft
  (bei Pause einmal „Play“, tut sich gar nichts, einmal erneut öffnen; nach einer Warnung
  noch eine Weile weiter beobachten, ob der Titel doch noch startet).
* ``SelfTest``: Steuerung, Abspielen und Pause einmal durchprobieren.

Alles läuft über den GLib-Hauptloop und blockiert die Oberfläche nie.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gi.repository import Gio, GLib

from musik_bingo.domain.links import normalize_link
from musik_bingo.domain.matching import is_same_song
from musik_bingo.domain.models import Song
from musik_bingo.infrastructure.mpris import (
    NOT_RESPONDING,
    MprisPlayer,
    link_from_metadata,
    track_from_metadata,
    track_identity,
)

BUS_NAME = "org.mpris.MediaPlayer2.spotify"
# Paket/.deb, Snap, Flatpak
DESKTOP_IDS = ("spotify.desktop", "spotify_spotify.desktop", "com.spotify.Client.desktop")
CHECK_TIMEOUT_MS = 2500
START_TIMEOUT_MS = 15_000
LATE_WATCH_MS = 30_000  # so lange nach dem Öffnen wird nach einer Warnung noch beobachtet


def _now_ms() -> int:
    return GLib.get_monotonic_time() // 1000


def find_desktop_app(ids: tuple[str, ...] = DESKTOP_IDS) -> Gio.DesktopAppInfo | None:
    for desktop_id in ids:
        try:
            info = Gio.DesktopAppInfo.new(desktop_id)
        except (GLib.Error, TypeError):
            info = None
        if info is not None:
            return info
    return None


def launch_desktop_app(ids: tuple[str, ...] = DESKTOP_IDS) -> bool:
    """Startet die installierte Spotify-App. False, wenn keine gefunden wurde oder der Start scheiterte."""
    info = find_desktop_app(ids)
    if info is None:
        return False
    try:
        return bool(info.launch([], None))
    except GLib.Error:
        return False


class NameWaiter:
    """Ruft ``on_done(True)`` auf, sobald ``name`` am Bus erscheint, sonst nach ``timeout_ms`` ``on_done(False)``."""

    def __init__(self, name: str, timeout_ms: int, on_done: Callable[[bool], None],
                 connection: Gio.DBusConnection | None = None):
        self.name = name
        self.timeout_ms = timeout_ms
        self.on_done = on_done
        self.connection = connection
        self.watch = 0
        self.source = 0
        self.active = False

    def start(self) -> None:
        self.active = True
        flags = Gio.BusNameWatcherFlags.NONE
        if self.connection is not None:
            self.watch = Gio.bus_watch_name_on_connection(self.connection, self.name, flags,
                                                          self._appeared, None)
        else:
            self.watch = Gio.bus_watch_name(Gio.BusType.SESSION, self.name, flags, self._appeared, None)
        self.source = GLib.timeout_add(self.timeout_ms, self._timeout)

    def _appeared(self, *_args) -> None:
        self._finish(True)

    def _timeout(self) -> bool:
        self.source = 0
        self._finish(False)
        return False

    def cancel(self) -> None:
        self.on_done = None
        self._finish(False)

    def _finish(self, appeared: bool) -> None:
        if not self.active:
            return
        self.active = False
        if self.watch:
            Gio.bus_unwatch_name(self.watch)
            self.watch = 0
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
        callback, self.on_done = self.on_done, None
        if callback:
            callback(appeared)


class PlaybackCheck:
    """Öffnet ``uri`` per OpenUri und beobachtet, ob genau dieser Titel mit „Playing“ läuft.

    * richtiger Titel + Playing → ``PLAYING``. Richtig ist er bei passendem Link oder – Spotifys
      „Relinking“ – bei anderer Track-ID, aber gleichem Titel und Interpret wie ``song``.
    * richtiger Titel, aber pausiert/gestoppt → einmal Play(), erneut prüfen
    * nach der Wartezeit hat sich gar nichts getan (noch derselbe Eintrag wie vor dem Öffnen) →
      einmal OpenUri wiederholen. Hat Spotify schon gewechselt (lädt nur noch), wird nicht neu
      geöffnet – das würde den Titel neu starten –, sondern noch einmal so lange gewartet.
    * danach ``FAILED``. Anschließend wird bis ``late_ms`` nach dem Start still weiter beobachtet:
      Läuft der richtige Titel doch noch, folgt ``LATE_PLAYING`` (ohne weitere Befehle).
    * OpenUri abgelehnt → ``OPEN_ERROR`` mit Meldung, keine Antwort → ``NO_REPLY``
      (Aufrufer öffnet den Titel anders)

    ``on_done(result, detail)`` kommt einmal – nur nach ``FAILED`` eventuell noch einmal mit
    ``LATE_PLAYING``. Nach ``cancel()`` nie.
    """

    PLAYING, FAILED, OPEN_ERROR, NO_REPLY, LATE_PLAYING = "playing", "failed", "open_error", "no_reply", "late"

    def __init__(self, player: MprisPlayer, uri: str, on_done: Callable[[str, str], None],
                 timeout_ms: int = CHECK_TIMEOUT_MS, poll_ms: int = 200, song: Song | None = None,
                 late_ms: int = LATE_WATCH_MS):
        self.player = player
        self.uri = uri
        self.expected = normalize_link(uri)
        self.song = song
        self.on_done = on_done
        self.timeout_ms = timeout_ms
        self.poll_ms = poll_ms
        self.late_ms = late_ms
        self.started_at = 0
        self.deadline = 0
        self.source = 0
        self.listening = False
        self.pending = False
        self.open_pending = False  # OpenUri noch unbeantwortet: erst Antwort/Zeitüberschreitung abwarten
        self.before: str | None = None  # Eintrag vor dem Öffnen (None = unbekannt)
        self.last_identity = ""
        self.saw_track = False
        self.play_sent = False
        self.reopened = False
        self.extended = False
        self.watching_late = False
        self.finished = False

    def start(self) -> None:
        self.started_at = _now_ms()
        self.player.add_listener(self._poll)
        self.listening = True
        self.source = GLib.timeout_add(self.poll_ms, self._tick)
        # Zustand vor dem Öffnen merken: Der Player beantwortet Aufrufe der Reihe nach,
        # diese Antwort zeigt also noch den alten Eintrag.
        self.player.fetch_state(self._got_before, on_error=lambda _message: None)
        self._open()

    def cancel(self) -> None:
        self._finish(None, "")

    def _got_before(self, state: dict) -> None:
        if self.before is None:
            self.before = track_identity(state.get("Metadata"))

    def _open(self) -> None:
        self.deadline = _now_ms() + self.timeout_ms
        self.open_pending = True
        self.player.open_uri(self.uri, on_error=self._open_failed, on_success=self._opened)

    def _opened(self) -> None:
        self.open_pending = False

    def _open_failed(self, message: str) -> None:
        self.open_pending = False
        if self.watching_late:
            return
        self._finish(self.NO_REPLY if message == NOT_RESPONDING else self.OPEN_ERROR, message)

    def _tick(self) -> bool:
        if self.finished:
            self.source = 0
            return False
        if _now_ms() >= self.deadline:
            self._deadline_reached()
        else:
            self._poll()
        if self.finished:
            self.source = 0
        return not self.finished

    def _poll(self) -> None:
        if self.finished or self.pending:
            return
        self.pending = True
        self.player.fetch_state(self._received, on_error=self._poll_failed)

    def _poll_failed(self, _message: str) -> None:
        self.pending = False  # Player antwortet (noch) nicht – bis zum Zeitlimit weiter versuchen

    def _is_expected(self, metadata) -> bool:
        if link_from_metadata(metadata) == self.expected:
            return True
        return is_same_song(track_from_metadata(metadata), self.song)

    def _received(self, state: dict) -> None:
        self.pending = False
        if self.finished:
            return
        metadata = state.get("Metadata")
        identity = track_identity(metadata)
        if identity:
            self.last_identity = identity
        if not self._is_expected(metadata):
            return
        playing = state.get("PlaybackStatus") == "Playing"
        if self.watching_late:
            if playing:
                self._finish(self.LATE_PLAYING, "")
            return
        self.saw_track = True
        if playing:
            self._finish(self.PLAYING, "")
        elif not self.play_sent:
            self.play_sent = True
            self.deadline = _now_ms() + self.timeout_ms
            self.player.play()

    def _changed_since_open(self) -> bool:
        return self.before is not None and bool(self.last_identity) and self.last_identity != self.before

    def _deadline_reached(self) -> None:
        if self.watching_late:
            self._finish(None, "")  # Titel kam auch später nicht: still beenden, Warnung bleibt
            return
        if self.open_pending:
            return  # Spotify hat OpenUri noch nicht beantwortet – Antwort oder NO_REPLY folgt gleich
        if not self.saw_track and not self.reopened and not self.extended:
            if self._changed_since_open():
                self.extended = True  # Spotify hat gewechselt und lädt noch: nicht neu starten
                self.deadline = _now_ms() + self.timeout_ms
            else:
                self.reopened = True
                self._open()
            return
        self._report(self.FAILED)
        late_end = self.started_at + self.late_ms
        if _now_ms() < late_end:
            self.watching_late = True
            self.deadline = late_end
        else:
            self._finish(None, "")

    def _report(self, result: str) -> None:
        if self.on_done:
            self.on_done(result, "")

    def _finish(self, result: str | None, detail: str) -> None:
        if self.finished:
            return
        self.finished = True
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
        if self.listening:
            self.player.remove_listener(self._poll)
            self.listening = False
        callback, self.on_done = self.on_done, None
        if callback and result is not None:
            callback(result, detail)


@dataclass
class SelfTestOutcome:
    responding: bool = True
    can_control: bool = False
    started: bool = False
    paused: bool = False


class SelfTest:
    """Spotify-Test: Steuerbarkeit lesen, ``uri`` abspielen und kontrollieren, nach kurzer Zeit pausieren."""

    def __init__(self, player: MprisPlayer, uri: str, on_done: Callable[[SelfTestOutcome], None],
                 check_timeout_ms: int = CHECK_TIMEOUT_MS, pause_after_ms: int = 3000,
                 pause_timeout_ms: int = 2000, poll_ms: int = 200, song: Song | None = None):
        self.player = player
        self.uri = uri
        self.song = song
        self.on_done = on_done
        self.check_timeout_ms = check_timeout_ms
        self.pause_after_ms = pause_after_ms
        self.pause_timeout_ms = pause_timeout_ms
        self.poll_ms = poll_ms
        self.outcome = SelfTestOutcome()
        self.check: PlaybackCheck | None = None
        self.source = 0
        self.deadline = 0
        self.pending = False
        self.finished = False

    def start(self) -> None:
        self.player.fetch_state(self._got_capabilities, on_error=self._no_state)

    def _no_state(self, message: str) -> None:
        self.outcome.responding = message != NOT_RESPONDING
        self._finish()

    def cancel(self) -> None:
        self.on_done = None
        self._finish()

    def _got_capabilities(self, state: dict) -> None:
        if self.finished:
            return
        # Fehlt eine Angabe, gilt sie wie bei MPRIS üblich als vorhanden.
        self.outcome.can_control = bool(state.get("CanControl", True)) and bool(state.get("CanPlay", True))
        if not self.uri:
            self._finish()
            return
        self.check = PlaybackCheck(self.player, self.uri, self._checked, self.check_timeout_ms, self.poll_ms,
                                   song=self.song, late_ms=0)
        self.check.start()

    def _checked(self, result: str, _detail: str) -> None:
        self.check = None
        if result == PlaybackCheck.NO_REPLY:
            self.outcome.responding = False
        if result != PlaybackCheck.PLAYING:
            self._finish()
            return
        self.outcome.started = True
        self.source = GLib.timeout_add(self.pause_after_ms, self._pause)

    def _pause(self) -> bool:
        if self.finished:
            self.source = 0
            return False
        self.player.pause()
        self.deadline = _now_ms() + self.pause_timeout_ms
        self.source = GLib.timeout_add(self.poll_ms, self._poll_paused)
        return False

    def _poll_paused(self) -> bool:
        if self.finished:
            self.source = 0
            return False
        if _now_ms() >= self.deadline:
            self.source = 0
            self._finish()
            return False
        if not self.pending:
            self.pending = True
            self.player.fetch_state(self._paused_state, on_error=lambda _m: setattr(self, "pending", False))
        return True

    def _paused_state(self, state: dict) -> None:
        self.pending = False
        if not self.finished and state.get("PlaybackStatus") in ("Paused", "Stopped"):
            self.outcome.paused = True
            self._finish()

    def _finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        if self.check is not None:
            self.check.cancel()
            self.check = None
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
        callback, self.on_done = self.on_done, None
        if callback:
            callback(self.outcome)
