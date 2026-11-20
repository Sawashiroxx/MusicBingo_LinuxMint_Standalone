"""Regressionstests für Befunde aus der unabhängigen Code-Prüfung (Nov. 2026)."""
import random
import re
import time
import unittest

from musik_bingo.domain.catalog import random_mix
from musik_bingo.domain.links import spotify_web_search_url, youtube_search_url
from musik_bingo.domain.matching import PlayingTrack, SongMatcher
from musik_bingo.domain.models import Song
from musik_bingo.domain.playlist import parse_csv, parse_text, from_player_tracks, ORDER_TITLE_ARTIST
from musik_bingo.domain.song_list import format_songs, parse_song_line, parse_songs, set_links_in_text
from musik_bingo.domain.text import clean_title, count_text, strip_leading_number


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


class SameTitleTests(unittest.TestCase):
    def test_mix_never_contains_same_title_twice(self):
        xmas = [Song("Last Christmas", "Wham!"), Song("Last Christmas", "Taylor Swift")] + [Song(f"X{i}", "A") for i in range(5)]
        charts = [Song("Golden", "HUNTR/X"), Song("golden", "Andere Band")] + [Song(f"C{i}", "B") for i in range(5)]
        for seed in range(20):
            songs = random_mix(xmas, charts, 14, 50, random.Random(seed)).songs
            titles = [s.title.casefold() for s in songs]
            self.assertEqual(len(titles), len(set(titles)))

    def test_shipped_catalogs_have_unique_titles(self):
        from musik_bingo.domain.catalog import parse_catalog
        from musik_bingo.domain.text import normalize
        from musik_bingo.paths import CATALOG_DIR
        artists: dict[str, set[str]] = {}
        for path in CATALOG_DIR.glob("*.txt"):
            for song in parse_catalog(path.stem, path.read_text(encoding="utf-8")).songs:
                artists.setdefault(normalize(song.title), set()).add(normalize(song.artist))
        self.assertEqual({k: v for k, v in artists.items() if len(v) > 1}, {})


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

    def test_count_text_uses_singular_for_one(self):
        """Regression: Statuszeile meldete „1 Links gespeichert“."""
        self.assertEqual(count_text(1, "Link", "Links"), "1 Link")
        self.assertEqual(count_text(0, "Link", "Links"), "0 Links")
        self.assertEqual(count_text(2, "Link", "Links"), "2 Links")

    def test_search_urls_escape_slashes(self):
        self.assertTrue(spotify_web_search_url("Thunderstruck", "AC/DC").endswith("AC%2FDC%20Thunderstruck"))
        self.assertNotIn("/DC", youtube_search_url("Thunderstruck", "AC/DC"))


if __name__ == "__main__":
    unittest.main()


