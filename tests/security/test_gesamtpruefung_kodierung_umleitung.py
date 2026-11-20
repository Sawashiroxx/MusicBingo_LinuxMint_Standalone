"""Regressionstests zur Gesamtprüfung November 2026 (Fable-Durchgang 3)."""
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path

from musik_bingo.domain.models import Song


class KodierungTests(unittest.TestCase):
    """Befund: Windows-Dateien (cp1252) wurden als Latin-1 gelesen – „–“ und „’“ wurden zu Steuerzeichen."""

    def setUp(self):
        try:
            from musik_bingo.presentation.dialogs import read_text_file
        except (ImportError, ValueError) as error:  # pragma: no cover
            self.skipTest(f"GTK nicht verfügbar: {error}")
        self.read_text_file = read_text_file

    def test_windows_1252_mit_gedankenstrich_und_apostroph(self):
        from musik_bingo.domain.playlist import parse_playlist
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "liste.txt"
            path.write_bytes("Last Christmas – Wham!\r\nRockin’ Around the Christmas Tree – Brenda Lee\r\n".encode("cp1252"))
            songs = parse_playlist(self.read_text_file(path), str(path)).songs
        self.assertEqual([(s.title, s.artist) for s in songs],
                         [("Last Christmas", "Wham!"), ("Rockin’ Around the Christmas Tree", "Brenda Lee")])

    def test_excel_unicode_text_utf16(self):
        from musik_bingo.domain.playlist import parse_playlist
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "excel.csv"
            path.write_bytes("Titel\tInterpret\r\nStille Nacht\tTraditional\r\n".encode("utf-16"))
            songs = parse_playlist(self.read_text_file(path), str(path)).songs
        self.assertEqual(songs, [Song("Stille Nacht", "Traditional")])

class UmleitungTests(unittest.TestCase):
    """Befund: QuickTime-Verweisfilm (als .mp3 getarnt) ließ GStreamer eine HTTP-Adresse abrufen."""

    def test_quicktime_verweisfilm_erreicht_nie_das_netz(self):
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import GLib, Gst
            from musik_bingo.infrastructure.audio_player import AudioPlayer
            Gst.init(None)
        except (ImportError, ValueError) as error:  # pragma: no cover
            self.skipTest(f"GStreamer nicht verfügbar: {error}")
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(5)
        server.settimeout(0.2)
        port = server.getsockname()[1]
        hits, stop = [], threading.Event()

        def accept():
            while not stop.is_set():
                try:
                    connection, _ = server.accept()
                except OSError:
                    continue
                hits.append(1)
                connection.close()
        thread = threading.Thread(target=accept, daemon=True)
        thread.start()

        def atom(kind: bytes, payload: bytes) -> bytes:
            return struct.pack(">I", len(payload) + 8) + kind + payload

        errors = []
        context = GLib.MainContext.default()
        try:
            with tempfile.TemporaryDirectory() as directory:
                # mehrere Versuche: Die Anfrage ging beim alten Stand nur in etwa 2 von 3 Läufen hinaus (Wettlauf)
                for attempt in range(6):
                    url = f"http://127.0.0.1:{port}/umleitung{attempt}".encode() + b"\x00"
                    rdrf = atom(b"rdrf", struct.pack(">I", 0) + b"url " + struct.pack(">I", len(url)) + url)
                    movie = atom(b"ftyp", b"qt  " + struct.pack(">I", 0) + b"qt  ") + atom(b"moov", atom(b"rmra", atom(b"rmda", rdrf)))
                    path = Path(directory) / f"Last Christmas {attempt}.mp3"
                    path.write_bytes(movie)
                    player = AudioPlayer(on_error=errors.append, audio_sink=Gst.ElementFactory.make("fakesink"))
                    try:
                        player.play(path)
                        end = time.time() + 1.5
                        while time.time() < end:
                            context.iteration(False)
                            time.sleep(0.01)
                    finally:
                        player.close()
        finally:
            stop.set()
            thread.join(2)
            server.close()
        self.assertEqual(hits, [], "Die App hat eine Netzwerkverbindung geöffnet")
        self.assertTrue(errors, "Fehler muss gemeldet werden")
        # Keine Quelle für Netzwerk-Adressen mehr vorhanden – unabhängig vom Rang
        for scheme in ("http", "https", "rtsp", "rist"):
            self.assertFalse(Gst.uri_protocol_is_supported(Gst.URIType.SRC, scheme), scheme)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
