"""Simulierter MPRIS-Player (z. B. Spotify) für Tests auf einem privaten D-Bus."""
import threading
import time

from gi.repository import Gio, GLib

TRACKS = [
    {"mpris:trackid": "/com/spotify/track/4uLU6hMCjMI75M1A2tKUQC", "xesam:title": "Last Christmas - Remastered",
     "xesam:artist": ["Wham!"]},
    {"mpris:trackid": "/com/spotify/ad/123", "xesam:title": "Werbung", "xesam:artist": ["Spotify"]},
    {"mpris:trackid": "/com/spotify/track/0bYg9bo50gSsH3LtXe2SQn", "xesam:title": "All I Want for Christmas Is You",
     "xesam:artist": ["Mariah Carey"]},
    {"mpris:trackid": "/com/spotify/track/2FRnf9qhLbvw8fu4IBXx78", "xesam:title": "Driving Home for Christmas",
     "xesam:artist": ["Chris Rea"]},
]

XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <property name="Identity" type="s" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/><method name="Play"/><method name="Pause"/>
    <method name="PlayPause"/><method name="Stop"/>
    <method name="OpenUri"><arg type="s" direction="in"/></method>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="PlaybackStatus" type="s" access="read"/>
  </interface>
</node>
"""


def metadata_variant(track: dict) -> GLib.Variant:
    data = {}
    for key, value in track.items():
        if key == "mpris:trackid":
            data[key] = GLib.Variant("o", value)
        elif isinstance(value, list):
            data[key] = GLib.Variant("as", value)
        else:
            data[key] = GLib.Variant("s", value)
    return GLib.Variant("a{sv}", data)


class FakePlayer:
    """Simulierter Player in eigenem Thread/Hauptloop – wie ein fremder Prozess."""

    def __init__(self, address: str, name: str, tracks: list[dict], loop_playlist: bool, identity="Spotify",
                 ad_ms: int | None = None):
        # ad_ms: Werbung endet nach so vielen ms von selbst (wie bei Spotify Free); None = nie
        self.tracks = tracks
        self.loop_playlist = loop_playlist
        self.position = 0
        self.status = "Playing"
        self.calls: list[tuple[str, tuple]] = []
        self.identity = identity
        self.ad_ms = ad_ms
        self.next_at: list[str] = []
        self.block_next_on_ads = False
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(address, name), daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError("Simulierter Player startet nicht.")

    def _run(self, address: str, name: str) -> None:
        self.context = GLib.MainContext()
        self.context.push_thread_default()
        self.loop = GLib.MainLoop(self.context)
        self.conn = Gio.DBusConnection.new_for_address_sync(
            address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None,
        )
        info = Gio.DBusNodeInfo.new_for_xml(XML)
        for iface in info.interfaces:
            self.conn.register_object("/org/mpris/MediaPlayer2", iface, self._method, self._get, None)
        self.conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName",
                            GLib.Variant("(su)", (name, 4)), None, Gio.DBusCallFlags.NONE, -1, None)
        self.ready.set()
        self.loop.run()
        self.context.pop_thread_default()

    def _get(self, _conn, _sender, _path, _iface, prop):
        if prop == "Identity":
            return GLib.Variant("s", self.identity)
        if prop == "Metadata":
            return metadata_variant(self.tracks[self.position]) if self.tracks else GLib.Variant("a{sv}", {})
        return GLib.Variant("s", self.status)

    def _method(self, _conn, _sender, _path, _iface, method, params, invocation):
        self.calls.append((method, params.unpack() if params else ()))
        if method == "Next":
            self.next_at.append(self.tracks[self.position].get("mpris:trackid", "") if self.tracks else "")
        if method == "Next" and self.tracks and self.block_next_on_ads and "/ad/" in self.tracks[self.position].get("mpris:trackid", ""):
            pass  # Spotify Free: während Werbung ist „Weiter“ gesperrt
        elif method == "Next" and self.tracks:
            if self.position + 1 < len(self.tracks):
                self.position += 1
            elif self.loop_playlist:
                self.position = 0
            self.emit()
        elif method == "Pause":
            self.status = "Paused"
        invocation.return_value(None)

    def advance(self) -> None:
        self.position = (self.position + 1) % len(self.tracks)
        self.emit()

    def set_track(self, index: int) -> None:
        self.position = index
        self.emit()

    def _schedule_ad_end(self) -> None:
        if self.ad_ms is not None and self.tracks and "/ad/" in self.tracks[self.position].get("mpris:trackid", ""):
            position = self.position
            def end():
                if not self.closed and self.position == position:
                    self.advance()
            threading.Timer(self.ad_ms / 1000, end).start()

    def emit(self) -> None:
        self.conn.emit_signal(None, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "PropertiesChanged",
                              GLib.Variant("(sa{sv}as)", ("org.mpris.MediaPlayer2.Player",
                                                          {"Metadata": metadata_variant(self.tracks[self.position])}, [])))
        self._schedule_ad_end()

    closed = False

    def close(self):
        self.closed = True
        self.conn.close_sync(None)
        self.loop.quit()
        self.thread.join(5)


def run_until(predicate, timeout=5.0) -> bool:
    context = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        context.iteration(False)
        time.sleep(0.005)
    return predicate()


