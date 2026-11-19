import random
import unittest

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.caller import Caller
from musik_bingo.domain.catalog import parse_catalog, random_mix, unique_songs
from musik_bingo.domain.links import normalize_link, spotify_search_uri, youtube_search_url
from musik_bingo.domain.matching import PlayingTrack, SongMatcher, compare_with_playlist
from musik_bingo.domain.models import Song
from musik_bingo.domain.playlist import (
    ORDER_ARTIST_TITLE,
    ORDER_TITLE_ARTIST,
    parse_csv,
    parse_m3u,
    parse_playlist,
    parse_text,
    to_csv,
    to_m3u,
    to_text,
)
from musik_bingo.domain.song_list import format_songs, parse_songs
from musik_bingo.domain.text import clean_title

TRACK = "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
from musik_bingo.paths import CATALOG_DIR


class LinkTests(unittest.TestCase):
    def test_spotify_and_youtube_links_are_normalized(self):
        self.assertEqual(normalize_link(TRACK), TRACK)
        self.assertEqual(normalize_link("https://open.spotify.com/intl-de/track/4uLU6hMCjMI75M1A2tKUQC?si=abc"), TRACK)
        self.assertEqual(normalize_link("https://youtu.be/E8gmARGvPlI?t=3"), "https://www.youtube.com/watch?v=E8gmARGvPlI")
        self.assertEqual(
            normalize_link("https://music.youtube.com/watch?v=E8gmARGvPlI&list=PL1"),
            "https://www.youtube.com/watch?v=E8gmARGvPlI",
        )

    def test_unknown_or_broken_links_are_rejected(self):
        for value in ("", "http://example.com/track", "spotify:track:kurz", "javascript:alert(1)",
                      "https://open.spotify.com/album/4uLU6hMCjMI75M1A2tKUQC", "https://www.youtube.com/watch?v=",
                      "file:///etc/passwd", "x" * 600, None):
            with self.subTest(value=value):
                self.assertEqual(normalize_link(value), "")

    def test_search_uris_are_url_encoded(self):
        self.assertEqual(spotify_search_uri("Last Christmas", "Wham!"), "spotify:search:Wham%21%20Last%20Christmas")
        self.assertIn("search_query=Ihr%20Kinderlein%20kommet", youtube_search_url("Ihr Kinderlein kommet", ""))


class SongTextTests(unittest.TestCase):
    def test_link_suffix_and_comments_round_trip(self):
        text = f"# Kommentar\nLast Christmas – Wham! | {TRACK}\nKein Link – A | nicht-ein-link"
        songs = parse_songs(text)
        self.assertEqual(songs[0].link, TRACK)
        self.assertEqual(songs[1], Song("Kein Link", "A | nicht-ein-link"))
        self.assertEqual(parse_songs(format_songs(songs)), songs)
        self.assertEqual([s.link for s in parse_songs(format_songs(songs))], [TRACK, ""])

    def test_link_does_not_change_song_identity(self):
        self.assertEqual(Song("A", "B", TRACK), Song("A", "B"))
        self.assertEqual(len(parse_songs(f"A – B | {TRACK}\nA – B")), 1)


