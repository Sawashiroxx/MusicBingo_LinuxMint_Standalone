"""MPRIS-Anbindung gegen einen simulierten Player auf einem privaten D-Bus.

Es wird keine echte Spotify-/Browser-Instanz benötigt und nichts ins Netz gesendet.
"""
import shutil
import unittest

from musik_bingo.domain.models import Song
from musik_bingo.infrastructure.launcher import plan_launch

try:
    from gi.repository import Gio, GLib
    from musik_bingo.infrastructure import mpris
    from tests.support.fake_mpris import TRACKS, FakePlayer, metadata_variant, run_until
except (ImportError, ValueError):  # pragma: no cover
    Gio = None


@unittest.skipUnless(Gio is not None and shutil.which("dbus-daemon"), "D-Bus/PyGObject nicht verfügbar")
class MprisTests(unittest.TestCase):
    def setUp(self):
        self.bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
        self.bus.up()
        self.address = self.bus.get_bus_address()
        self.client = Gio.DBusConnection.new_for_address_sync(
            self.address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None,
        )
        self.fakes = []

    def tearDown(self):
        for fake in self.fakes:
            fake.close()
        self.client.close_sync(None)
        self.bus.down()

    def fake(self, name="org.mpris.MediaPlayer2.spotify", tracks=TRACKS, loop=False, identity="Spotify", ad_ms=None):
        player = FakePlayer(self.address, name, list(tracks), loop, identity, ad_ms)
        self.fakes.append(player)
        return player

    def test_change_signal_during_loading_wins_over_older_initial_state(self):
        """Mutation M4 (Fable): Kommt ein Änderungssignal an, BEVOR die Antwort auf das erste GetAll
        eintrifft, ist das Signal der neuere Stand – die ältere GetAll-Antwort darf es nicht überschreiben."""
        self.fake()  # meldet beim Laden Track 0 (Last Christmas), Status Playing
        info = mpris.list_players(self.client)[0]
        player = mpris.MprisPlayer(info, self.client)
        try:
            self.assertFalse(player.loaded)  # GetAll ist unterwegs, die Antwort braucht den Hauptloop
            newer = GLib.Variant("(sa{sv}as)", ("org.mpris.MediaPlayer2.Player", {
                "Metadata": metadata_variant(TRACKS[2]), "PlaybackStatus": GLib.Variant("s", "Paused")}, []))
            player._properties_changed(None, None, None, None, None, newer)  # Signal vor der Antwort
            self.assertTrue(run_until(lambda: player.loaded))
            self.assertEqual(player.current_track().title, TRACKS[2]["xesam:title"])
            self.assertEqual(player.status(), "Paused")
        finally:
            player.close()

    def test_close_stops_all_notifications(self):
        """Mutation M24 (Fable): Nach close() darf keine Meldung mehr ankommen – weder aus späten
        Antworten auf das erste Laden noch aus Änderungssignalen des Players."""
        fake = self.fake()
        info = mpris.list_players(self.client)[0]
        changes, heard = [], []
        player = mpris.MprisPlayer(info, self.client, on_change=lambda: changes.append(1))
        player.add_listener(lambda: heard.append(1))
        player.close()  # noch bevor die GetAll-Antwort verarbeitet wurde
        fake.set_track(1)
        fake.set_status("Paused")
        run_until(lambda: False, timeout=1.0)  # Hauptloop laufen lassen: Antwort + Signale treffen ein
        self.assertEqual((changes, heard), ([], []))
        self.assertFalse(player.loaded)
        self.assertEqual(player.listeners, [])

        # Gegenprobe: ohne close() kommen dieselben Meldungen an (der Test misst also etwas)
        open_player = mpris.MprisPlayer(info, self.client, on_change=lambda: changes.append(1))
        try:
            self.assertTrue(run_until(lambda: open_player.loaded))
            fake.set_track(2)
            self.assertTrue(run_until(lambda: len(changes) >= 2))
        finally:
            open_player.close()

    def test_lists_and_chooses_players(self):
        self.fake()
        self.fake("org.mpris.MediaPlayer2.firefox.instance_1_23", identity="Mozilla Firefox")
        players = mpris.list_players(self.client)
        self.assertEqual([p.identity for p in players], ["Mozilla Firefox", "Spotify"])
        self.assertTrue(mpris.choose_player(players, target="spotify").is_spotify)
        self.assertTrue(mpris.choose_player(players, target="youtube").is_browser)
        self.assertEqual(mpris.choose_player(players, preferred=players[0].bus_name).bus_name, players[0].bus_name)
        self.assertIsNone(mpris.choose_player([], target="spotify"))
        self.assertIsNone(mpris.choose_player([p for p in players if not p.is_spotify], target="spotify"))

    def test_music_youtube_track_link_is_normalized(self):
        self.fake("org.mpris.MediaPlayer2.chromium.instance42", identity="Chromium", tracks=[
            {"mpris:trackid": "/org/mpris/MediaPlayer2/Track/1", "xesam:title": "Last Christmas",
             "xesam:artist": ["Wham!"], "xesam:url": "https://music.youtube.com/watch?v=E8gmARGvPlI&list=RDAMVM"}])
        info = mpris.list_players(self.client)[0]
        player = mpris.MprisPlayer(info, self.client)
        try:
            self.assertTrue(run_until(lambda: player.loaded))  # Eigenschaften kommen asynchron
            track = player.current_track()
            self.assertEqual((track.title, track.artist), ("Last Christmas", "Wham!"))
            self.assertEqual(track.url, "https://www.youtube.com/watch?v=E8gmARGvPlI")
        finally:
            player.close()

    def test_reads_current_track_and_follows_changes(self):
        fake = self.fake()
        info = mpris.list_players(self.client)[0]
        changes = []
        player = mpris.MprisPlayer(info, self.client, on_change=lambda: changes.append(player.current_track()))
        self.assertTrue(run_until(lambda: player.loaded))  # Eigenschaften kommen asynchron, mit Meldung
        self.assertEqual(len(changes), 1)
        track = player.current_track()
        self.assertEqual(track.title, "Last Christmas - Remastered")
        self.assertEqual(track.url, "spotify:track:4uLU6hMCjMI75M1A2tKUQC")
        fake.set_track(2)
        self.assertTrue(run_until(lambda: changes and changes[-1] and changes[-1].artist == "Mariah Carey"))
        fake.set_track(1)  # Werbung wird ignoriert
        self.assertTrue(run_until(lambda: len(changes) >= 3))  # Laden, Mariah Carey, Werbung
        self.assertIsNone(changes[-1])
        player.close()

    def test_open_uri_and_controls(self):
        fake = self.fake()
        player = mpris.MprisPlayer(mpris.list_players(self.client)[0], self.client)
        player.open_uri("spotify:track:4uLU6hMCjMI75M1A2tKUQC")
        player.play_pause()
        player.stop()
        self.assertTrue(run_until(lambda: len(fake.calls) == 3))
        self.assertEqual(fake.calls[0], ("OpenUri", ("spotify:track:4uLU6hMCjMI75M1A2tKUQC",)))
        self.assertEqual([c[0] for c in fake.calls[1:]], ["PlayPause", "Stop"])

    def test_player_disappears(self):
        fake = self.fake()
        player = mpris.MprisPlayer(mpris.list_players(self.client)[0], self.client)
        errors = []
        fake.close()
        self.fakes.remove(fake)
        player.next(on_error=errors.append)
        self.assertTrue(run_until(lambda: errors))
        self.assertEqual(mpris.list_players(self.client), [])

    def read_playlist(self, loop: bool, tracks=TRACKS, limit=500, setup=None, cancel_after=None):
        fake = self.fake(tracks=tracks, loop=loop, ad_ms=400)
        if setup:
            setup(fake)
        player = mpris.MprisPlayer(mpris.list_players(self.client)[0], self.client)
        result = {}
        progress = []
        reader = mpris.PlaylistReader(
            player, progress.append,
            lambda t, r, complete: result.update(tracks=t, reason=r, complete=complete),
            limit=limit, wait_ms=500, poll_ms=30)
        reader.AD_WAIT_MS = 3000
        reader.start()
        if cancel_after is not None:
            run_until(lambda: len(progress) >= cancel_after, timeout=5)
            reader.cancel()
        self.assertTrue(run_until(lambda: result, timeout=15))
        return result, progress

    def test_reads_whole_playlist_with_repeat(self):
        result, progress = self.read_playlist(loop=True)
        self.assertEqual([t.artist for t in result["tracks"]], ["Wham!", "Mariah Carey", "Chris Rea"])
        self.assertEqual(result["reason"], "Playlist vollständig gelesen.")
        self.assertTrue(result["complete"])
        self.assertEqual(progress, [1, 2, 3])
        self.assertIn(("Pause", ()), self.fakes[0].calls)

    def test_same_title_other_artist_in_browser_is_a_new_track(self):
        """Regression: Browser (feste trackid, keine URL) – gleicher Titel, anderer Interpret."""
        def browser(title, artist):
            return {"mpris:trackid": "/org/mpris/MediaPlayer2/firefox", "xesam:title": title, "xesam:artist": [artist]}
        tracks = [browser("White Christmas", "Bing Crosby"), browser("Last Christmas", "Wham!"),
                  browser("White Christmas", "Michael Bublé"), browser("Driving Home for Christmas", "Chris Rea"),
                  browser("Feliz Navidad", "José Feliciano")]
        self.assertNotEqual(mpris.track_identity(tracks[0]), mpris.track_identity(tracks[2]))
        result, _ = self.read_playlist(loop=True, tracks=tracks)
        self.assertEqual([t.artist for t in result["tracks"]],
                         ["Bing Crosby", "Wham!", "Michael Bublé", "Chris Rea", "José Feliciano"])
        self.assertEqual(result["reason"], "Playlist vollständig gelesen.")

    def test_duplicate_track_in_playlist_does_not_end_reading(self):
        """Regression: [A, B, C, B, D, E] wurde als A, B, C „vollständig“ gemeldet."""
        def spotify(n):
            return {"mpris:trackid": f"/com/spotify/track/{n * 22}", "xesam:title": f"Song {n}",
                    "xesam:artist": [f"Artist {n}"]}
        tracks = [spotify(n) for n in "ABCBDE"]
        result, _ = self.read_playlist(loop=True, tracks=tracks)
        self.assertEqual([t.title for t in result["tracks"]], ["Song A", "Song B", "Song C", "Song D", "Song E"])
        self.assertTrue(result["complete"])
        self.assertIn("ein Titel kam mehrfach", result["reason"])

    def test_first_track_duplicated_mid_playlist_does_not_truncate(self):
        """Regression (Fable, 2. Prüfung): A B C D A E F → wurde bei der zweiten A beendet."""
        def spotify(n):
            return {"mpris:trackid": f"/com/spotify/track/{n * 22}", "xesam:title": f"Song {n}",
                    "xesam:artist": [f"Artist {n}"]}
        for loop, order in ((True, "ABCDAEF"), (False, "ABCDAEF"), (False, "ABCA"), (True, "ABA")):
            with self.subTest(loop=loop, order=order):
                result, _ = self.read_playlist(loop=loop, tracks=[spotify(n) for n in order])
                expected = [f"Song {n}" for n in dict.fromkeys(order)]
                self.assertEqual([t.title for t in result["tracks"]], expected)
                self.assertTrue(result["complete"])
                if order != "ABA":  # A B A | A B A: zwei gleiche hintereinander sehen aus wie kein Wechsel
                    self.assertIn("ein Titel kam mehrfach", result["reason"])
                for fake in self.fakes:
                    fake.close()
                self.fakes.clear()

    def test_reading_stops_when_player_never_returns_to_start(self):
        """Schutz vor Endlosschleife: Player wiederholt nur die letzten Titel."""
        def spotify(n):
            return {"mpris:trackid": f"/com/spotify/track/{n * 22}", "xesam:title": f"Song {n}",
                    "xesam:artist": [f"Artist {n}"]}
        tracks = [spotify(n) for n in "ABC"] + [spotify(n) for n in "BC" * 6]
        result, _ = self.read_playlist(loop=False, tracks=tracks)
        self.assertEqual([t.title for t in result["tracks"]], ["Song A", "Song B", "Song C"])
        self.assertTrue(result["complete"])

    def test_reads_playlist_until_end_without_repeat(self):
        result, _ = self.read_playlist(loop=False)
        self.assertEqual(len(result["tracks"]), 3)
        self.assertEqual(result["reason"], "Playlist-Ende erreicht.")
        # Ende wird erst nach einem zweiten „Weiter“ angenommen
        self.assertGreaterEqual(sum(1 for c in self.fakes[0].calls if c[0] == "Next"), 4)

    def test_ad_with_blocked_next_is_waited_out(self):
        def setup(fake):
            fake.block_next_on_ads = True
        result, _ = self.read_playlist(loop=True, setup=setup)
        self.assertEqual([t.artist for t in result["tracks"]], ["Wham!", "Mariah Carey", "Chris Rea"])
        self.assertTrue(result["complete"])

    def test_never_presses_next_during_ad(self):
        result, _ = self.read_playlist(loop=True)
        fake = self.fakes[0]
        self.assertEqual([t.artist for t in result["tracks"]], ["Wham!", "Mariah Carey", "Chris Rea"])
        self.assertTrue(fake.next_at)
        self.assertFalse([trackid for trackid in fake.next_at if "/ad/" in trackid])

    def test_same_song_twice_in_a_row_does_not_end_reading(self):
        tracks = [TRACKS[0], TRACKS[2], TRACKS[2], TRACKS[3]]
        result, _ = self.read_playlist(loop=False, tracks=tracks)
        self.assertEqual([t.artist for t in result["tracks"]], ["Wham!", "Mariah Carey", "Chris Rea"])

    def test_cancel_marks_result_incomplete(self):
        long = [dict(TRACKS[0], **{"mpris:trackid": f"/com/spotify/track/{i:022d}", "xesam:title": f"Song {i}"})
                for i in range(40)]
        result, _ = self.read_playlist(loop=True, tracks=long, cancel_after=2)
        self.assertFalse(result["complete"])
        self.assertIn("abgebrochen", result["reason"])

    def test_read_limit_and_empty_player(self):
        result, _ = self.read_playlist(loop=True, limit=2)
        self.assertEqual(len(result["tracks"]), 2)
        self.assertIn("Limit", result["reason"])
        self.tearDown()
        self.setUp()
        result, _ = self.read_playlist(loop=False, tracks=[])
        self.assertEqual(result["tracks"], [])
        self.assertFalse(result["complete"])
        self.assertIn("kein Titel", result["reason"])


