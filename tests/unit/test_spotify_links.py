"""Link-Übersicht: Abdeckung mit Spotify-Links, Links nachtragen, Links aus der Playlist übernehmen."""
import json
import tempfile
import unittest
from pathlib import Path

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.link_coverage import link_coverage
from musik_bingo.domain.links import parse_user_link
from musik_bingo.domain.matching import links_from_playlist
from musik_bingo.domain.models import Song
from musik_bingo.domain.song_list import format_songs, parse_songs, set_links_in_text
from musik_bingo.infrastructure.file_store import FileStore

ID_A = "4uLU6hMCjMI75M1A2tKUQC"
ID_B = "7qiZfU4dY1lWllzX7mPBI3"
YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class LinkCoverageTests(unittest.TestCase):
    def test_counts_spotify_youtube_and_missing_in_stable_order(self):
        songs = [
            Song("Eins", "A", f"spotify:track:{ID_A}"),
            Song("Zwei", "B"),
            Song("Drei", "C", YT),
            Song("Vier", "D"),
            Song("Fünf", "E", f"spotify:track:{ID_B}"),
        ]
        coverage = link_coverage(songs)
        self.assertEqual((coverage.total, coverage.spotify, coverage.youtube, coverage.without), (5, 2, 1, 2))
        self.assertEqual([s.title for s in coverage.missing_spotify], ["Zwei", "Drei", "Vier"])
        self.assertFalse(coverage.complete)

    def test_empty_and_complete_lists(self):
        empty = link_coverage([])
        self.assertEqual((empty.total, empty.spotify, empty.without), (0, 0, 0))
        self.assertEqual(list(empty.missing_spotify), [])
        full = link_coverage([Song("Eins", "A", f"spotify:track:{ID_A}")])
        self.assertTrue(full.complete)

    def test_duplicates_count_once(self):
        coverage = link_coverage([Song("Eins", "A"), Song("eins", "a", f"spotify:track:{ID_A}")])
        self.assertEqual(coverage.total, 1)


