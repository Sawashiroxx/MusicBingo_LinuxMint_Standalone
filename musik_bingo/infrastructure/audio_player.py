from pathlib import Path
from typing import Callable

import gi

try:
    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst
except (ImportError, ValueError):
    GLib = None
    Gst = None


# Elemente, die selbst Netzwerkverbindungen öffnen könnten (HTTP-Quellen, HLS/DASH-Demuxer,
# RTSP/SDP …). Eine als .mp3 getarnte HLS-Playlist würde sonst Segmente aus dem Netz laden.
_BLOCKED_KLASS = ("Network", "Adaptive")
_ALLOWED_SOURCES = ("filesrc",)


def _is_blocked(factory) -> bool:
    if factory is None:
        return False
    klass = factory.get_metadata("klass") or ""
    if any(part in klass for part in _BLOCKED_KLASS):
        return True
    return "Source" in klass.split("/") and factory.get_name() not in _ALLOWED_SOURCES


def block_network_elements() -> int:
    """Netzwerkfähige Elemente aus dem automatischen Zusammenstecken nehmen (nur dieser Prozess)."""
    count = 0
    for factory in Gst.Registry.get().get_feature_list(Gst.ElementFactory):
        klass = factory.get_metadata("klass") or ""
        if any(part in klass for part in _BLOCKED_KLASS) and factory.get_rank() != Gst.Rank.NONE:
            factory.set_rank(Gst.Rank.NONE)
            count += 1
    return count


class AudioPlayer:
    """Kleiner lokaler Player – spielt nur lokale Dateien, ohne Netzwerkzugriff.

    Gst wird im GTK-Hauptloop verarbeitet.
    """

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
        block_network_elements()
        self.on_finished = on_finished
        self.on_error = on_error
        self.playbin = Gst.ElementFactory.make("playbin", "musik-bingo-player")
        if self.playbin is None:
            raise RuntimeError("GStreamer konnte keinen Audioplayer erstellen.")
        if audio_sink is not None:
            self.playbin.set_property("audio-sink", audio_sink)
        # Zweite Sicherung: Taucht trotzdem ein Netzwerk-Element auf, wird sofort abgebrochen.
        self.blocked = ""
        self.playbin.connect("deep-element-added", self._element_added)
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

    def _element_added(self, _bin, _sub_bin, element) -> None:
        # Läuft im Streaming-Thread: nur markieren und den Abbruch im Hauptloop auslösen.
        if self.blocked or not _is_blocked(element.get_factory()):
            return
        self.blocked = element.get_factory().get_name()
        element.set_locked_state(True)  # Element startet nicht, öffnet also nichts
        GLib.idle_add(self._abort_blocked)

    def _abort_blocked(self) -> bool:
        name, self.blocked = self.blocked, ""
        self.stop()
        if self.on_error:
            self.on_error(f"Datei wurde nicht abgespielt: Sie ist keine reine Audiodatei ({name}).")
        return False

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
