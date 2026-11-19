"""Regressionstests für Befunde aus der unabhängigen Code-Prüfung (Nov. 2026)."""
import random
import time
import unittest

from musik_bingo.domain.catalog import random_mix
from musik_bingo.domain.links import spotify_web_search_url, youtube_search_url
from musik_bingo.domain.matching import PlayingTrack, SongMatcher
from musik_bingo.domain.models import Song
from musik_bingo.domain.playlist import parse_csv, parse_text, from_player_tracks, ORDER_TITLE_ARTIST
from musik_bingo.domain.song_list import format_songs, parse_songs
from musik_bingo.domain.text import clean_title, strip_leading_number


class RegexDosTests(unittest.TestCase):
    def test_adversarial_titles_are_cleaned_quickly(self):
        attacks = [
            "A (" + "lyric video " * 60 + "x)",
            "A " + "- official " * 200,
            "(" * 5000 + "x" + ")" * 5000,
            "[" + "official/" * 3000 + "]",
            "x" * 100_000,
        ]
        for text in attacks:
            with self.subTest(text=text[:30]):
                start = time.perf_counter()
                clean_title(text)
                self.assertLess(time.perf_counter() - start, 0.5)

    def test_import_preview_of_huge_paste_stays_fast(self):
        start = time.perf_counter()
        parse_text("\n".join(f"Interpret {i} - Titel {i} (Official Video)" for i in range(5000)))
        self.assertLess(time.perf_counter() - start, 5)


class ContradictingArtistTests(unittest.TestCase):
    def test_cover_by_other_artist_is_not_drawn(self):
        matcher = SongMatcher([Song("Hello", "Adele"), Song("Jingle Bells", "Michael Bublé")])
        self.assertIsNone(matcher.find(PlayingTrack("Hello", "Lionel Richie")))
        self.assertIsNone(matcher.find(PlayingTrack("Jingle Bells", "Frank Sinatra")))
        self.assertEqual(matcher.find(PlayingTrack("Hello", "Adele")).artist, "Adele")

    def test_traditional_and_artistless_songs_accept_any_performer(self):
        matcher = SongMatcher([Song("Stille Nacht", "Traditional"), Song("O Tannenbaum")])
        self.assertEqual(matcher.find(PlayingTrack("Stille Nacht", "Helene Fischer")).title, "Stille Nacht")
        self.assertEqual(matcher.find(PlayingTrack("O Tannenbaum", "Kinderchor")).title, "O Tannenbaum")

    def test_title_only_report_requires_unique_title(self):
        matcher = SongMatcher([Song("Hello", "Adele")])
        self.assertIsNotNone(matcher.find(PlayingTrack("Hello", "")))


class DashInTitleTests(unittest.TestCase):
    def test_editor_round_trip_keeps_hyphen_in_title(self):
        song = Song("Rockin' Around - Live", "Brenda Lee")
        self.assertEqual(parse_songs(format_songs([song])), [song])
        self.assertEqual(parse_songs("Song - Teil 2 – Band")[0], Song("Song - Teil 2", "Band"))
        self.assertEqual(parse_songs("Old - Style")[0], Song("Old", "Style"))

    def test_player_import_of_version_suffix(self):
        result = from_player_tracks([PlayingTrack("Do They Know It's Christmas? - 1984 Version", "Band Aid",
                                                  "spotify:track:4uLU6hMCjMI75M1A2tKUQC")])
        song = result.songs[0]
        self.assertEqual((song.title, song.artist), ("Do They Know It's Christmas?", "Band Aid"))
        self.assertEqual(parse_songs(format_songs([song])), [song])


class CsvRobustnessTests(unittest.TestCase):
    def test_oversized_field_becomes_value_error(self):
        with self.assertRaises(ValueError):
            parse_csv("Track Name,Artist\n\"" + "x" * 200_000 + "\",A\n")

    def test_garbage_bytes_fail_cleanly(self):
        for text in ("Track Name;Artist\n\x00\x01;\x02\n;;\n", "\x00" * 1000, ";;;\n;;;"):
            with self.subTest(text=text[:10]):
                try:
                    parse_csv(text)
                except ValueError:
                    pass  # saubere Fehlermeldung ist erwünscht


class SmallFixesTests(unittest.TestCase):
    def test_band_names_with_numbers_survive(self):
        self.assertEqual(strip_leading_number("311 - Amber"), "311 - Amber")
        self.assertEqual(parse_text("22 - Taylor Swift", ORDER_TITLE_ARTIST).songs[0], Song("22", "Taylor Swift"))
        self.assertEqual(strip_leading_number("12. Wham! - Last Christmas"), "Wham! - Last Christmas")

    def test_mix_rounds_half_up(self):
        xmas = [Song(f"X{i}", "A") for i in range(5)]
        charts = [Song(f"C{i}", "B") for i in range(5)]
        self.assertEqual(random_mix(xmas, charts, 1, 50, random.Random(1)).christmas, 1)
        self.assertEqual(random_mix(xmas, charts, 3, 50, random.Random(1)).christmas, 2)

    def test_search_urls_escape_slashes(self):
        self.assertTrue(spotify_web_search_url("Thunderstruck", "AC/DC").endswith("AC%2FDC%20Thunderstruck"))
        self.assertNotIn("/DC", youtube_search_url("Thunderstruck", "AC/DC"))


if __name__ == "__main__":
    unittest.main()
