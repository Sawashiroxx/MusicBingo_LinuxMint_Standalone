"""GUI- und Ende-zu-Ende-Tests: echte GTK-Fenster unter Xvfb, eigener D-Bus pro Lauf.

Werden übersprungen, wenn xvfb-run oder dbus-run-session fehlen.
Screenshots landen in $SCREENSHOT_DIR (Standard: temporärer Ordner).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parent / "scenarios"
TOOLS = shutil.which("xvfb-run") and shutil.which("dbus-run-session")


@unittest.skipUnless(TOOLS, "xvfb-run und dbus-run-session werden für GUI-Tests benötigt")
class GuiTests(unittest.TestCase):
    def scenario(self, name: str, *args: str, timeout: int = 180) -> str:
        command = ["dbus-run-session", "--", "xvfb-run", "-a", "-s", "-screen 0 1600x1000x24",
                   sys.executable, str(SCENARIOS / name), *args]
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=SCENARIOS)
        output = result.stdout + "\n" + "\n".join(
            line for line in result.stderr.splitlines() if "Traceback" in line or "Error" in line or line.startswith("  "))
        self.assertEqual(result.returncode, 0, f"{name} {' '.join(args)} fehlgeschlagen:\n{output[-4000:]}")
        self.assertNotIn("FAIL ", result.stdout)
        return result.stdout

    def test_full_game_flow(self):
        self.scenario("full_flow.py")

    def test_evening_features(self):
        """Titel, Beamer, Timer, Gewinnerliste, Stufen und Runden im echten Fenster."""
        self.scenario("feier.py")

    def test_follow_spotify_end_to_end(self):
        self.scenario("follow_spotify.py")

    def test_bingo_check_without_card_number(self):
        self.scenario("ohne_nummer.py")

    @unittest.skipUnless(shutil.which("xdotool"), "xdotool fehlt – echte Tastendrücke nicht möglich (CI installiert es)")
    def test_shortcuts_with_real_keystrokes(self):
        """Regression: Leertaste/T wirkten mit echten Tastendrücken nicht (nur im Direktaufruf)."""
        self.scenario("tasten.py")

    def test_spotify_open_uri_fallback_uses_web_player(self):
        self.scenario("spotify_fallback.py")

    def test_spotify_playback_is_checked_started_tested_and_paused(self):
        """Abspiel-Kontrolle, Spotify-Autostart, „Spotify testen“ und „Nach Ablauf pausieren“.

        haengt: Spotify antwortet nicht – Oberfläche bleibt bedienbar. spaet: Titel startet nach der Prüfzeit.
        testabbruch: abgebrochener und neu gestarteter Test läuft nur einmal. pause_kontrolle: nach der
        Pause zum Ende der Spielzeit sendet die Kontrolle kein „Play“ mehr.
        """
        for mode in ("pausiert", "ignoriert", "start", "test", "pause", "haengt", "spaet", "testabbruch",
                     "pause_kontrolle"):
            with self.subTest(mode=mode):
                self.scenario("spotify_abspielen.py", mode)

    def test_follow_youtube_in_browser_end_to_end(self):
        self.scenario("follow_youtube.py")

    def test_edge_cases(self):
        for mode in ("broken", "deep", "defaults", "empty", "big"):
            with self.subTest(mode=mode):
                self.scenario("edge_cases.py", mode)

    @unittest.skipUnless(shutil.which("xprop"), "xprop (x11-utils) fehlt")
    def test_window_class_matches_desktop_entry(self):
        """Die Taskleiste ordnet das Fenster nur bei passender WM_CLASS dem Menüeintrag zu."""
        self.scenario("window_class.py")

    def test_table_text_is_readable_in_both_themes(self):
        """Regression: Dateidialog war im dunklen Design unlesbar (weiße Zellen, heller Text)."""
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                self.scenario("contrast.py", theme)

    def test_spotify_link_overview(self):
        """Chip „Spotify: x von y“, Dialog „Spotify-Links“ und Link-Übernahme beim Playlist-Abgleich."""
        target = Path(os.environ.get("SCREENSHOT_DIR") or tempfile.mkdtemp(prefix="links-"))
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                self.scenario("spotify_links.py", theme, str(target))
        self.assertEqual(len(list(target.glob("links-*.png"))), 6)  # Dialog, Songliste, Spielleitung × 2

    def test_screenshots_render_in_both_themes(self):
        target = Path(os.environ.get("SCREENSHOT_DIR") or tempfile.mkdtemp(prefix="screens-"))
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                self.scenario("screenshots.py", theme, str(target))
        self.assertGreaterEqual(len(list(target.glob("*.png"))), 14)  # 7 Ansichten × 2 Designs


if __name__ == "__main__":
    unittest.main()