class TitleCleanupTests(unittest.TestCase):
    def test_removes_streaming_and_youtube_noise(self):
        cases = {
            "Last Christmas (Official Video)": "Last Christmas",
            "Last Christmas - Remastered 2017": "Last Christmas",
            "Fairytale of New York [Official Music Video] | HD": "Fairytale of New York",
            "Feliz Navidad (feat. Someone)": "Feliz Navidad",
            "Thank You (Not So Bad)": "Thank You (Not So Bad)",
            "Dancing with Myself": "Dancing with Myself",
            "Shabab(e)s im VIP": "Shabab(e)s im VIP",
            "Song ft. X": "Song",
            "(Official Video)": "(Official Video)",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(clean_title(raw), expected)


class PlaylistImportTests(unittest.TestCase):
    def test_exportify_csv_with_links_and_quotes(self):
        csv_text = (
            "\ufeff\"Track URI\",\"Track Name\",\"Artist Name(s)\",\"Album Name\"\n"
            f"\"{TRACK}\",\"Last Christmas - Remastered\",\"Wham!\",\"Album\"\n"
            "\"spotify:track:0bYg9bo50gSsH3LtXe2SQn\",\"All I Want for Christmas Is You\",\"Mariah Carey\",\"x\"\n"
            "\"\",\"\",\"\",\"\"\n"
            "\"spotify:track:0bYg9bo50gSsH3LtXe2SQn\",\"all i want for christmas is you\",\"mariah carey\",\"x\"\n"
        )
        result = parse_playlist(csv_text, "liste.csv")
        self.assertEqual([s.display_name for s in result.songs], ["Last Christmas – Wham!", "All I Want for Christmas Is You – Mariah Carey"])
        self.assertEqual(result.songs[0].link, TRACK)
        self.assertEqual(result.duplicates, 1)

    def test_semicolon_csv_with_german_headers(self):
        result = parse_csv("Titel;Interpret\nStille Nacht;Traditional\nO Tannenbaum;\n")
        self.assertEqual(result.songs, [Song("Stille Nacht", "Traditional"), Song("O Tannenbaum")])

    def test_csv_without_title_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Titelspalte"):
            parse_csv("foo,bar\n1,2\n")

    def test_empty_inputs(self):
        self.assertEqual(parse_csv("").songs, [])
        self.assertEqual(parse_text("\n \n").songs, [])
        self.assertEqual(parse_m3u("#EXTM3U\n").songs, [])

    def test_youtube_titles_in_artist_title_order(self):
        text = (
            "1. Wham! - Last Christmas (Official Video)\n"
            "Mariah Carey - All I Want For Christmas Is You (Official Video) https://youtu.be/aAkMkVFwAoo\n"
            "https://www.youtube.com/watch?v=E8gmARGvPlI\n"
            "Stille Nacht\n"
        )
        result = parse_text(text, ORDER_ARTIST_TITLE)
        self.assertEqual(result.songs[0], Song("Last Christmas", "Wham!"))
        self.assertEqual(result.songs[1].link, "https://www.youtube.com/watch?v=aAkMkVFwAoo")
        self.assertEqual(result.songs[2], Song("Stille Nacht"))
        self.assertEqual(len(result.skipped), 1)  # reine URL ohne Titel

    def test_auto_order_respects_own_en_dash_format(self):
        result = parse_text("Last Christmas – Wham!\nWham! - Last Christmas")
        self.assertEqual(result.songs, [Song("Last Christmas", "Wham!")])
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(parse_text("Titel - Interpret", ORDER_TITLE_ARTIST).songs, [Song("Titel", "Interpret")])
        with self.assertRaises(ValueError):
            parse_text("x", "falsch")

    def test_m3u_with_extinf_and_plain_paths(self):
        text = (
            "#EXTM3U\n#EXTINF:215,Wham! - Last Christmas\n/home/nutzer/Musik/lc.mp3\n"
            "C:\\Musik\\Chris Rea - Driving Home for Christmas.mp3\n"
            "#EXTINF:-1,Mariah Carey - All I Want\nhttps://youtu.be/aAkMkVFwAoo\n"
            "https://youtu.be/E8gmARGvPlI\n"
        )
        result = parse_playlist(text, "x.m3u8")
        self.assertEqual([s.display_name for s in result.songs], [
            "Last Christmas – Wham!", "Driving Home for Christmas – Chris Rea", "All I Want – Mariah Carey"])
        self.assertEqual(result.songs[2].link, "https://www.youtube.com/watch?v=aAkMkVFwAoo")
        self.assertEqual(len(result.skipped), 1)

    def test_import_limit(self):
        result = parse_text("\n".join(f"Song {i}" for i in range(2005)))
        self.assertEqual(len(result.songs), 2000)
        self.assertEqual(len(result.skipped), 5)

    def test_exports_round_trip(self):
        songs = [Song("Last Christmas", "Wham!", TRACK), Song("Stille Nacht", "", "https://www.youtube.com/watch?v=E8gmARGvPlI"), Song("Ohne Quelle", "X")]
        self.assertEqual(parse_text(to_text(songs), ORDER_ARTIST_TITLE).songs, songs)
        reimported = parse_csv(to_csv(songs)).songs
        self.assertEqual(reimported, songs)
        self.assertEqual([s.link for s in reimported], [s.link for s in songs])
        m3u, skipped = to_m3u(songs, {"last christmas – wham!": "/musik/lc.mp3"})
        self.assertIn("/musik/lc.mp3", m3u)
        self.assertIn("https://www.youtube.com/watch?v=E8gmARGvPlI", m3u)
        self.assertEqual(skipped, 1)
        self.assertEqual(to_text([]), "")


class PlayerTrackImportTests(unittest.TestCase):
    def test_spotify_and_youtube_tracks_are_cleaned(self):
        from musik_bingo.domain.playlist import from_player_tracks
        tracks = [
            PlayingTrack("Last Christmas - Remastered", "Wham!", TRACK),
            PlayingTrack("Stille Nacht", ""),
            PlayingTrack("Mariah Carey - All I Want For Christmas Is You (Official Video)", "Mariah Carey",
                         "https://www.youtube.com/watch?v=aAkMkVFwAoo"),
            PlayingTrack("Chris Rea - Driving Home For Christmas", "ChrisReaVEVO"),
            PlayingTrack("Last Christmas", "Wham!"),
            PlayingTrack("", "Niemand"),
        ]
        result = from_player_tracks(tracks)
        self.assertEqual([s.display_name for s in result.songs], [
            "Last Christmas – Wham!", "Stille Nacht", "All I Want For Christmas Is You – Mariah Carey",
            "Driving Home For Christmas – Chris Rea"])
        self.assertEqual(result.songs[0].link, TRACK)
        self.assertEqual(result.songs[2].link, "https://www.youtube.com/watch?v=aAkMkVFwAoo")
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(len(result.skipped), 1)


class MatcherTests(unittest.TestCase):
    def setUp(self):
        self.pool = [
            Song("Last Christmas", "Wham!", TRACK),
            Song("Last Christmas", "Taylor Swift"),
            Song("All I Want for Christmas Is You", "Mariah Carey"),
            Song("Stille Nacht", "Traditional"),
            Song("Golden", "HUNTR/X"),
        ]
        self.matcher = SongMatcher(self.pool)

    def test_spotify_track_id_wins(self):
        self.assertEqual(self.matcher.find(PlayingTrack("irgendwas", "", TRACK)), self.pool[0])

    def test_title_and_artist(self):
        self.assertEqual(self.matcher.find(PlayingTrack("Last Christmas - Remastered", "Taylor Swift")), self.pool[1])
        self.assertEqual(
            self.matcher.find(PlayingTrack("Golden", "HUNTR/X, EJAE, AUDREY NUNA, REI AMI, KPop Demon Hunters Cast")),
            self.pool[4],
        )

    def test_ambiguous_title_without_artist_is_not_guessed(self):
        self.assertIsNone(self.matcher.find(PlayingTrack("Last Christmas", "")))
        self.assertIsNone(self.matcher.find(PlayingTrack("Last Christmas", "Jimmy Eat World")))

    def test_youtube_style_titles(self):
        self.assertEqual(self.matcher.find(PlayingTrack("Wham! - Last Christmas (Official Video)", "WhamVEVO")), self.pool[0])
        self.assertEqual(
            self.matcher.find(PlayingTrack("Mariah Carey - All I Want For Christmas Is You (Official Video)", "Sony Music")),
            self.pool[2],
        )
        self.assertEqual(self.matcher.find(PlayingTrack("Stille Nacht | Weihnachtslieder", "Kinderchor")), self.pool[3])

    def test_unknown_song(self):
        self.assertIsNone(self.matcher.find(PlayingTrack("Highway to Hell", "AC/DC")))
        self.assertIsNone(self.matcher.find(PlayingTrack("", "")))

    def test_short_artist_names_do_not_match_everything(self):
        matcher = SongMatcher([Song("Song", "A"), Song("Song", "B")])
        self.assertIsNone(matcher.find(PlayingTrack("Song", "Sony Music")))

    def test_compare_with_playlist(self):
        playlist = [Song("Last Christmas", "Wham!"), Song("Stille Nacht"), Song("Highway to Hell", "AC/DC")]
        missing, extra = compare_with_playlist(self.pool, playlist)
        self.assertEqual(extra, [Song("Highway to Hell", "AC/DC")])
        self.assertEqual(missing, [self.pool[1], self.pool[2], self.pool[4]])


class FollowModeTests(unittest.TestCase):
    def test_draw_specific_song(self):
        pool = [Song("A"), Song("B"), Song("C")]
        caller = Caller(pool, pool, -1)
        self.assertTrue(caller.draw_song(Song("C")))
        self.assertEqual(caller.drawn, [Song("C")])
        self.assertFalse(caller.draw_song(Song("C")))  # schon gezogen
        self.assertFalse(caller.draw_song(Song("X")))  # nicht im Pool
        self.assertEqual(caller.draw_next(), Song("A"))
        self.assertEqual(sorted(s.title for s in caller.order), ["A", "B", "C"])
        caller.undo()
        caller.undo()
        self.assertTrue(caller.draw_song(Song("C")))  # nach Undo wieder ziehbar
        self.assertTrue(caller.is_drawn(Song("c")))

    def test_follow_settings_round_trip_and_validation(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – Artist | spotify:track:{i:022d}" for i in range(10)))
        service.create_cards(3, False, 2)
        service.set_playback_target("spotify")
        service.follow_player = True
        service.player_name = "org.mpris.MediaPlayer2.spotify"
        service.draw_song(service.game.songs[4])
        data = service.to_dict()
        restored = GameService.from_dict(data)
        self.assertEqual(restored.playback_target, "spotify")
        self.assertTrue(restored.follow_player)
        self.assertEqual(restored.game.caller.current, service.game.songs[4])
        self.assertEqual(restored.game.caller.current.link, "spotify:track:" + "4".zfill(22))
        self.assertEqual(restored.game.cards[0].songs[0].link[:14], "spotify:track:")
        with self.assertRaises(ValueError):
            service.set_playback_target("radio")
        for key, value in (("playback_target", "radio"), ("follow_player", "ja"), ("player_name", 5)):
            broken = service.to_dict()
            broken["settings"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                GameService.from_dict(broken)

    def test_old_save_without_new_settings_still_loads(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i}" for i in range(9)))
        service.create_cards(3, False, 1)
        data = service.to_dict()
        for key in ("playback_target", "follow_player", "player_name"):
            del data["settings"][key]
        restored = GameService.from_dict(data)
        self.assertEqual(restored.playback_target, "lokal")
        self.assertFalse(restored.follow_player)


class CatalogTests(unittest.TestCase):
    def test_shipped_catalogs_are_valid(self):
        files = sorted(CATALOG_DIR.glob("*.txt"))
        self.assertGreaterEqual(len(files), 4)
        categories = set()
        for path in files:
            with self.subTest(path=path.name):
                catalog = parse_catalog(path.stem, path.read_text(encoding="utf-8"))
                categories.add(catalog.category)
                self.assertTrue(catalog.name and catalog.source)
                self.assertGreaterEqual(len(catalog.songs), 15)
                self.assertTrue(all(song.artist for song in catalog.songs))
        self.assertEqual(categories, {"weihnachten", "charts"})

    def test_catalog_errors(self):
        with self.assertRaisesRegex(ValueError, "kategorie"):
            parse_catalog("x", "# kategorie: oper\nA – B")
        with self.assertRaisesRegex(ValueError, "keine Songs"):
            parse_catalog("x", "# name: Leer\n")

    def test_mix_ratio_dedupe_and_fill(self):
        xmas = [Song(f"X{i}", "A") for i in range(10)] + [Song("Last Christmas", "Wham!")]
        charts = [Song(f"C{i}", "B") for i in range(30)] + [Song("last christmas", "WHAM!")]
        result = random_mix(xmas, charts, 20, 50, random.Random(1))
        self.assertEqual((result.christmas, result.charts, result.shortfall), (10, 10, 0))
        self.assertEqual(len({s.key for s in result.songs}), 20)
        # Zu wenig Weihnachtslieder: mit Charts auffüllen
        result = random_mix(xmas, charts, 30, 100, random.Random(2))
        self.assertEqual((result.christmas, result.charts, result.shortfall), (11, 19, 0))
        # Mehr gewünscht als vorhanden
        result = random_mix(xmas, charts, 100, 50, random.Random(3))
        self.assertEqual(len(result.songs), 41)
        self.assertEqual(result.shortfall, 59)
        self.assertEqual(random_mix(xmas, [], 5, 0, random.Random(4)).christmas, 5)
        self.assertEqual(random_mix([], [], 5, 50).songs, [])

    def test_mix_input_validation(self):
        for total, percent in ((0, 50), (2001, 50), (True, 50), (10, -1), (10, 101), (10, 50.5)):
            with self.subTest(total=total, percent=percent), self.assertRaises(ValueError):
                random_mix([Song("A")], [Song("B")], total, percent)

    def test_unique_songs_across_catalogs(self):
        a = parse_catalog("a", "# kategorie: charts\nGolden – HUNTR/X\nOrdinary – Alex Warren")
        b = parse_catalog("b", "# kategorie: charts\ngolden – huntr/x\nDracula – Tame Impala")
        self.assertEqual(len(unique_songs([a, b])), 3)


if __name__ == "__main__":
    unittest.main()