class LaunchPlanTests(unittest.TestCase):
    def test_spotify_paths(self):
        song = Song("Last Christmas", "Wham!", "spotify:track:4uLU6hMCjMI75M1A2tKUQC")
        self.assertEqual(plan_launch(song, "spotify", True, True).method, "mpris")
        self.assertEqual(plan_launch(song, "spotify", False, True).uri, song.link)
        self.assertTrue(plan_launch(song, "spotify", False, False).uri.startswith("https://open.spotify.com/track/"))
        plain = Song("Last Christmas", "Wham!")
        plan = plan_launch(plain, "spotify", True, True)
        self.assertEqual((plan.method, plan.exact), ("uri", False))
        self.assertTrue(plan.uri.startswith("spotify:search:"))
        self.assertTrue(plan_launch(plain, "spotify", False, False).uri.startswith("https://open.spotify.com/search/"))

    def test_youtube_paths(self):
        video = Song("A", "B", "https://youtu.be/E8gmARGvPlI")
        self.assertEqual(plan_launch(Song("A", "B", "https://www.youtube.com/watch?v=E8gmARGvPlI"), "youtube", True, True).uri,
                         "https://www.youtube.com/watch?v=E8gmARGvPlI")
        self.assertEqual(video.link, "https://www.youtube.com/watch?v=E8gmARGvPlI")  # Modell normalisiert
        self.assertEqual(Song("A", "B", "https://example.com/x").link, "")
        self.assertIn("youtube.com/results", plan_launch(Song("A", "B"), "youtube", False, False).uri)
        with self.assertRaises(ValueError):
            plan_launch(Song("A"), "lokal", False, False)




if __name__ == "__main__":
    unittest.main()
