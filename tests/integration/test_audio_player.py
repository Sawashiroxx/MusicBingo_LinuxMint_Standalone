import tempfile
import unittest
import wave
from pathlib import Path

from musik_bingo.infrastructure.audio_player import AudioPlayer, Gst


@unittest.skipIf(Gst is None, "GStreamer-Python ist optional")
class AudioPlayerTests(unittest.TestCase):
    def make_wav(self, path: Path, duration: float = 0.5) -> None:
        sample_rate = 8000
        frame_count = int(sample_rate * duration)
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(b"\0\0" * frame_count)

    def make_player(self, sync: bool = False) -> AudioPlayer:
        sink = Gst.ElementFactory.make("fakesink", "test-audio-sink")
        if sink is None:
            self.skipTest("GStreamer fakesink fehlt")
        sink.set_property("sync", sync)
        return AudioPlayer(audio_sink=sink, watch_bus=False)

    def test_wav_reaches_end_of_stream_without_audio_hardware(self):
        Gst.init(None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Bühne und Titel.wav"
            self.make_wav(path)
            player = self.make_player()
            try:
                player.play(path)
                message = player.bus.timed_pop_filtered(
                    5 * Gst.SECOND,
                    Gst.MessageType.EOS | Gst.MessageType.ERROR,
                )
                self.assertIsNotNone(message, "GStreamer lieferte weder EOS noch Fehler")
                if message.type == Gst.MessageType.ERROR:
                    error, debug = message.parse_error()
                    self.fail(f"WAV-Wiedergabe fehlgeschlagen: {error} ({debug})")
                self.assertEqual(message.type, Gst.MessageType.EOS)
            finally:
                player.close()

    def test_missing_audio_file_is_reported_before_playback(self):
        Gst.init(None)
        player = self.make_player()
        try:
            with self.assertRaises(FileNotFoundError):
                player.play(Path("/definitely/not/a/music-bingo-file.wav"))
        finally:
            player.close()

    def test_pause_resume_and_stop_update_player_state(self):
        Gst.init(None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long.wav"
            self.make_wav(path, duration=3)
            player = self.make_player(sync=True)
            try:
                player.play(path)
                player.pause()
                self.assertTrue(player.is_playing)
                self.assertTrue(player.is_paused)
                player.resume()
                self.assertTrue(player.is_playing)
                self.assertFalse(player.is_paused)
                player.stop()
                self.assertFalse(player.is_playing)
                self.assertFalse(player.is_paused)
            finally:
                player.close()

    def test_unreadable_audio_file_reports_gstreamer_error(self):
        Gst.init(None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-audio.wav"
            path.write_text("Das ist keine Audiodatei", encoding="utf-8")
            player = self.make_player()
            try:
                player.play(path)
                message = player.bus.timed_pop_filtered(
                    5 * Gst.SECOND,
                    Gst.MessageType.EOS | Gst.MessageType.ERROR,
                )
                self.assertIsNotNone(message, "GStreamer lieferte weder EOS noch Fehler")
                self.assertEqual(message.type, Gst.MessageType.ERROR)
                error, _debug = message.parse_error()
                self.assertTrue(str(error))
            finally:
                player.close()

    def test_disguised_stream_playlist_never_reaches_the_network(self):
        """Regression (Fable 2.4): HLS-Playlist als .mp3 → GStreamer lud Segmente per HTTP."""
        import socket
        import threading
        import time

        from gi.repository import GLib

        from musik_bingo.infrastructure.audio_player import block_network_elements

        Gst.init(None)
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(5)
        server.settimeout(0.2)
        port = server.getsockname()[1]
        hits = []
        stop = threading.Event()

        def accept():
            while not stop.is_set():
                try:
                    connection, _ = server.accept()
                except OSError:
                    continue
                hits.append(connection.recv(100))
                connection.close()
        thread = threading.Thread(target=accept, daemon=True)
        thread.start()
        errors = []
        with tempfile.TemporaryDirectory() as directory:
            for name, body in (
                ("Last Christmas – Wham!.mp3", "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n"
                 f"#EXTINF:10.0,\nhttp://127.0.0.1:{port}/seg0.ts\n#EXT-X-ENDLIST\n"),
                ("Feliz Navidad.ogg", '<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011" '
                 'type="static" mediaPresentationDuration="PT10S"><Period><AdaptationSet mimeType="audio/mp4">'
                 f'<Representation id="a" bandwidth="1"><BaseURL>http://127.0.0.1:{port}/a.mp4</BaseURL>'
                 '</Representation></AdaptationSet></Period></MPD>'),
            ):
                with self.subTest(name=name):
                    path = Path(directory) / name
                    path.write_text(body, encoding="utf-8")
                    sink = Gst.ElementFactory.make("fakesink")
                    player = AudioPlayer(on_error=errors.append, audio_sink=sink)
                    try:
                        player.play(path)
                        context = GLib.MainContext.default()
                        end = time.time() + 3
                        while time.time() < end:
                            context.iteration(False)
                            time.sleep(0.01)
                    finally:
                        player.close()
        stop.set()
        thread.join(2)
        server.close()
        self.assertEqual(hits, [], "Die App hat eine Netzwerkverbindung geöffnet")
        self.assertGreaterEqual(len(errors), 2, "Fehler muss gemeldet werden")
        self.assertEqual(block_network_elements(), 0)  # alles bereits gesperrt
        for name in ("souphttpsrc", "hlsdemux", "hlsdemux2", "dashdemux", "dashdemux2"):
            factory = Gst.ElementFactory.find(name)
            if factory is not None:
                self.assertEqual(factory.get_rank(), Gst.Rank.NONE, name)


if __name__ == "__main__":
    unittest.main()
