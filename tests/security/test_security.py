"""Sicherheits- und Datenschutztests.

Geprüft wird: keine Netzwerkzugriffe der App, strikte Link-Positivliste,
private Dateirechte, robuste Behandlung manipulierter Dateien und Daten,
keine Befehls-Injektion über Ordnernamen im Menüeintrag.
"""
import ast
import json
import os
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.links import normalize_link
from musik_bingo.domain.models import Song
from musik_bingo.domain.playlist import parse_playlist
from musik_bingo.infrastructure.file_store import FileStore
from musik_bingo.infrastructure.launcher import plan_launch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "musik_bingo"
ALLOWED_URI_PREFIXES = (
    "spotify:track:", "spotify:search:", "https://open.spotify.com/track/",
    "https://open.spotify.com/search/", "https://www.youtube.com/watch?v=",
    "https://www.youtube.com/results?search_query=",
)


def sample_service(songs: int = 10) -> GameService:
    service = GameService()
    service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(songs)))
    service.create_cards(3, False, 3)
    return service


class NoNetworkTests(unittest.TestCase):
    FORBIDDEN_MODULES = {"socket", "ssl", "requests", "httpx", "aiohttp", "urllib.request", "http.client",
                         "ftplib", "smtplib", "telnetlib", "xmlrpc", "socketserver", "webbrowser"}
    FORBIDDEN_GI = {"Soup", "WebKit2", "WebKit"}
    FORBIDDEN_ATTRS = {"SocketClient", "NetworkMonitor", "Resolver", "Socket"}

    def test_app_code_imports_no_network_or_shell_modules(self):
        problems = []
        for path in PACKAGE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                    if node.module == "gi.repository":
                        names += [a.name for a in node.names if a.name in self.FORBIDDEN_GI]
                for name in names:
                    if name in self.FORBIDDEN_MODULES or name in self.FORBIDDEN_GI or name.startswith("subprocess"):
                        problems.append(f"{path.relative_to(ROOT)}: import {name}")
                if isinstance(node, ast.Attribute) and node.attr in self.FORBIDDEN_ATTRS:
                    problems.append(f"{path.relative_to(ROOT)}: {node.attr}")
                if isinstance(node, ast.Attribute) and node.attr in ("system", "popen") and \
                        isinstance(node.value, ast.Name) and node.value.id == "os":
                    problems.append(f"{path.relative_to(ROOT)}: os.{node.attr}")
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("eval", "exec"):
                    problems.append(f"{path.relative_to(ROOT)}: {node.func.id}()")
        self.assertEqual(problems, [])

    def test_runtime_flows_open_no_sockets(self):
        """Startet typische Abläufe in einem eigenen Prozess, der jede Netzwerkaktion verbietet."""
        script = textwrap.dedent(f"""
            import sys, os, tempfile
            def hook(event, args):
                if event.startswith(("socket.", "urllib.Request", "http.client", "webbrowser", "subprocess.Popen", "os.system")):
                    raise SystemExit("NETZWERK/PROZESS: " + event)
            sys.addaudithook(hook)
            sys.path.insert(0, {str(ROOT)!r})
            os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
            from musik_bingo.domain.playlist import parse_playlist, to_csv, to_text, to_m3u
            from musik_bingo.domain.catalog import parse_catalog, random_mix, unique_songs
            from musik_bingo.domain.matching import SongMatcher, PlayingTrack
            from musik_bingo.paths import CATALOG_DIR
            from musik_bingo.application.game_service import GameService
            from musik_bingo.infrastructure.file_store import FileStore
            from musik_bingo.infrastructure.launcher import plan_launch
            catalogs = [parse_catalog(p.stem, p.read_text()) for p in CATALOG_DIR.glob("*.txt")]
            songs = random_mix(unique_songs([c for c in catalogs if c.category == "weihnachten"]),
                               unique_songs([c for c in catalogs if c.category == "charts"]), 40, 50).songs
            text = to_text(songs) + to_csv(songs)
            parse_playlist(text, "x.txt")
            service = GameService()
            from musik_bingo.domain.song_list import format_songs
            service.set_song_text(format_songs(songs))
            service.create_cards(5, True, 30)
            store = FileStore()
            store.save(service); store.load()
            SongMatcher(songs).find(PlayingTrack("Last Christmas", "Wham!", "https://youtu.be/E8gmARGvPlI"))
            for s in songs[:5]:
                plan_launch(s, "spotify", False, False); plan_launch(s, "youtube", False, False)
            print("OK")
        """)
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.stdout.strip(), "OK", result.stderr[-2000:])