class FableReview24Tests(unittest.TestCase):
    """Befunde der unabhängigen Prüfung von v2.4 (Fable)."""

    def test_titles_with_dash_stay_intact_for_clean_players(self):
        tracks = [PlayingTrack("Stille Nacht - Heilige Nacht", "Helene Fischer",
                               "https://music.youtube.com/watch?v=aAkMkVFwAoo"),
                  PlayingTrack("Do They Know It's Christmas? - 1984 Version", "Band Aid",
                               "https://music.youtube.com/watch?v=E8gmARGvPlI")]
        songs = from_player_tracks(tracks).songs
        self.assertEqual([(s.title, s.artist) for s in songs],
                         [("Stille Nacht - Heilige Nacht", "Helene Fischer"),
                          ("Do They Know It's Christmas?", "Band Aid")])
        # Spotify-App ohne URL: Felder sind sauber getrennt
        app = from_player_tracks([PlayingTrack("Stille Nacht - Heilige Nacht", "Helene Fischer")],
                                 clean_metadata=True).songs[0]
        self.assertEqual((app.title, app.artist), ("Stille Nacht - Heilige Nacht", "Helene Fischer"))
        # YouTube-Video im Browser: weiterhin „Interpret - Titel“ zerlegen, Kanal verwerfen
        video = from_player_tracks([PlayingTrack("Chris Rea - Driving Home For Christmas", "ChrisReaVEVO",
                                                 "https://www.youtube.com/watch?v=aAkMkVFwAoo")]).songs[0]
        self.assertEqual((video.title, video.artist), ("Driving Home For Christmas", "Chris Rea"))

    def test_editor_round_trip_keeps_every_song(self):
        cases = [Song("#SELFIE", "The Chainsmokers"), Song("Stille Nacht - Heilige Nacht"),
                 Song("Old – Style"), Song("Rockin' Around - Live", "Brenda Lee"),
                 Song("Song", "", "spotify:track:4uLU6hMCjMI75M1A2tKUQC")]
        self.assertEqual(parse_songs(format_songs(cases)), cases)
        self.assertEqual(parse_songs(format_songs([Song("X", "A – B")])), [Song("X", "A - B")])
        self.assertEqual(parse_songs("# Kommentar\n#\n## Abschnitt\n#SELFIE – The Chainsmokers"),
                         [Song("#SELFIE", "The Chainsmokers")])
        # „#Abschnitt“ ohne Interpret bleibt Kommentar (bestehende Listen), Titel „#SELFIE“ übersteht den Editor
        self.assertEqual(parse_songs("#Weihnachten\n#80er-Block\nLast Christmas – Wham!"),
                         [Song("Last Christmas", "Wham!")])
        self.assertEqual(parse_songs(format_songs([Song("#SELFIE")])), [Song("#SELFIE")])

    def assert_documented_replacements(self, original: Song, result: Song, context) -> None:
        """Titel/Interpret wie im Original – bis auf die dokumentierten Ersetzungen des Editors:
        Gedankenstriche (– —) als Bindestrich „-“ und im Titel ein führendes Kommentarzeichen
        („# …“, „##…“, „#“) als „＃“. Andere Abweichungen (Zeichen weg, Song zerlegt) sind Fehler."""
        for field_name in ("title", "artist"):
            before, after = getattr(original, field_name), getattr(result, field_name)
            self.assertEqual(len(after), len(before), f"{field_name}: {after!r} ≠ {before!r} bei {context!r}")
            for index, (old, new) in enumerate(zip(before, after)):
                allowed = (new == old
                           or (old in "–—" and new == "-")
                           or (field_name == "title" and index == 0 and old == "#" and new == "＃"
                               and re.match(r"#(\s|#|$)", before)))
                self.assertTrue(allowed, f"{field_name}: {after!r} ≠ {before!r} bei {context!r}")
            if field_name == "title" and re.match(r"#(\s|#|$)", before):
                self.assertTrue(after.startswith("＃"), f"Kommentarzeichen nicht ersetzt: {context!r}")

    def check_editor_round_trip(self, song: Song) -> None:
        once = parse_songs(format_songs([song]))
        self.assertEqual(len(once), 1, f"Song verloren oder zerlegt: {song!r} → {format_songs([song])!r}")
        self.assert_documented_replacements(song, once[0], song)
        self.assertEqual(once[0].link, song.link, repr(song))
        self.assertEqual(parse_songs(format_songs(once)), once, f"nicht idempotent: {song!r}")
        self.assertEqual(format_songs(parse_songs(format_songs(once))), format_songs(once), repr(song))

    def test_editor_round_trip_fuzz_never_loses_or_splits_songs(self):
        # Realistische Namen: Wörter mit Bindestrich/Gedankenstrich dazwischen („Song - Live“, „A – B“)
        rng = random.Random(2412)
        words, dashes = ["a", "XY", "#b", "b|c", "Ü", "x-y"], ["-", "–", "—"]

        def name(max_words):
            parts = [rng.choice(words)]
            for _ in range(rng.randint(0, max_words)):
                if rng.random() < 0.4:
                    parts.append(rng.choice(dashes))
                parts.append(rng.choice(words))
            return " ".join(parts)
        for _ in range(3000):
            self.check_editor_round_trip(Song(name(4), name(2) if rng.random() < 0.7 else ""))

    def test_editor_round_trip_fuzz_with_random_characters(self):
        """Regression: Song("Wham! –", "x") wurde zu „Wham! – – x“ → Titel „Wham!“, Interpret „– x“."""
        self.check_editor_round_trip(Song("Wham! –", "x"))
        rng = random.Random(2026)
        alphabet = "ab XY#|-–—"
        link = "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
        checked = 0
        for _ in range(20_000):
            title = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 12)))
            artist = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))
            try:  # Wie beim Laden eines Spielstands: Leerzeichen am Rand entfernt, leerer Titel ungültig
                song = Song.from_dict({"title": title, "artist": artist, "link": link if rng.random() < 0.3 else ""})
            except ValueError:
                continue
            self.check_editor_round_trip(song)
            checked += 1
        self.assertGreater(checked, 19_000)

    def test_set_links_in_text_keeps_songs_with_dashes(self):
        """„Links übernehmen“ schreibt die Zeile mit format_song neu – der Song darf sich nicht ändern."""
        link = "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
        rng = random.Random(77)
        alphabet = "ab XY#|-–—"
        lines = ["Wham! – – x", "Wham! –  – x"]
        for _ in range(20_000):
            lines.append("".join(rng.choice(alphabet) for _ in range(rng.randint(1, 20))))
        for line in lines:
            song = parse_song_line(line)
            if song is None:
                continue
            updated = set_links_in_text(f"# Kopf\n{line}\nAndere – Band", {song.key: link})
            songs = parse_songs(updated)
            self.assertEqual(len(songs), 2, f"{line!r} → {updated!r}")
            self.assert_documented_replacements(song, songs[0], line)
            self.assertEqual(songs[0].link, link, repr(line))
            self.assertEqual(updated.split("\n")[0::2], ["# Kopf", "Andere – Band"])
        # Titel, der auf „ –“ endet, mit Interpret
        updated = set_links_in_text(format_songs([Song("Wham! –", "x")]), {Song("Wham! –", "x").key: link})
        self.assertEqual(len(parse_songs(updated)), 1, updated)
        self.assert_documented_replacements(Song("Wham! –", "x"), parse_songs(updated)[0], updated)
