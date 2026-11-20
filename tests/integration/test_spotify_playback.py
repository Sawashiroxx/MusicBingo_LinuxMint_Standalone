"""Spotify zuverlässig abspielen: Abspiel-Kontrolle, Warten auf den Start, Selbsttest.

Läuft gegen einen simulierten Spotify-Player auf einem privaten D-Bus – ohne echtes Spotify, ohne Netz.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    from gi.repository import Gio
    from tests.support.fake_mpris import TRACKS, FakePlayer, run_until
except (ImportError, ValueError):  # pragma: no cover
    Gio = None
if Gio is not None:  # ohne GTK-Bindings übersprungen; ein fehlendes App-Modul soll dagegen fehlschlagen
    from musik_bingo.infrastructure import mpris, spotify

URI = "spotify:track:2FRnf9qhLbvw8fu4IBXx78"  # „Driving Home for Christmas“ (TRACKS[3])


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

    def check(self, open_mode, timeout_ms=600):
        fake = self.fake(open_mode)
        result = []
        check = spotify.PlaybackCheck(self.player(), URI, lambda *args: result.append(args),
                                      timeout_ms=timeout_ms, poll_ms=50)
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