class UserLinkTests(unittest.TestCase):
    def test_accepts_spotify_variants_and_youtube(self):
        for value in (
            f"spotify:track:{ID_A}",
            f"https://open.spotify.com/track/{ID_A}?si=abc123def",
            f"https://open.spotify.com/intl-de/track/{ID_A}",
            f"  https://open.spotify.com/intl-de/track/{ID_A}?si=x  ",
        ):
            with self.subTest(value=value):
                self.assertEqual(parse_user_link(value), f"spotify:track:{ID_A}")
        self.assertEqual(parse_user_link("https://youtu.be/dQw4w9WgXcQ"), YT)

    def test_never_lets_foreign_schemes_through(self):
        for value in ("javascript:alert(1)", "file:///etc/passwd", "spotify:track:" + ID_A + ";rm -rf",
                      "https://open.spotify.com.evil.example/track/" + ID_A, "ftp://open.spotify.com/track/" + ID_A):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_user_link(value)

    def test_empty_means_remove(self):
        self.assertEqual(parse_user_link("   "), "")

    def test_rejects_invalid_with_german_text(self):
        for value in ("hallo", f"https://open.spotify.com/album/{ID_A}",
                      f"https://open.spotify.com/playlist/{ID_A}", "https://example.com/track/x",
                      "spotify:track:zukurz"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as context:
                    parse_user_link(value)
                self.assertRegex(str(context.exception), r"(Link|Titel)")
        with self.assertRaisesRegex(ValueError, "Album"):
            parse_user_link(f"https://open.spotify.com/album/{ID_A}")
        with self.assertRaisesRegex(ValueError, "Playlist"):
            parse_user_link(f"https://open.spotify.com/playlist/{ID_A}")


class SongTextLinkTests(unittest.TestCase):
    def test_sets_and_removes_links_keeping_other_lines(self):
        text = "# Weihnachten\nLast Christmas – Wham!\n\nHello – Adele | " + YT + "\n#Kommentar"
        updated = set_links_in_text(text, {"last christmas – wham!": f"spotify:track:{ID_A}",
                                           "hello – adele": ""})
        lines = updated.split("\n")
        self.assertEqual(lines[0], "# Weihnachten")
        self.assertEqual(lines[1], f"Last Christmas – Wham! | spotify:track:{ID_A}")
        self.assertEqual(lines[2], "")
        self.assertEqual(lines[3], "Hello – Adele")
        self.assertEqual(lines[4], "#Kommentar")
        self.assertEqual(parse_songs(updated)[0].link, f"spotify:track:{ID_A}")


class PlaylistLinkTransferTests(unittest.TestCase):
    def test_fills_missing_links_only(self):
        pool = [Song("Last Christmas", "Wham!"), Song("Hello", "Adele", YT), Song("Fehlt", "X")]
        playlist = [Song("Last Christmas", "Wham!", f"spotify:track:{ID_A}"),
                    Song("Hello", "Adele", f"spotify:track:{ID_B}"),
                    Song("Ganz anders", "Y", f"spotify:track:{ID_B}")]
        self.assertEqual(links_from_playlist(pool, playlist), {"last christmas – wham!": f"spotify:track:{ID_A}"})

    def test_playlist_without_links_transfers_nothing(self):
        self.assertEqual(links_from_playlist([Song("A", "B")], [Song("A", "B")]), {})


def service_with_round() -> GameService:
    service = GameService()
    service.set_song_text("# Liste\n" + "\n".join(f"Song {i:02d} – Interpret {i}" for i in range(30)))
    service.create_cards(5, True, 20)
    for _ in range(5):
        service.game.caller.draw_next()
    return service


class ServiceSetLinkTests(unittest.TestCase):
    def test_link_is_set_everywhere_consistently(self):
        service = service_with_round()
        target = service.game.caller.current
        drawn_before = [s.key for s in service.game.caller.drawn]
        order_before = [s.key for s in service.game.caller.order]
        wins_before = [service.check_bingo(n) for n in range(1, 21)]
        cards_before = [[s.key for s in card.songs] for card in service.game.cards]

        song = service.set_song_link(target.key, f"https://open.spotify.com/intl-de/track/{ID_A}?si=abc")
        link = f"spotify:track:{ID_A}"
        self.assertEqual(song.link, link)
        self.assertEqual(song, target)  # Identität unverändert
        self.assertIn(f"{target.display_name} | {link}", service.song_text.splitlines())
        self.assertTrue(service.song_text.startswith("# Liste\n"))
        self.assertEqual(next(s for s in service.game.songs if s.key == target.key).link, link)
        self.assertEqual(next(s for s in service.game.caller.pool if s.key == target.key).link, link)
        self.assertEqual(next(s for s in service.game.caller.order if s.key == target.key).link, link)
        self.assertEqual(service.game.caller.current.link, link)
        self.assertEqual(service.game.caller.drawn[-1].link, link)
        for card in service.game.cards:
            for item in card.songs:
                if item.key == target.key:
                    self.assertEqual(item.link, link)
        # Ziehung, Karten und Gewinnprüfung bleiben gleich
        self.assertEqual([s.key for s in service.game.caller.drawn], drawn_before)
        self.assertEqual([s.key for s in service.game.caller.order], order_before)
        self.assertEqual([[s.key for s in card.songs] for card in service.game.cards], cards_before)
        self.assertEqual([service.check_bingo(n) for n in range(1, 21)], wins_before)
        self.assertEqual(link_coverage(service.game.songs).spotify, 1)

    def test_remove_link(self):
        service = service_with_round()
        key = service.game.songs[3].key
        service.set_song_link(key, f"spotify:track:{ID_A}")
        service.set_song_link(key, "")
        self.assertEqual(service.game.songs[3].link, "")
        self.assertNotIn("|", service.song_text)
        self.assertTrue(all(not s.link for card in service.game.cards for s in card.songs))

    def test_invalid_link_raises_and_changes_nothing(self):
        service = service_with_round()
        before = json.dumps(service.to_dict(), sort_keys=True)
        with self.assertRaises(ValueError):
            service.set_song_link(service.game.songs[0].key, "https://example.com/x")
        with self.assertRaises(ValueError):
            service.set_song_links({service.game.songs[0].key: f"spotify:track:{ID_A}", service.game.songs[1].key: "kaputt"})
        with self.assertRaisesRegex(ValueError, "nicht"):
            service.set_song_link("gibt es nicht – niemand", f"spotify:track:{ID_A}")
        self.assertEqual(json.dumps(service.to_dict(), sort_keys=True), before)

    def test_draft_only_song_list_without_cards(self):
        service = GameService()
        service.set_song_text("A – B\nC – D")
        service.set_song_link("c – d", YT)
        self.assertEqual(format_songs(parse_songs(service.song_text)), f"A – B\nC – D | {YT}")

    def test_batch_returns_number_of_changes(self):
        service = service_with_round()
        keys = [s.key for s in service.game.songs[:2]]
        changed = service.set_song_links({keys[0]: f"spotify:track:{ID_A}", keys[1]: f"spotify:track:{ID_B}"})
        self.assertEqual(changed, 2)
        self.assertEqual(service.set_song_links({keys[0]: f"spotify:track:{ID_A}"}), 0)

    def test_save_and_load_round_trip(self):
        service = service_with_round()
        target = service.game.caller.current
        service.set_song_link(target.key, f"spotify:track:{ID_A}")
        with tempfile.TemporaryDirectory() as folder:
            store = FileStore(Path(folder) / "spielstand.json")
            store.save(service)
            loaded = store.load()
        self.assertEqual(loaded.game.caller.current.link, f"spotify:track:{ID_A}")
        self.assertEqual(next(s for s in loaded.game.songs if s.key == target.key).link, f"spotify:track:{ID_A}")
        self.assertTrue(all(s.link == f"spotify:track:{ID_A}" for card in loaded.game.cards
                            for s in card.songs if s.key == target.key))
        self.assertEqual(parse_songs(loaded.song_text), parse_songs(service.song_text))
        self.assertEqual(next(s for s in parse_songs(loaded.song_text) if s.key == target.key).link,
                         f"spotify:track:{ID_A}")
        self.assertEqual([loaded.check_bingo(n) for n in range(1, 21)],
                         [service.check_bingo(n) for n in range(1, 21)])


if __name__ == "__main__":
    unittest.main()
