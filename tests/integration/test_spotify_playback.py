"""Spotify zuverlässig abspielen: Abspiel-Kontrolle, Warten auf den Start, Selbsttest.

Läuft gegen einen simulierten Spotify-Player auf einem privaten D-Bus – ohne echtes Spotify, ohne Netz.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    from gi.repository import Gio
    from tests.support.fake_mpris import TRACKS, FakePlayer, run_until
except (ImportError, ValueError):  # pragma: no cover
    Gio = None
if Gio is not None:  # ohne GTK-Bindings übersprungen; ein fehlendes App-Modul soll dagegen fehlschlagen
    from musik_bingo.domain.models import Song
    from musik_bingo.infrastructure import mpris, spotify

URI = "spotify:track:2FRnf9qhLbvw8fu4IBXx78"  # „Driving Home for Christmas“ (TRACKS[3])
RELINKED = "spotify:track:" + URI.rsplit(":", 1)[-1][::-1]  # so meldet der Fake im Modus „relinked“


def fake_metadata(fake) -> dict:
    """Metadaten, wie der Fake sie gerade meldet (ohne D-Bus)."""
    from tests.support.fake_mpris import metadata_variant
    return metadata_variant(fake.tracks[fake.position]).unpack()


@unittest.skipUnless(Gio is not None and shutil.which("dbus-daemon"), "D-Bus/PyGObject nicht verfügbar")
class SpotifyPlaybackTests(unittest.TestCase):
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
        self.players = []

    def tearDown(self):
        for player in self.players:
            player.close()
        for fake in self.fakes:
            fake.close()
        self.client.close_sync(None)
        self.bus.down()

    def fake(self, open_mode="play", status="Paused"):
        fake = FakePlayer(self.address, spotify.BUS_NAME, list(TRACKS), True)
        fake.open_mode = open_mode
        fake.status = status
        self.fakes.append(fake)
        return fake

    def player(self):
        info = mpris.choose_player(mpris.list_players(self.client), target="spotify")
        player = mpris.MprisPlayer(info, self.client)
        self.players.append(player)
        return player

    def check(self, open_mode, timeout_ms=600, **options):
        fake = self.fake(open_mode)
        result = []
        check = spotify.PlaybackCheck(self.player(), URI, lambda *args: result.append(args),
                                      timeout_ms=timeout_ms, poll_ms=50, **options)
        self.addCleanup(check.cancel)
        check.start()
        self.assertTrue(run_until(lambda: result, timeout=10))
        run_until(lambda: False, timeout=0.3)  # keine weiteren Aufrufe nach dem Ergebnis
        return fake, check, result

    @staticmethod
    def names(fake):
        return [call[0] for call in fake.calls]

    def test_link_from_metadata_reads_spotify_trackid(self):
        self.assertEqual(mpris.link_from_metadata({"mpris:trackid": "/com/spotify/track/2FRnf9qhLbvw8fu4IBXx78"}),
                         URI)
        self.assertEqual(mpris.link_from_metadata({"mpris:trackid": URI, "xesam:title": ""}), URI)
        self.assertEqual(mpris.link_from_metadata({"mpris:trackid": "/com/spotify/ad/1"}), "")
        self.assertEqual(mpris.link_from_metadata({}), "")

    def test_running_title_is_confirmed_without_extra_commands(self):
        fake, check, result = self.check("play")
        self.assertEqual(result, [(spotify.PlaybackCheck.PLAYING, "")])
        self.assertEqual(self.names(fake), ["OpenUri"])
        self.assertEqual(fake.calls[0][1], (URI,))
        self.assertTrue(check.saw_track)

    def test_paused_title_gets_one_play(self):
        fake, check, result = self.check("paused")
        self.assertEqual(result, [(spotify.PlaybackCheck.PLAYING, "")])
        self.assertEqual(self.names(fake), ["OpenUri", "Play"])
        self.assertTrue(check.play_sent)

    def test_title_that_never_plays_fails_after_single_play(self):
        fake, _check, result = self.check("stuck_paused")
        self.assertEqual(result[0][0], spotify.PlaybackCheck.FAILED)
        self.assertEqual(self.names(fake).count("Play"), 1)
        self.assertEqual(self.names(fake).count("OpenUri"), 1)

    def test_missing_title_is_opened_once_more(self):
        fake, check, result = self.check("ignore_once")
        self.assertEqual(result, [(spotify.PlaybackCheck.PLAYING, "")])
        self.assertEqual(self.names(fake), ["OpenUri", "OpenUri"])
        self.assertTrue(check.reopened)

    def test_ignored_open_uri_fails_after_one_retry(self):
        fake, _check, result = self.check("ignore")
        self.assertEqual(result, [(spotify.PlaybackCheck.FAILED, "")])
        self.assertEqual(self.names(fake), ["OpenUri", "OpenUri"])

    def test_rejected_open_uri_reports_error(self):
        fake = self.fake()
        fake.reject_open_uri = True
        result = []
        spotify.PlaybackCheck(self.player(), URI, lambda *args: result.append(args), timeout_ms=600, poll_ms=50).start()
        self.assertTrue(run_until(lambda: result, timeout=5))
        self.assertEqual(result[0][0], spotify.PlaybackCheck.OPEN_ERROR)
        self.assertIn("nicht unterstützt", result[0][1])

    def test_cancel_stops_everything(self):
        fake = self.fake("ignore")
        result = []
        check = spotify.PlaybackCheck(self.player(), URI, lambda *args: result.append(args), timeout_ms=300, poll_ms=50)
        check.start()
        run_until(lambda: False, timeout=0.1)
        check.cancel()
        run_until(lambda: False, timeout=1.2)  # länger als zwei Zeitfenster
        self.assertEqual(result, [])
        self.assertEqual(self.names(fake), ["OpenUri"])
        self.assertTrue(check.finished)

    # -- Langsames Spotify, „Relinking“ und späte Bestätigung

    def watch(self, fake, song=None, timeout_ms=400, late_ms=5000):
        result = []
        check = spotify.PlaybackCheck(self.player(), URI, lambda *args: result.append(args), timeout_ms=timeout_ms,
                                      poll_ms=50, song=song, late_ms=late_ms)
        self.addCleanup(check.cancel)
        check.start()
        return check, result

    def test_fake_reports_spotify_web_url_like_real_spotify(self):
        self.fake()
        metadata = self.player_loaded().metadata()
        self.assertEqual(metadata["xesam:url"], "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC")
        self.assertEqual(mpris.link_from_metadata(metadata), "spotify:track:4uLU6hMCjMI75M1A2tKUQC")

    def test_relinked_track_with_same_title_and_artist_counts_as_playing(self):
        fake = self.fake("relinked")
        check, result = self.watch(fake, song=Song("Driving Home for Christmas", "Chris Rea", URI))
        self.assertTrue(run_until(lambda: result, timeout=5))
        run_until(lambda: False, timeout=1.0)  # länger als das Zeitfenster: kein zweites OpenUri
        self.assertEqual(result, [(spotify.PlaybackCheck.PLAYING, "")])
        self.assertEqual(mpris.link_from_metadata(fake_metadata(fake)), RELINKED)
        self.assertEqual(self.names(fake), ["OpenUri"])

    def test_relinked_track_with_other_title_is_not_accepted(self):
        fake = self.fake("relinked")
        _check, result = self.watch(fake, song=Song("Last Christmas", "Wham!", URI), late_ms=0)
        self.assertTrue(run_until(lambda: result, timeout=5))
        self.assertEqual(result, [(spotify.PlaybackCheck.FAILED, "")])

    def test_slow_start_after_warning_is_reported_late(self):
        fake = self.fake("delayed")
        fake.start_delay_s = 1.5
        check, result = self.watch(fake)
        self.assertTrue(run_until(lambda: result, timeout=5))
        self.assertEqual(result, [(spotify.PlaybackCheck.FAILED, "")])  # Warnung nach der Prüfzeit …
        self.assertTrue(run_until(lambda: len(result) == 2, timeout=5))
        self.assertEqual(result[1], (spotify.PlaybackCheck.LATE_PLAYING, ""))  # … und Entwarnung, sobald er läuft
        self.assertTrue(check.finished)
        self.assertEqual(self.names(fake).count("OpenUri"), 1)
        self.assertEqual(fake.load_starts, 1)

    def test_changed_but_still_loading_title_is_not_opened_again(self):
        fake = self.fake("delayed")
        fake.start_delay_s = 1.5
        fake.loading_track = {"mpris:trackid": "/com/spotify/track/0000000000000000000000", "xesam:title": "Lädt …",
                              "xesam:artist": ["Spotify"]}
        _check, result = self.watch(fake)
        self.assertTrue(run_until(lambda: len(result) == 2, timeout=8))
        self.assertEqual([item[0] for item in result],
                         [spotify.PlaybackCheck.FAILED, spotify.PlaybackCheck.LATE_PLAYING])
        self.assertEqual(self.names(fake).count("OpenUri"), 1)  # kein Neustart des ladenden Titels
        self.assertEqual(fake.load_starts, 1)

    def test_late_watch_ends_quietly(self):
        fake = self.fake("ignore")
        check, result = self.watch(fake, timeout_ms=200, late_ms=1200)
        self.assertTrue(run_until(lambda: check.finished, timeout=5))
        run_until(lambda: False, timeout=0.3)
        self.assertEqual(result, [(spotify.PlaybackCheck.FAILED, "")])
        self.assertEqual(self.names(fake), ["OpenUri", "OpenUri"])

    def test_late_watch_stops_on_cancel(self):
        fake = self.fake("delayed")
        fake.start_delay_s = 1.2
        check, result = self.watch(fake, timeout_ms=200)
        self.assertTrue(run_until(lambda: result, timeout=5))
        check.cancel()
        run_until(lambda: False, timeout=1.5)
        self.assertEqual(result, [(spotify.PlaybackCheck.FAILED, "")])

    # -- Hängendes Spotify (besitzt den Busnamen, antwortet aber nie)

    def hung_player(self):
        process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "hung_player_process.py")],
                                   stdout=subprocess.PIPE, text=True,
                                   env=dict(os.environ, DBUS_SESSION_BUS_ADDRESS=self.address))
        self.addCleanup(process.wait, 5)
        self.addCleanup(process.kill)
        self.assertEqual(process.stdout.readline().strip(), "ready")
        process.stdout.close()
        os.kill(process.pid, signal.SIGSTOP)
        return process

    def test_hung_player_never_blocks_long(self):
        self.hung_player()
        start = time.monotonic()
        players = mpris.list_players(self.client)
        self.assertLess(time.monotonic() - start, 2.0)
        self.assertEqual([p.bus_name for p in players], [spotify.BUS_NAME])
        self.assertTrue(players[0].is_spotify)
        start = time.monotonic()
        player = mpris.MprisPlayer(players[0], self.client)
        self.players.append(player)
        self.assertLess(time.monotonic() - start, 1.0)
        result = []
        spotify.PlaybackCheck(player, URI, lambda *args: result.append(args), timeout_ms=600, poll_ms=50).start()
        self.assertTrue(run_until(lambda: result, timeout=6))
        self.assertEqual(result, [(spotify.PlaybackCheck.NO_REPLY, mpris.NOT_RESPONDING)])

    def test_self_test_reports_hung_player(self):
        self.hung_player()
        player = mpris.MprisPlayer(mpris.list_players(self.client)[0], self.client)
        self.players.append(player)
        outcome = []
        spotify.SelfTest(player, URI, outcome.append, check_timeout_ms=600, poll_ms=50).start()
        self.assertTrue(run_until(lambda: outcome, timeout=6))
        self.assertEqual((outcome[0].responding, outcome[0].can_control, outcome[0].started), (False, False, False))

    def player_loaded(self):
        player = self.player()
        self.assertTrue(run_until(lambda: player.loaded, timeout=3))
        return player

    def test_name_waiter_sees_late_player(self):
        result = []
        waiter = spotify.NameWaiter(spotify.BUS_NAME, 5000, result.append, connection=self.client)
        waiter.start()
        self.assertTrue(waiter.active)
        timer = threading.Timer(1.0, lambda: self.fake())
        timer.start()
        self.assertTrue(run_until(lambda: result, timeout=8))
        timer.join()
        self.assertEqual(result, [True])
        self.assertFalse(waiter.active)

    def test_name_waiter_times_out_and_can_be_cancelled(self):
        result = []
        spotify.NameWaiter(spotify.BUS_NAME, 400, result.append, connection=self.client).start()
        self.assertTrue(run_until(lambda: result, timeout=3))
        self.assertEqual(result, [False])
        cancelled = []
        waiter = spotify.NameWaiter(spotify.BUS_NAME, 300, cancelled.append, connection=self.client)
        waiter.start()
        waiter.cancel()
        run_until(lambda: False, timeout=0.6)
        self.assertEqual(cancelled, [])

    def self_test(self, open_mode="play", uri=URI, can_control=True):
        fake = self.fake(open_mode)
        fake.can_control = can_control
        outcome = []
        test = spotify.SelfTest(self.player(), uri, outcome.append, check_timeout_ms=600, pause_after_ms=300,
                                pause_timeout_ms=800, poll_ms=50)
        test.start()
        self.assertTrue(run_until(lambda: outcome, timeout=10))
        return fake, outcome[0]

    def test_self_test_plays_and_pauses(self):
        fake, outcome = self.self_test()
        self.assertEqual((outcome.can_control, outcome.started, outcome.paused), (True, True, True))
        self.assertEqual(self.names(fake), ["OpenUri", "Pause"])
        self.assertEqual(fake.status, "Paused")

    def test_self_test_reports_missing_start_and_control(self):
        fake, outcome = self.self_test("ignore", can_control=False)
        self.assertEqual((outcome.can_control, outcome.started, outcome.paused), (False, False, False))
        self.assertNotIn("Pause", self.names(fake))

    def test_self_test_without_link_only_checks_control(self):
        fake, outcome = self.self_test(uri="")
        self.assertEqual((outcome.can_control, outcome.started, outcome.paused), (True, False, False))
        self.assertEqual(fake.calls, [])


class DesktopLaunchTests(unittest.TestCase):
    def run_launch(self, desktop_id: str | None) -> tuple[str, bool]:
        """In eigenem Prozess, damit die App-Liste von Gio nur die Testordner sieht."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            marker = tmp / "gestartet"
            apps = tmp / "home" / "applications"
            apps.mkdir(parents=True)
            (tmp / "dirs").mkdir()
            if desktop_id:
                (apps / desktop_id).write_text(textwrap.dedent(f"""\
                    [Desktop Entry]
                    Type=Application
                    Name=Spotify
                    Exec=touch {marker}
                    """))
            env = dict(os.environ, XDG_DATA_HOME=str(tmp / "home"), XDG_DATA_DIRS=str(tmp / "dirs"))
            script = ("import sys; sys.path.insert(0, %r)\n"
                      "from musik_bingo.infrastructure import spotify\n"
                      "print(spotify.launch_desktop_app())") % str(ROOT)
            result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                                    timeout=30)
            for _ in range(100):
                if marker.exists():
                    break
                threading.Event().wait(0.05)
            return result.stdout.strip(), marker.exists()

    @unittest.skipUnless(Gio is not None and shutil.which("touch"), "Gio nicht verfügbar")
    def test_launches_installed_spotify_variant(self):
        for desktop_id in spotify.DESKTOP_IDS:
            with self.subTest(desktop_id=desktop_id):
                self.assertEqual(self.run_launch(desktop_id), ("True", True))

    @unittest.skipUnless(Gio is not None, "Gio nicht verfügbar")
    def test_reports_missing_spotify(self):
        self.assertEqual(self.run_launch(None), ("False", False))
        self.assertEqual(spotify.DESKTOP_IDS,
                         ("spotify.desktop", "spotify_spotify.desktop", "com.spotify.Client.desktop"))


if __name__ == "__main__":
    unittest.main()