class LinkWhitelistTests(unittest.TestCase):
    MALICIOUS = [
        "javascript:alert(1)", "file:///etc/passwd", "data:text/html,<script>", "vbscript:x",
        "http://evil.example/track", "https://open.spotify.com.evil.example/track/4uLU6hMCjMI75M1A2tKUQC",
        "https://evil.example/?u=https://www.youtube.com/watch?v=E8gmARGvPlI",
        "https://youtube.com.evil.example/watch?v=E8gmARGvPlI", "spotify:track:../../etc",
        "spotify:user:attacker", "spotify:track:4uLU6hMCjMI75M1A2tKUQC;rm -rf ~",
        "https://www.youtube.com/watch?v=E8gmARGvPl\n", "https://user:pw@evil.example/",
        "\x00spotify:track:4uLU6hMCjMI75M1A2tKUQC", "smb://server/share",
    ]

    def test_malicious_links_are_rejected(self):
        for link in self.MALICIOUS:
            with self.subTest(link=link):
                self.assertEqual(normalize_link(link), "")
                self.assertEqual(Song("A", "B", link).link, "")

    def test_fuzzed_links_only_produce_whitelisted_forms(self):
        rng = random.Random(4711)
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:/?#&=%.-_~@!$'()*+,;[] \t\n\x00üé"
        prefixes = ["", "spotify:track:", "https://open.spotify.com/track/", "https://youtu.be/",
                    "https://www.youtube.com/watch?v=", "http://", "file://", "javascript:"]
        for _ in range(5000):
            candidate = rng.choice(prefixes) + "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            result = normalize_link(candidate)
            if result:
                self.assertTrue(result.startswith(("spotify:track:", "https://www.youtube.com/watch?v=")), candidate)
                self.assertRegex(result, r"^(spotify:track:[A-Za-z0-9]{22}|https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11})$")

    def test_launch_uris_stay_on_allowed_hosts_for_any_title(self):
        rng = random.Random(42)
        alphabet = "abcXYZ ÄÖÜß/\\?#&=%.:;'\"<>|`$(){}[]\n\t\x00‮🎄"
        for _ in range(2000):
            title = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30)))
            artist = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 20)))
            song = Song(title, artist)
            for target in ("spotify", "youtube"):
                for mpris_on, scheme in ((True, True), (False, True), (False, False)):
                    uri = plan_launch(song, target, mpris_on, scheme).uri
                    self.assertTrue(uri.startswith(ALLOWED_URI_PREFIXES), uri)
                    self.assertFalse(any(ch in uri for ch in " \n\t\x00\"'<>`$|\\#"), uri)
                    # Nach dem festen Präfix darf kein weiterer Pfad/Host entstehen
                    rest = uri.split(":search:", 1)[-1].split("/search/", 1)[-1].split("search_query=", 1)[-1]
                    self.assertNotIn("/", rest)


