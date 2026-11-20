"""E2E: Spotify zuverlässig abspielen – Abspiel-Kontrolle, Autostart, „Spotify testen“, „Nach Ablauf pausieren“.

Aufruf: spotify_abspielen.py <pausiert|ignoriert|start|test|pause>
Spotify wird als eigener Prozess simuliert (tests/support/fake_player_process.py) – kein echtes Spotify, kein Netz.
"""
import json
import subprocess
import sys
import time

from common import MESSAGES, ROOT, TMP, check, forbid_network, patch_dialogs, pump, run, wait

from gi.repository import GLib

MODE = sys.argv[1] if len(sys.argv) > 1 else "pausiert"
LOG = TMP / "fake.json"
PROCESSES: list[subprocess.Popen] = []
WARNING = "Spotify hat den Titel nicht gestartet – bitte in Spotify prüfen"
# Titel → Spotify-ID. Bewusst keine der IDs, die der simulierte Player beim Start schon „spielt“ –
# sonst wäre „läuft bereits“ je nach zufälliger Ziehung richtig und der Test nicht eindeutig.
SONGS = {f"Song {i} – Artist {i}": f"{i:02d}" + "A" * 20 for i in range(13)}


def start_fake(kind: str = "spotify", delay: float = 0.0, wait_ready: bool = True) -> subprocess.Popen:
    process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "fake_player_process.py"), str(LOG),
                                kind, str(delay)], stdout=subprocess.PIPE, text=True)
    PROCESSES.append(process)
    if wait_ready:
        assert process.stdout.readline().strip() == "ready"
    return process


def state():
    try:
        return json.loads(LOG.read_text())
    except (OSError, ValueError):
        return {"calls": [], "pos": -1, "status": ""}


def calls(name: str, uri: str | None = None) -> int:
    return sum(1 for method, args in state()["calls"] if method == name and (uri is None or args == [uri]))


def uri_of(song) -> str:
    return song.link


def setup_round(w, with_links: int | None = None) -> None:
    lines = []
    for index, (song, track_id) in enumerate(SONGS.items()):
        linked = with_links is None or index < with_links
        lines.append(f"{song} | spotify:track:{track_id}" if linked else song)
    w.song_buffer.set_text("\n".join(lines))
    w.size_combo.set_active(0)
    w.free_check.set_active(False)
    w.count_spin.set_value(3)
    w._generate(None)
    w.target_buttons["spotify"].set_active(True)


class LoopWatch:
    """Misst, ob der GTK-Hauptloop flüssig bleibt (kein blockierender D-Bus-Aufruf)."""

    def __init__(self):
        self.last = time.monotonic()
        self.max_gap = 0.0
        GLib.timeout_add(20, self._tick)

    def _tick(self) -> bool:
        now = time.monotonic()
        self.max_gap = max(self.max_gap, now - self.last)
        self.last = now
        return True


def status(w) -> str:
    return w.status.get_text() + " | " + w.audio_status.get_text()


def scenario_paused(w):
    start_fake("spotify-pausiert")
    setup_round(w)
    w.auto_play_check.set_active(True)
    watch = LoopWatch()
    w._draw_next()
    song = w.service.game.caller.current
    check("Status: läuft in Spotify", wait(lambda: f"Läuft in Spotify: {song.display_name}" in status(w), 8))
    check("genau ein OpenUri", wait(lambda: calls("OpenUri", uri_of(song)) == 1, 2))
    check("pausierter Titel bekam einmal Play", wait(lambda: calls("Play") == 1 and state()["status"] == "Playing", 2))
    check("keine Warnung", not w.warning_revealer.get_reveal_child())
    check("Hauptloop blockiert nie", watch.max_gap < 0.5)


def scenario_ignored(w):
    start_fake("spotify-ignoriert")
    setup_round(w)
    w.auto_play_check.set_active(True)
    watch = LoopWatch()
    w._draw_next()
    first = w.service.game.caller.current
    check("Warnung nach Wiederholung",
          wait(lambda: w.warning_revealer.get_reveal_child() and WARNING in w.warning_label.get_text(), 10))
    check("Warnung nennt den Song", first.title in w.warning_label.get_text())
    check("OpenUri genau einmal wiederholt", wait(lambda: calls("OpenUri", uri_of(first)) == 2, 2))
    check("Warnung ist kein Dialog", MESSAGES == [])
    check("kein „Überspringen“ bei Spotify-Warnung", not w.warning_skip_button.get_visible())
    check("Hauptloop blockiert nie", watch.max_gap < 0.5)

    # Neues Ziehen bricht die laufende Kontrolle ab: keine Meldungen zu alten Songs
    w._draw_next()
    second = w.service.game.caller.current
    check("neues Ziehen blendet alte Warnung aus", not w.warning_revealer.get_reveal_child())
    pump(0.5)
    w._draw_next()
    third = w.service.game.caller.current
    check("Warnung zum neuesten Song", wait(lambda: w.warning_revealer.get_reveal_child(), 10)
          and third.title in w.warning_label.get_text() and second.title not in w.warning_label.get_text())
    pump(3.0)
    check("abgebrochene Kontrolle wiederholt nichts", calls("OpenUri", uri_of(second)) == 1)


