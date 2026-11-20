"""E2E: Spotify zuverlässig abspielen – Abspiel-Kontrolle, Autostart, „Spotify testen“, „Nach Ablauf pausieren“.

Aufruf: spotify_abspielen.py <pausiert|ignoriert|start|test|pause|haengt|spaet|testabbruch|pause_kontrolle>
Spotify wird als eigener Prozess simuliert (tests/support/fake_player_process.py) – kein echtes Spotify, kein Netz.
"""
import json
import os
import signal
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


def start_fake(kind: str = "spotify", delay: float = 0.0, wait_ready: bool = True,
               kind_seconds: float = 3.0) -> subprocess.Popen:
    process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "fake_player_process.py"), str(LOG),
                                kind, str(delay), str(kind_seconds)], stdout=subprocess.PIPE, text=True)
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
    # Ziehreihenfolge festlegen: erst ein Song mit Link (nicht der erste der Liste), dann einer ohne Link.
    # Der Test darf dann nur den bereits gezogenen Song spielen – nie einen noch nicht gezogenen (Gäste hören mit).
    caller = w.service.game.caller
    linked = [song for song in w.service.game.songs if song.link]
    plain = next(song for song in w.service.game.songs if not song.link)
    caller.order.remove(linked[4])
    caller.order.remove(plain)
    caller.order[:0] = [linked[4], plain]
    caller.draw_next()
    caller.draw_next()
    w._render_caller()
    w._save()
    before = json.dumps(w.service.to_dict(), sort_keys=True)
    launches = []

    def launch():
        launches.append(1)
        start_fake("spotify", delay=1.0, wait_ready=False)
        return True
    spotify.launch_desktop_app = launch
    expected = linked[4]
    check("aktueller Song ohne Link", not caller.current.link)
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
    check("kein noch nicht gezogener Song gespielt", calls("OpenUri") == 1
          and calls("OpenUri", linked[0].link) == 0)
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

    # Regression (Fable): Auflösung 0 s → es gab kein „reveal“, Spotify spielte den alten Song weiter
    w.auto_play_check.set_active(False)
    w.reveal_spin.set_value(0)
    w._draw_next()
    w._play_audio(None)
    check("Titel läuft (Auflösung 0)", wait(lambda: state()["status"] == "Playing", 8))
    drawn_before, pauses = len(w.service.game.caller.drawn), calls("Pause")
    check("Auflösung 0: nach Ablauf pausiert und nächster Song gezogen",
          wait(lambda: len(w.service.game.caller.drawn) == drawn_before + 1, 6)
          and wait(lambda: calls("Pause") == pauses + 1 and state()["status"] == "Paused", 3))
    # Mit automatischem Abspielen übernimmt der nächste Titel – kein überflüssiges Pause davor
    w.auto_play_check.set_active(True)
    w._draw_next()
    check("Titel läuft (Autoplay, Auflösung 0)", wait(lambda: "Läuft in Spotify" in status(w), 8))
    drawn_before, pauses = len(w.service.game.caller.drawn), calls("Pause")
    check("Auflösung 0 + Autoplay: kein Pause, nächster Titel startet",
          wait(lambda: len(w.service.game.caller.drawn) == drawn_before + 1, 6) and pump(0.6) is None
          and calls("Pause") == pauses and wait(lambda: state()["status"] == "Playing", 8))
    # Regression (Fable, 2. Durchgang): Nächster Song ohne Spotify-Link startet nicht automatisch –
    # der alte Titel muss trotz Autoplay pausieren
    from musik_bingo.domain.models import Song
    caller = w.service.game.caller
    nxt = caller.order[caller.index + 1]
    caller.order[caller.index + 1] = Song(nxt.title, nxt.artist)  # ohne Link
    check("Titel läuft (vor Song ohne Link)", wait(lambda: state()["status"] == "Playing", 8))
    drawn_before, pauses = len(caller.drawn), calls("Pause")
    w._new_song_started()
    check("nächster Song ohne Link: alter Titel pausiert",
          wait(lambda: len(caller.drawn) == drawn_before + 1, 6)
          and wait(lambda: calls("Pause") == pauses + 1 and state()["status"] == "Paused", 3))
    # Ohne Verbindung zu Spotify: ehrlicher Hinweis statt stiller Untätigkeit
    w.auto_play_check.set_active(False)
    w._disconnect_player()
    w._new_song_started()
    check("ohne Verbindung: Hinweis „bitte von Hand pausieren“",
          wait(lambda: "nicht verbunden" in status(w), 6))
    w.auto_play_check.set_active(True)
    w.reveal_spin.set_value(3)

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


