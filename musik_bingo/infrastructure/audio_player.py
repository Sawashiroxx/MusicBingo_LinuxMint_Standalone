from pathlib import Path
from typing import Callable

import gi

try:
    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst
except (ImportError, ValueError):
    GLib = None
    Gst = None


class AudioPlayer:
    """Kleiner lokaler Player. Gst wird im GTK-Hauptloop verarbeitet."""

    def __init__(
        self,
        on_finished: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        audio_sink=None,
        watch_bus: bool = True,
    ):
        if Gst is None:
            raise RuntimeError("GStreamer-Python (python3-gst-1.0) ist nicht installiert.")
        Gst.init(None)
        self.on_finished = on_finished
        self.on_error = on_error
        self.playbin = Gst.ElementFactory.make("playbin", "musik-bingo-player")
        if self.playbin is None:
            raise RuntimeError("GStreamer konnte keinen Audioplayer erstellen.")
        if audio_sink is not None:
            self.playbin.set_property("audio-sink", audio_sink)
        self.bus = self.playbin.get_bus()
        self.watch_bus = watch_bus
        if watch_bus:
            self.bus.add_signal_watch()
            self.bus.connect("message", self._on_message)
        self.is_playing = False
        self.is_paused = False

    def play(self, path: Path) -> None:
        path = Path(path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Audiodatei nicht gefunden: {path}")
        self.stop()
        try:
            uri = Gst.filename_to_uri(str(path.resolve()))
            self.playbin.set_property("uri", uri)
            result = self.playbin.set_state(Gst.State.PLAYING)
        except GLib.Error as error:
            self.stop()
            raise RuntimeError(f"Audiodatei konnte nicht geöffnet werden: {error}") from error
        if result == Gst.StateChangeReturn.FAILURE:
            self.stop()
            raise RuntimeError("GStreamer konnte die Audiodatei nicht abspielen.")
        self.is_playing = True

    def pause(self) -> None:
        if not self.is_playing:
            return
        result = self.playbin.set_state(Gst.State.PAUSED)
        if result == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Wiedergabe konnte nicht pausiert werden.")
        self.is_paused = True

    def resume(self) -> None:
        if not self.is_playing or not self.is_paused:
            return
        result = self.playbin.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Wiedergabe konnte nicht fortgesetzt werden.")
        self.is_paused = False

    def stop(self) -> None:
        if getattr(self, "playbin", None) is not None:
            self.playbin.set_state(Gst.State.NULL)
        self.is_playing = False
        self.is_paused = False

    def close(self) -> None:
        self.stop()
        if self.watch_bus:
            self.bus.remove_signal_watch()

    def _on_message(self, _bus, message) -> None:
        if message.type == Gst.MessageType.EOS:
            self.stop()
            if self.on_finished:
                self.on_finished()
        elif message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            self.stop()
            if self.on_error:
                self.on_error(str(error))