def scenario_start(w):
    from musik_bingo.infrastructure import spotify
    from musik_bingo.presentation import gtk_app

    opened = []
    gtk_app.open_uri = opened.append
    launches = []
    setup_round(w)
    w.auto_play_check.set_active(True)
    w.spotify_scheme = False

    # 1. Spotify nicht installiert → bisheriger Rückfall (Webplayer)
    def missing():
        launches.append("fehlt")
        return False
    spotify.launch_desktop_app = missing
    w._draw_next()
    song = w.service.game.caller.current
    check("nicht installiert: Webplayer geöffnet",
          wait(lambda: opened == ["https://open.spotify.com/track/" + song.link.rsplit(":", 1)[-1]]))
    check("Startversuch gemacht", launches == ["fehlt"])

    # 2. Start ohne Rückmeldung → nach Zeitüberschreitung Rückfall, nur für den neuesten Song
    def silent():
        launches.append("stumm")
        return True
    spotify.launch_desktop_app = silent
    w.spotify_start_timeout_ms = 1500
    opened.clear()
    w._draw_next()
    old = w.service.game.caller.current
    check("Status: Spotify wird gestartet", "Spotify wird gestartet …" in status(w))
    w._draw_next()
    new = w.service.game.caller.current
    check("während des Wartens kein zweiter Start", launches.count("stumm") == 1)
    check("Zeitüberschreitung: Rückfall für den neuen Song",
          wait(lambda: opened, 5) and opened == ["https://open.spotify.com/track/" + new.link.rsplit(":", 1)[-1]])
    check("alter Song nicht geöffnet", not any(old.link.rsplit(":", 1)[-1] in uri for uri in opened))

    # 3. Spotify startet (meldet sich erst nach 1 s am Bus) → OpenUri + Kontrolle
    def launch():
        launches.append("echt")
        start_fake("spotify", delay=1.0, wait_ready=False)
        return True
    spotify.launch_desktop_app = launch
    w.spotify_start_timeout_ms = 15_000
    opened.clear()
    watch = LoopWatch()
    w._draw_next()
    song = w.service.game.caller.current
    check("Status: Spotify wird gestartet (2)", "Spotify wird gestartet …" in status(w))
    check("nach dem Start: läuft in Spotify",
          wait(lambda: f"Läuft in Spotify: {song.display_name}" in status(w), 10))
    check("OpenUri an gestartetes Spotify", wait(lambda: calls("OpenUri", uri_of(song)) == 1, 2))
    check("kein Rückfall geöffnet", opened == [])
    check("Hauptloop blockiert nie beim Warten", watch.max_gap < 0.5)
    check("mit Spotify verbunden", w.player is not None and w.player.info.is_spotify)