class SaveFileTests(unittest.TestCase):
    def test_save_file_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "musik-bingo" / "spielstand.json"
            store = FileStore(path)
            store.save(sample_service())
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode & 0o077, 0, oct(mode))  # nur für den Benutzer lesbar
            # Fehler beim Schreiben: alter Stand bleibt, keine Temp-Dateien
            before = path.read_text()
            broken = sample_service()
            with mock.patch.object(GameService, "to_dict", side_effect=RuntimeError("Absturz")):
                with self.assertRaises(RuntimeError):
                    store.save(broken)
            self.assertEqual(path.read_text(), before)
            self.assertEqual([p.name for p in path.parent.iterdir()], ["spielstand.json"])

    def test_manipulated_save_files_are_rejected(self):
        base = sample_service().to_dict()
        cases = {
            "zu viele Songs": dict(base, songs=[{"title": f"S{i}"} for i in range(2001)]),
            "zu viele Karten": dict(base, cards=[base["cards"][0]] * 501),
            "bool als Zahl": dict(base, size=True),
            "Index außerhalb": dict(base, caller_index=10_000),
            "Titel kein Text": dict(base, songs=[{"title": ["x"]}] + base["songs"][1:]),
            "riesiger Titel": dict(base, songs=[{"title": "x" * 10_000}] + base["songs"][1:]),
            "Audiozuordnung kein Text": dict(base, audio_files={"song 0 – artist 0": 42}),
            "Version": dict(base, version=99),
            "Ziel unbekannt": dict(base, settings=dict(base["settings"], playback_target="../../etc")),
            "Liste statt Objekt": [base],
        }
        for name, data in cases.items():
            with self.subTest(name=name), self.assertRaises((ValueError, TypeError)):
                GameService.from_dict(json.loads(json.dumps(data)))

    def test_foreign_links_in_save_file_are_dropped(self):
        data = sample_service().to_dict()
        data["songs"][0]["link"] = "javascript:alert(1)"
        restored = GameService.from_dict(data)
        self.assertEqual(restored.game.songs[0].link, "")

    def test_deeply_nested_json_fails_without_hanging(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "boese.json"
            path.write_text("[" * 200_000 + "]" * 200_000)
            start = time.perf_counter()
            with self.assertRaises((RecursionError, ValueError)):
                FileStore.import_from(path)
            self.assertLess(time.perf_counter() - start, 5)


class EveningInputTests(unittest.TestCase):
    """Feiertitel und Gewinnernamen landen auf Karten, Beamer, CSV – nur sauberer Text."""

    def test_title_and_names_are_cleaned_in_save_files(self):
        data = sample_service().to_dict()
        data["settings"]["event_title"] = "\u202eFeier\x00\n" + "x" * 5000
        data["winners"] = [{"round": 1, "target": "reihe", "card": 1, "name": "\u2066Name\x1b[31m" + "y" * 900,
                            "song_count": 5}]
        restored = GameService.from_dict(data)
        self.assertEqual(len(restored.event_title), 60)
        self.assertTrue(restored.event_title.startswith("Feier"))
        name = restored.winners[0].name
        self.assertLessEqual(len(name), 60)
        self.assertFalse(any(ord(char) < 32 or char in "\u202e\u2066" for char in name))

    def test_too_many_winners_are_rejected(self):
        data = sample_service().to_dict()
        data["winners"] = [{"round": 1, "target": "reihe", "card": 1, "name": "", "song_count": 1}] * 1001
        with self.assertRaises(ValueError):
            GameService.from_dict(data)

    def test_csv_export_neutralizes_formulas_everywhere(self):
        from musik_bingo.domain.evening import Winner, winners_csv
        text = winners_csv([Winner(1, "reihe", 3, "@SUMME(A1)", 4)], "=cmd|' /C calc'!A0")
        for cell in ("=cmd", "@SUMME"):
            self.assertNotIn("," + cell, "," + text.replace("\n", ","))


class ImportLimitTests(unittest.TestCase):
    def test_large_files_are_refused(self):
        try:
            from musik_bingo.presentation.dialogs import read_text_file
        except (ImportError, ValueError) as error:  # pragma: no cover
            self.skipTest(f"GTK nicht verfügbar: {error}")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gross.csv"
            with open(path, "wb") as handle:
                handle.truncate(6 * 1024 * 1024)
            with self.assertRaisesRegex(ValueError, "5 MB"):
                read_text_file(path)
            latin = Path(directory) / "latin.txt"
            latin.write_bytes("Süßer die Glocken - Traditional".encode("latin-1"))
            self.assertIn("Süßer", read_text_file(latin))

    def test_import_caps_and_binary_garbage(self):
        result = parse_playlist(os.urandom(200_000).decode("latin-1"), "x.txt")
        self.assertLessEqual(len(result.songs), 2000)
        self.assertTrue(all(len(s.title) <= 300 and len(s.artist) <= 300 for s in result.songs))


class PlayerDataTests(unittest.TestCase):
    def test_hostile_mpris_metadata_is_handled(self):
        try:
            from musik_bingo.infrastructure.mpris import track_from_metadata, track_identity
        except (ImportError, ValueError) as error:  # pragma: no cover
            self.skipTest(str(error))
        samples = [
            None, {}, {"xesam:title": None}, {"xesam:title": 5, "xesam:artist": 7},
            {"xesam:title": "x" * 1_000_000, "xesam:artist": ["y" * 100_000] * 10},
            {"xesam:title": "Song", "xesam:url": "javascript:alert(1)"},
            {"xesam:title": "Song", "mpris:trackid": "/com/spotify/track/../../etc"},
            {"xesam:title": "Werbung", "mpris:trackid": "spotify:ad:123"},
        ]
        for metadata in samples:
            with self.subTest(metadata=str(metadata)[:60]):
                track = track_from_metadata(metadata)
                track_identity(metadata)
                if track is not None:
                    self.assertEqual(normalize_link(track.url), track.url)
        self.assertIsNone(track_from_metadata(samples[-1]))


class AudioPlayerTests(unittest.TestCase):
    def test_only_existing_local_files_are_played(self):
        try:
            from musik_bingo.infrastructure.audio_player import AudioPlayer
            from gi.repository import Gst
            Gst.init(None)
            sink = Gst.ElementFactory.make("fakesink", None)
            player = AudioPlayer(audio_sink=sink, watch_bus=False)
        except (ImportError, ValueError, RuntimeError, TypeError) as error:
            self.skipTest(f"GStreamer nicht verfügbar: {error}")
        for target in ("http://evil.example/x.mp3", "https://evil.example/x.mp3", "/nicht/vorhanden.mp3",
                       "smb://server/x.mp3"):
            with self.subTest(target=target), self.assertRaises(FileNotFoundError):
                player.play(Path(target))
        player.close()


class DesktopEntryInjectionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("desktop-file-validate"), "desktop-file-utils fehlt")
    def test_folder_name_cannot_inject_commands(self):
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio
        except (ImportError, ValueError) as error:  # pragma: no cover
            self.skipTest(str(error))
        with tempfile.TemporaryDirectory() as tmp:
            evil = Path(tmp) / 'Feier $(touch PWNED) `touch PWNED2` "x" 100% \\ ;touch PWNED3'
            (evil / "scripts").mkdir(parents=True)
            shutil.copytree(ROOT / "musik_bingo" / "data" / "icons", evil / "musik_bingo" / "data" / "icons")
            shutil.copy(ROOT / "scripts" / "install-desktop.sh", evil / "scripts")
            marker = Path(tmp) / "gestartet"
            (evil / "scripts" / "starten.sh").write_text(f'#!/bin/bash\necho "$0" > "{marker}"\n')
            data_home = Path(tmp) / "share"
            subprocess.run(["bash", str(evil / "scripts" / "install-desktop.sh")], check=True, capture_output=True,
                           env=dict(os.environ, XDG_DATA_HOME=str(data_home)), cwd=tmp)
            desktop = data_home / "applications" / "musik-bingo.desktop"
            subprocess.run(["desktop-file-validate", str(desktop)], check=True)
            info = Gio.DesktopAppInfo.new_from_filename(str(desktop))
            self.assertIsNotNone(info)
            info.launch([], None)
            for _ in range(100):
                if marker.exists():
                    break
                time.sleep(0.05)
            self.assertEqual(marker.read_text().strip(), str(evil / "scripts" / "starten.sh"))
            leftovers = [p.name for p in Path(tmp).rglob("PWNED*")] + [p.name for p in Path.cwd().glob("PWNED*")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