def scenario_hung(w):
    """Spotify besitzt den Busnamen, antwortet aber nicht: Die Oberfläche darf nicht einfrieren."""
    from musik_bingo.presentation import gtk_app

    process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "hung_player_process.py")],
                               stdout=subprocess.PIPE, text=True)
    PROCESSES.append(process)
    assert process.stdout.readline().strip() == "ready"
    os.kill(process.pid, signal.SIGSTOP)
    opened = []
    gtk_app.open_uri = opened.append
    shown = []
    gtk_app.dialogs.message = lambda parent, kind, title, detail: shown.append((title, detail))
    setup_round(w)
    w.auto_play_check.set_active(True)
    pump(0.3)
    watch = LoopWatch()
    started = time.monotonic()
    w._draw_next()
    print(f"Ziehen blockierte {time.monotonic() - started:.1f} s", flush=True)
    song = w.service.game.caller.current
    check("Meldung: Spotify reagiert nicht", wait(lambda: "Spotify reagiert nicht" in status(w), 10))
    check("Rückfall: Titel anders geöffnet", wait(lambda: len(opened) == 1, 2)
          and song.link.rsplit(":", 1)[-1] in opened[0])
    check("Hauptloop beim Ziehen < 3 s blockiert", watch.max_gap < 3.0)
    print(f"größte Lücke beim Ziehen: {watch.max_gap:.1f} s", flush=True)

    watch = LoopWatch()
    started = time.monotonic()
    w._spotify_test(None)
    print(f"„Spotify testen“ blockierte {time.monotonic() - started:.1f} s", flush=True)
    check("Test-Dialog kommt", wait(lambda: shown, 15))
    detail = shown[0][1] if shown else ""
    print(detail, flush=True)
    check("Prüfliste: Spotify gefunden", "✓ Spotify gefunden" in detail)
    check("Prüfliste: Steuerung nicht möglich", "✗ Steuerung möglich" in detail)
    check("Hinweis: Spotify reagiert nicht", "Spotify reagiert nicht" in detail)
    check("Hauptloop bei „Spotify testen“ < 3 s blockiert", watch.max_gap < 3.0)
    print(f"größte Lücke beim Test: {watch.max_gap:.1f} s", flush=True)


def scenario_late(w):
    """Spotify startet den Titel erst nach der Prüfzeit: Warnung erscheint und verschwindet wieder."""
    start_fake("spotify-verzoegert", kind_seconds=4.0)
    setup_round(w)
    w.playback_check_ms = 1000
    w.auto_play_check.set_active(True)
    w._draw_next()
    song = w.service.game.caller.current
    check("Warnung nach der Prüfzeit", wait(lambda: w.warning_revealer.get_reveal_child()
                                            and WARNING in w.warning_label.get_text(), 6))
    check("Warnung verschwindet, sobald der Titel läuft",
          wait(lambda: not w.warning_revealer.get_reveal_child(), 10))
    check("Status: läuft jetzt in Spotify", f"Läuft jetzt in Spotify: {song.display_name}" in status(w))
    check("ladender Titel nicht neu gestartet", calls("OpenUri", uri_of(song)) == 1 and state()["load_starts"] == 1)
    check("Titel läuft", wait(lambda: state()["status"] == "Playing", 3))