def scenario_test(w):
    from musik_bingo.infrastructure import spotify
    from musik_bingo.presentation import dialogs

    shown = []
    dialogs.message = lambda parent, kind, title, detail: shown.append((title, detail))
    setup_round(w, with_links=len(SONGS) - 2)
    check("Knopf bei Spotify sichtbar", w.spotify_test_button.get_visible() and w.spotify_test_button.get_sensitive())
    w.target_buttons["lokal"].set_active(True)
    check("Knopf bei lokalen Dateien unsichtbar", not w.spotify_test_button.get_visible())
    w.target_buttons["youtube"].set_active(True)
    check("Knopf bei YouTube unsichtbar", not w.spotify_test_button.get_visible())
    w.target_buttons["spotify"].set_active(True)
    w.service.game.caller.draw_next()
    w.service.game.caller.draw_next()
    w._render_caller()
    w._save()
    before = json.dumps(w.service.to_dict(), sort_keys=True)
    launches = []

    def launch():
        launches.append(1)
        start_fake("spotify", delay=1.0, wait_ready=False)
        return True
    spotify.launch_desktop_app = launch
    expected = w.service.game.caller.current
    if not expected.link:
        expected = next(song for song in w.service.game.songs if song.link)
    w._spotify_test(None)
    check("Knopf während des Tests gesperrt", not w.spotify_test_button.get_sensitive())
    w._spotify_test(None)
    check("keine zweite Ausführung", launches == [1])
    check("Dialog mit Prüfliste", wait(lambda: shown, 20))
    title, detail = shown[0] if shown else ("", "")
    print(detail, flush=True)
    check("Dialogtitel", title == "Spotify-Test")
    for line in ("✓ Spotify gefunden", "✓ Steuerung möglich", "✓ Titel gestartet", "✓ Pause funktioniert",
                 f"✗ {len(SONGS) - 2} von {len(SONGS)} Songs mit Spotify-Link", "Einstellungen → Autoplay ausschalten"):
        check(f"Prüfliste: {line}", line in detail)
    check("Testsong per OpenUri gespielt", wait(lambda: calls("OpenUri", expected.link) == 1, 2))
    check("Spotify danach pausiert", wait(lambda: calls("Pause") == 1 and state()["status"] == "Paused", 2))
    check("Spielstand unverändert", json.dumps(w.service.to_dict(), sort_keys=True) == before)
    check("Knopf wieder frei", w.spotify_test_button.get_sensitive())
    check("nur ein Dialog", len(shown) == 1)


class AudioStub:
    def __init__(self):
        self.is_playing, self.is_paused, self.paused = True, False, 0

    def pause(self):
        self.paused += 1
        self.is_paused = True

    def stop(self):
        self.is_playing = self.is_paused = False

    def play(self, _path):
        self.is_playing, self.is_paused = True, False

    def close(self):
        pass


def scenario_pause(w):
    start_fake("spotify")
    setup_round(w)
    check("„Nach Ablauf pausieren“ standardmäßig an", w.pause_after_check.get_active())
    w.auto_play_check.set_active(True)
    w.timer_spin.set_value(2)
    w.reveal_spin.set_value(3)
    w._draw_next()
    check("Titel läuft", wait(lambda: "Läuft in Spotify" in status(w), 8))
    check("nach Ablauf pausiert (Spotify)", wait(lambda: w.timer.phase == "auflösung", 5)
          and wait(lambda: calls("Pause") == 1 and state()["status"] == "Paused", 3))

    w.pause_after_check.set_active(False)
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Einstellung gespeichert", saved["settings"]["pause_after_timer"] is False)
    w._draw_next()
    check("Titel läuft (2)", wait(lambda: state()["status"] == "Playing", 8))
    check("ausgeschaltet: kein Pause", wait(lambda: w.timer.phase == "auflösung", 5) and pump(0.6) is None
          and calls("Pause") == 1)
    w.pause_after_check.set_active(True)

    # Lokale Dateien: GStreamer-Player wird pausiert
    w.target_buttons["lokal"].set_active(True)
    stub = AudioStub()
    w.audio_player = stub
    w._new_song_started()
    stub.is_playing, stub.is_paused = True, False
    check("lokal: nach Ablauf pausiert", wait(lambda: w.timer.phase == "auflösung", 5) and wait(lambda: stub.paused == 1, 2))

    # YouTube: nichts pausieren
    w.target_buttons["youtube"].set_active(True)
    stub.is_playing, stub.is_paused, stub.paused = True, False, 0
    pauses = calls("Pause")
    w._new_song_started()
    check("YouTube: nichts pausiert", wait(lambda: w.timer.phase == "auflösung", 5) and pump(0.6) is None
          and stub.paused == 0 and calls("Pause") == pauses)

    # Folgen-Modus: unverändert, kein Pause
    w.target_buttons["spotify"].set_active(True)
    w.follow_switch.set_active(True)
    check("Folgen aktiv", w.follow_switch.get_active())
    pauses = calls("Pause")
    w._new_song_started()
    check("Folgen-Modus: kein Pause", wait(lambda: w.timer.phase == "auflösung", 5) and pump(0.6) is None
          and calls("Pause") == pauses)
    check("Häkchen im Folgen-Modus gesperrt", not w.pause_after_check.get_sensitive())


SCENARIOS = {"pausiert": scenario_paused, "ignoriert": scenario_ignored, "start": scenario_start,
             "test": scenario_test, "pause": scenario_pause}

forbid_network()
patch_dialogs()
try:
    run(SCENARIOS[MODE])
finally:
    for process in PROCESSES:
        if process.poll() is None:
            process.terminate()
