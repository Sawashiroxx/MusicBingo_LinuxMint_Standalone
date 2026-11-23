"""Regressionstests zur Gesamtprüfung November 2026 (Fable-Durchgang 3)."""
import csv
import io
import json
import unittest

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.models import Song
from musik_bingo.domain.playlist import parse_csv, parse_playlist


class CsvOhneRatenTests(unittest.TestCase):
    """Befund: csv.Sniffer hält Hochkommas in Titeln für Anführungszeichen und verschluckt Zeilen."""

    ROWS = [("Last Christmas", "Wham!"), ("Merry Christmas, Happy Holidays", "'N Sync"),
            ("All I Want for Christmas Is You", "Mariah Carey"), ("Rockin' Around the Christmas Tree", "Brenda Lee"),
            ("Don't Stop Believin'", "Journey"), ("'Til You Can't", "Cody Johnson"), ("Feliz Navidad", "José Feliciano")]

    def csv_text(self, delimiter: str) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")  # nur nötige Anführungszeichen
        writer.writerow(["Titel", "Interpret"])
        writer.writerows(self.ROWS)
        return buffer.getvalue()

    def test_hochkommas_in_csv_ohne_anfuehrungszeichen(self):
        for delimiter in (",", ";", "\t"):
            with self.subTest(delimiter=delimiter):
                songs = parse_csv(self.csv_text(delimiter)).songs
                self.assertEqual([(s.title, s.artist) for s in songs], self.ROWS)

    def test_spalte_spotify_id_ohne_praefix_liefert_links(self):
        text = ("Spotify ID,Track Name,Artist Name(s)\n4uLU6hMCjMI75M1A2tKUQC,Last Christmas,Wham!\n"
                "0bYg9bo50gSsH3LtXe2SQn,All I Want for Christmas Is You,Mariah Carey\n")
        self.assertEqual([s.link for s in parse_csv(text).songs],
                         ["spotify:track:4uLU6hMCjMI75M1A2tKUQC", "spotify:track:0bYg9bo50gSsH3LtXe2SQn"])

class TabellenTextTests(unittest.TestCase):
    """Aus Excel/LibreOffice kopierte Zellen und „Unicode-Text (*.txt)“ sind Tab-getrennt. Ohne Endung .csv wurde
    die Kopfzeile zum Song, jeder Titel enthielt einen Tabulator und der Interpret fehlte."""

    TABLE = "Titel\tInterpret\tLink\r\nStille Nacht\tTraditional\t\r\nLast Christmas\tWham!\t" \
            "spotify:track:4uLU6hMCjMI75M1A2tKUQC\r\n"

    def test_eingefuegte_tabelle_mit_kopfzeile(self):
        for filename in ("", "liste.txt", "LISTE.TXT"):
            with self.subTest(filename=filename):
                songs = parse_playlist(self.TABLE, filename).songs
                self.assertEqual([(s.title, s.artist, s.link) for s in songs],
                                 [("Stille Nacht", "Traditional", ""),
                                  ("Last Christmas", "Wham!", "spotify:track:4uLU6hMCjMI75M1A2tKUQC")])

    def test_leerzeilen_und_bom_vor_der_kopfzeile(self):
        songs = parse_playlist("\ufeff\n\nTrack Name\tArtist Name(s)\nFeliz Navidad\tJosé Feliciano\n").songs
        self.assertEqual(songs, [Song("Feliz Navidad", "José Feliciano")])

    def test_normale_textlisten_bleiben_textlisten(self):
        # Tabulator ohne erkennbare Kopfzeile und Kopfwörter ohne Tabulator: wie bisher zeilenweise lesen
        self.assertEqual(parse_playlist("Wham! - Last Christmas\nTitel - Interpret\n").format_name, "Textliste")
        self.assertEqual(parse_playlist("Wham!\tLast Christmas\n").format_name, "Textliste")
        self.assertEqual(parse_playlist(self.TABLE).format_name, "CSV")


class SpielstandZeichenTests(unittest.TestCase):
    """Befund: Ein Stand mit einsamem Surrogat lädt, lässt sich nie wieder speichern und verhindert den Start."""

    def test_einsames_surrogat_im_titel_wird_abgelehnt(self):
        service = GameService()
        service.set_song_text("\n".join(f"Titel {i} – Interpret {i}" for i in range(12)))
        service.create_cards(3, False, 2)
        text = json.dumps(service.to_dict()).replace("Titel 0", "Kaputt \\ud83d")  # so steht es in einer fremden JSON-Datei
        with self.assertRaisesRegex(ValueError, "ungültige Zeichen"):
            GameService.from_dict(json.loads(text))

    def test_nul_zeichen_im_titel_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            Song.from_dict({"title": "Null\x00Titel"})

    def test_nul_zeichen_in_der_songliste_wird_entfernt(self):
        # GTK schneidet Text am NUL-Zeichen ab: Der Editor zeigte nur noch die Zeilen davor.
        service = GameService()
        service.set_song_text("\n".join(f"Titel {i} – Interpret {i}" for i in range(12)))
        service.create_cards(3, False, 2)
        data = service.to_dict()
        data["song_text"] = data["song_text"].replace("Titel 3 ", "Titel\x00 3 ")
        loaded = GameService.from_dict(data)
        self.assertNotIn("\x00", loaded.song_text)
        self.assertEqual(len(loaded.song_text.splitlines()), 12)


if __name__ == "__main__":
    unittest.main()
