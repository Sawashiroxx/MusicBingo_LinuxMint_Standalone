"""Spotify-Wiedergabe: „Nach Ablauf pausieren“ im Spielstand, Prüfliste des Spotify-Tests, Testsong-Wahl."""
import copy
import unittest

from musik_bingo.application.game_service import GameService
from musik_bingo.application.spotify_check import (
    AUTOPLAY_HINT,
    NO_REPLY_NOTE,
    NO_TEST_SONG_NOTE,
    checklist,
    count_spotify_links,
    pick_test_song,
    report,
)
from musik_bingo.domain.matching import PlayingTrack, is_same_song
from musik_bingo.domain.models import Song

WHAM = Song("Last Christmas", "Wham!", "spotify:track:4uLU6hMCjMI75M1A2tKUQC")
MARIAH = Song("All I Want for Christmas Is You", "Mariah Carey", "spotify:track:0bYg9bo50gSsH3LtXe2SQn")
YOUTUBE = Song("Feliz Navidad", "José Feliciano", "https://www.youtube.com/watch?v=N8NcQzMQN_U")
PLAIN = Song("Driving Home for Christmas", "Chris Rea")


def service() -> GameService:
    result = GameService()
    result.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(12)))
    result.create_cards(3, False, 3)
    return result


class PauseAfterTimerSettingTests(unittest.TestCase):
    def test_default_is_on_and_round_trips(self):
        svc = service()
        self.assertTrue(svc.pause_after_timer)
        self.assertTrue(GameService.from_dict(svc.to_dict()).pause_after_timer)
        svc.pause_after_timer = False
        data = svc.to_dict()
        self.assertIs(data["settings"]["pause_after_timer"], False)
        self.assertFalse(GameService.from_dict(data).pause_after_timer)

    def test_old_saves_without_field_load_with_default(self):
        data = service().to_dict()
        del data["settings"]["pause_after_timer"]
        self.assertTrue(GameService.from_dict(data).pause_after_timer)

    def test_manipulated_value_is_rejected(self):
        base = service().to_dict()
        for value in ("ja", 1, None, [True]):
            data = copy.deepcopy(base)
            data["settings"]["pause_after_timer"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Nach Ablauf pausieren"):
                GameService.from_dict(data)


class ChecklistTests(unittest.TestCase):
    def test_all_good(self):
        items = checklist(found=True, can_control=True, started=True, paused=True, with_link=12, total=12)
        self.assertEqual(items, [
            (True, "Spotify gefunden"),
            (True, "Steuerung möglich"),
            (True, "Titel gestartet"),
            (True, "Pause funktioniert"),
            (True, "12 von 12 Songs mit Spotify-Link"),
        ])
        text = report(items)
        self.assertIn("✓ Spotify gefunden", text)
        self.assertNotIn("✗", text)
        self.assertTrue(text.rstrip().endswith(AUTOPLAY_HINT))
        self.assertIn("Einstellungen → Autoplay ausschalten", AUTOPLAY_HINT)

    def test_failures_and_missing_links_are_marked(self):
        items = checklist(found=True, can_control=False, started=False, paused=False, with_link=3, total=10)
        self.assertEqual([ok for ok, _ in items], [True, False, False, False, False])
        self.assertEqual(items[-1][1], "3 von 10 Songs mit Spotify-Link")
        text = report(items)
        self.assertIn("✗ Titel gestartet", text)
        self.assertIn("✗ 3 von 10 Songs mit Spotify-Link", text)
        self.assertIn(AUTOPLAY_HINT, text)

    def test_empty_list_is_not_ok(self):
        self.assertEqual(checklist(False, False, False, False, 0, 0)[-1], (False, "0 von 0 Songs mit Spotify-Link"))


class TestSongTests(unittest.TestCase):
    def test_counts_only_spotify_links(self):
        self.assertEqual(count_spotify_links([WHAM, YOUTUBE, PLAIN, MARIAH]), 2)
        self.assertEqual(count_spotify_links([]), 0)

    def test_current_song_with_link_wins_otherwise_first_with_link(self):
        self.assertIs(pick_test_song(MARIAH, [WHAM, MARIAH], [MARIAH]), MARIAH)
        # Vor Spielbeginn (nichts gezogen) darf der erste Song mit Link spielen.
        self.assertIs(pick_test_song(None, [PLAIN, MARIAH], []), MARIAH)
        self.assertIs(pick_test_song(None, [YOUTUBE, PLAIN, WHAM, MARIAH]), WHAM)
        self.assertIsNone(pick_test_song(None, [YOUTUBE, PLAIN], []))
        self.assertIsNone(pick_test_song(YOUTUBE, [YOUTUBE, PLAIN], [YOUTUBE]))

    def test_running_round_never_plays_an_undrawn_song(self):
        """Gäste würden einen noch nicht gezogenen Song hören – nur aktueller oder bereits gezogener Song."""
        songs = [YOUTUBE, PLAIN, WHAM, MARIAH]
        # aktueller Song ohne Link, WHAM schon gezogen → WHAM; MARIAH (nicht gezogen) nie
        self.assertIs(pick_test_song(PLAIN, songs, [WHAM, PLAIN]), WHAM)
        # zuletzt gezogener Song mit Link hat Vorrang vor älteren
        self.assertIs(pick_test_song(PLAIN, songs, [WHAM, MARIAH, PLAIN]), MARIAH)
        # nur Songs ohne Link gezogen → nichts abspielen, obwohl WHAM/MARIAH Links haben
        self.assertIsNone(pick_test_song(PLAIN, songs, [YOUTUBE, PLAIN]))
        # auch ohne „aktuellen“ Song: gezogen ist gezogen
        self.assertIsNone(pick_test_song(None, songs, [PLAIN]))

    def test_report_explains_test_without_song_and_unresponsive_spotify(self):
        items = checklist(True, True, False, False, 2, 4)
        text = report(items, [NO_TEST_SONG_NOTE])
        self.assertIn(NO_TEST_SONG_NOTE, text)
        self.assertIn("noch nicht gezogen", NO_TEST_SONG_NOTE)
        self.assertTrue(text.rstrip().endswith(AUTOPLAY_HINT))
        self.assertIn("Spotify reagiert nicht", report(items, [NO_REPLY_NOTE]))
        self.assertEqual(report(items), report(items, []))


class RelinkTests(unittest.TestCase):
    def test_same_title_and_artist_like_song_identity(self):
        self.assertTrue(is_same_song(PlayingTrack("Last Christmas", "Wham!", "spotify:track:x"), WHAM))
        self.assertTrue(is_same_song(PlayingTrack(" last christmas ", "WHAM!"), WHAM))
        self.assertFalse(is_same_song(PlayingTrack("Last Christmas", "Taylor Swift"), WHAM))
        # Relinking meldet oft Zusätze bzw. mehrere Interpreten – das ist derselbe Titel
        self.assertTrue(is_same_song(PlayingTrack("Last Christmas - Remastered", "Wham!"), WHAM))
        self.assertTrue(is_same_song(PlayingTrack("Last Christmas", "Wham!, George Michael"), WHAM))
        # … aber ein anderer Titel bleibt ein anderer Titel
        self.assertFalse(is_same_song(PlayingTrack("Last Christmas Party", "Wham!"), WHAM))
        self.assertFalse(is_same_song(PlayingTrack("Last Christmas", "Taylor Swift, Ed Sheeran"), WHAM))
        self.assertFalse(is_same_song(None, WHAM))
        self.assertFalse(is_same_song(PlayingTrack("Last Christmas", "Wham!"), None))
        self.assertFalse(is_same_song(PlayingTrack("", ""), Song("x")))


if __name__ == "__main__":
    unittest.main()
