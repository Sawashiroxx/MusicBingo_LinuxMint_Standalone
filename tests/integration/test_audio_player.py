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


if __name__ == "__main__":
    unittest.main()
