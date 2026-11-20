"""Spotify-Desktop-App zuverlässig ansteuern – nur lokal (D-Bus/MPRIS, Desktop-Starter).

* ``launch_desktop_app``: Spotify starten (normales Paket, Snap oder Flatpak).
* ``NameWaiter``: asynchron warten, bis sich Spotify am Sitzungsbus meldet.
* ``PlaybackCheck``: Nach ``OpenUri`` prüfen, ob wirklich der richtige Titel läuft
  (bei Pause einmal „Play“, fehlt der Titel einmal erneut öffnen).
* ``SelfTest``: Steuerung, Abspielen und Pause einmal durchprobieren.

Alles läuft über den GLib-Hauptloop und blockiert die Oberfläche nie.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gi.repository import Gio, GLib

from musik_bingo.domain.links import normalize_link
from musik_bingo.infrastructure.mpris import MprisPlayer, link_from_metadata

BUS_NAME = "org.mpris.MediaPlayer2.spotify"
# Paket/.deb, Snap, Flatpak
DESKTOP_IDS = ("spotify.desktop", "spotify_spotify.desktop", "com.spotify.Client.desktop")
CHECK_TIMEOUT_MS = 2500
START_TIMEOUT_MS = 15_000


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

    * richtiger Titel + Playing → ``PLAYING``
    * richtiger Titel, aber pausiert/gestoppt → einmal Play(), erneut prüfen
    * Titel kommt nicht → einmal OpenUri wiederholen, danach ``FAILED``
    * OpenUri abgelehnt → ``OPEN_ERROR`` mit Meldung (Aufrufer öffnet den Titel anders)

    ``on_done(result, detail)`` kommt genau einmal – nach ``cancel()`` nie.
    """

    PLAYING, FAILED, OPEN_ERROR = "playing", "failed", "open_error"

    def __init__(self, player: MprisPlayer, uri: str, on_done: Callable[[str, str], None],
                 timeout_ms: int = CHECK_TIMEOUT_MS, poll_ms: int = 200):
        self.player = player
        self.uri = uri
        self.expected = normalize_link(uri)
        self.on_done = on_done
        self.timeout_ms = timeout_ms
        self.poll_ms = poll_ms
        self.deadline = 0
        self.source = 0
        self.signal = 0
        self.pending = False
        self.saw_track = False
        self.play_sent = False
        self.reopened = False
        self.finished = False

    def start(self) -> None:
        self.signal = self.player.proxy.connect("g-properties-changed", lambda *_args: self._poll())
        self.source = GLib.timeout_add(self.poll_ms, self._tick)
        self._open()

    def cancel(self) -> None:
        self._finish(None, "")

    def _open(self) -> None:
        self.deadline = _now_ms() + self.timeout_ms
        self.player.open_uri(self.uri, on_error=self._open_failed)

    def _open_failed(self, message: str) -> None:
        self._finish(self.OPEN_ERROR, message)

    def _tick(self) -> bool:
        if self.finished:
            self.source = 0
            return False
        if _now_ms() >= self.deadline:
            self._deadline_reached()
        else:
            self._poll()
        return not self.finished

    def _poll(self) -> None:
        if self.finished or self.pending:
            return
        self.pending = True
        self.player.fetch_state(self._received, on_error=self._poll_failed)

    def _poll_failed(self, _message: str) -> None:
        self.pending = False  # Player antwortet (noch) nicht – bis zum Zeitlimit weiter versuchen

    def _received(self, state: dict) -> None:
        self.pending = False
        if self.finished:
            return
        if link_from_metadata(state.get("Metadata")) != self.expected:
            return
        self.saw_track = True
        if state.get("PlaybackStatus") == "Playing":
            self._finish(self.PLAYING, "")
        elif not self.play_sent:
            self.play_sent = True
            self.deadline = _now_ms() + self.timeout_ms
            self.player.play()

    def _deadline_reached(self) -> None:
        if not self.saw_track and not self.reopened:
            self.reopened = True
            self._open()
            return
        self._finish(self.FAILED, "")

    def _finish(self, result: str | None, detail: str) -> None:
        if self.finished:
            return
        self.finished = True
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
        if self.signal:
            self.player.proxy.disconnect(self.signal)
            self.signal = 0
        callback, self.on_done = self.on_done, None
        if callback and result is not None:
            callback(result, detail)


@dataclass
class SelfTestOutcome:
    can_control: bool = False
    started: bool = False
    paused: bool = False


class SelfTest:
    """Spotify-Test: Steuerbarkeit lesen, ``uri`` abspielen und kontrollieren, nach kurzer Zeit pausieren."""

    def __init__(self, player: MprisPlayer, uri: str, on_done: Callable[[SelfTestOutcome], None],
                 check_timeout_ms: int = CHECK_TIMEOUT_MS, pause_after_ms: int = 3000,
                 pause_timeout_ms: int = 2000, poll_ms: int = 200):
        self.player = player
        self.uri = uri
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
        self.player.fetch_state(self._got_capabilities, on_error=lambda _m: self._finish())

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
        self.check = PlaybackCheck(self.player, self.uri, self._checked, self.check_timeout_ms, self.poll_ms)
        self.check.start()

    def _checked(self, result: str, _detail: str) -> None:
        self.check = None
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