def scenario_retry(w):
    """Regression (Fable, 2. Durchgang): Nach „Abspielen“ läuft der Titel – die alte Warnung muss weg.
    Und: „Karten erzeugen“ beendet die stille Nachbeobachtung (keine Meldung zu alten Songs)."""
    start_fake("spotify-verzoegert", kind_seconds=4.0)
    setup_round(w)
    w.playback_check_ms = 1000
    w.auto_play_check.set_active(True)
    w._draw_next()
    song = w.service.game.caller.current
    check("Warnung nach der Prüfzeit", wait(lambda: w.warning_revealer.get_reveal_child()
                                            and WARNING in w.warning_label.get_text(), 6))
    w.playback_check_ms = 6000  # zweiter Versuch: genug Zeit, der Titel startet darin
    w._play_audio(None)
    check("erneutes Abspielen: läuft", wait(lambda: f"Läuft in Spotify: {song.display_name}" in status(w), 12))
    check("erneutes Abspielen: Warnung weg", not w.warning_revealer.get_reveal_child())

    w.playback_check_ms = 1000
    w._draw_next()
    check("Warnung zum nächsten Song", wait(lambda: w.warning_revealer.get_reveal_child(), 6))
    w._generate(None)
    pump(6.0)  # länger als der verzögerte Start
    check("neue Karten: keine „Läuft jetzt“-Meldung zur alten Runde", "Läuft jetzt" not in status(w))


def scenario_test_cancelled(w):
    """„Spotify testen“ während des Spotify-Starts abbrechen und neu starten: nur ein Test läuft."""
    from musik_bingo.infrastructure import spotify
    from musik_bingo.presentation import dialogs

    shown = []
    dialogs.message = lambda parent, kind, title, detail: shown.append((title, detail))
    setup_round(w)
    w._draw_next()
    launches = []

    def launch():
        launches.append(1)
        start_fake("spotify", delay=2.0, wait_ready=False)
        return True
    spotify.launch_desktop_app = launch
    w._spotify_test(None)
    check("Test wartet auf Spotify", w.spotify_test_running and launches == [1])
    w._draw_next()  # neuer Song bricht den Test ab
    check("Test abgebrochen", not w.spotify_test_running)
    w._spotify_test(None)
    check("neuer Test wartet auf denselben Start", w.spotify_test_running and launches == [1])
    check("Dialog kommt", wait(lambda: shown, 20))
    pump(4.0)  # ein verwaister zweiter Test würde jetzt noch OpenUri/Pause senden
    check("genau ein Dialog", len(shown) == 1)
    check("genau ein OpenUri", calls("OpenUri") == 1)
    check("genau ein Pause", calls("Pause") == 1)


def scenario_pause_control(w):
    """Kontrolle wartet noch (Titel gleich pausiert geladen → würde „Play“ senden), Spielzeit läuft ab."""
    start_fake("spotify-pausiert-spaet", kind_seconds=3.0)
    setup_round(w)
    w.playback_check_ms = 8000  # Kontrolle wartet sicher noch, wenn der Titel pausiert ankommt
    w.auto_play_check.set_active(True)
    w.timer_spin.set_value(2)
    w.reveal_spin.set_value(15)  # kein automatisches Weiterziehen während der Prüfung
    w._draw_next()
    song = w.service.game.caller.current
    check("Spielzeit abgelaufen, Spotify pausiert", wait(lambda: w.timer.phase == "auflösung", 5)
          and wait(lambda: calls("Pause") == 1, 2))
    # Der simulierte Player hängt den unbekannten Titel hinten an (5 bekannte Einträge → Position 5).
    check("Titel kommt danach pausiert an", wait(lambda: calls("OpenUri", uri_of(song)) == 1
                                                  and state()["pos"] == 5 and state()["status"] == "Paused", 4))
    pump(2.5)
    check("nach der Pause kein Play mehr", calls("Play") == 0 and state()["status"] == "Paused")


SCENARIOS = {"wiederholt": scenario_retry, "pausiert": scenario_paused, "ignoriert": scenario_ignored, "start": scenario_start,
             "test": scenario_test, "pause": scenario_pause, "haengt": scenario_hung, "spaet": scenario_late,
             "testabbruch": scenario_test_cancelled, "pause_kontrolle": scenario_pause_control}

forbid_network()
patch_dialogs()
try:
    run(SCENARIOS[MODE])
finally:
    for process in PROCESSES:
        if process.poll() is None:
            process.kill()
