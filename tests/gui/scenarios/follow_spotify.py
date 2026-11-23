"""E2E: Spotify-Anbindung gegen einen simulierten Spotify-Prozess (privater D-Bus)."""
import json
import subprocess
import sys

from common import (MESSAGES, ROOT, TMP, check, forbid_network, patch_dialogs, pump, run, wait)

from gi.repository import Gtk

LOG = TMP / "fake.json"
FAKE = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "fake_player_process.py"), str(LOG), "spotify"],
                        stdout=subprocess.PIPE, text=True)
assert FAKE.stdout.readline().strip() == "ready"
forbid_network()
patch_dialogs()


def state():
    try:
        return json.loads(LOG.read_text())
    except (OSError, ValueError):
        return {"calls": [], "pos": -1}


def scenario(w):
    from musik_bingo.domain.models import Song
    from musik_bingo.presentation import gtk_app

    w.song_buffer.set_text("Last Christmas – Wham!\nAll I Want for Christmas Is You – Mariah Carey\n"
                           "Driving Home for Christmas – Chris Rea\n"
                           + "\n".join(f"Song {i} – Artist {i}" for i in range(10)))
    w.size_combo.set_active(0)
    w.free_check.set_active(False)
    w.count_spin.set_value(5)
    w._generate(None)
    check("Karten erzeugt", len(w.service.game.cards) == 5)

    w.follow_switch.set_active(True)
    check("Folgen stellt Ziel auf Spotify", w.service.playback_target == "spotify")
    check("mit Spotify verbunden", w.player is not None and w.player.info.is_spotify)
    drawn = lambda: [s.artist for s in w.service.game.caller.drawn]  # noqa: E731
    check("laufender Titel automatisch gezogen", wait(lambda: drawn() == ["Wham!"]))
    check("Spotify-Track-ID erkannt", w.now_playing and w.now_playing.url == "spotify:track:4uLU6hMCjMI75M1A2tKUQC")

    w._undo()
    pump(2.5)  # länger als das Abfrageintervall
    check("Zurück bleibt im Folgen-Modus bestehen", drawn() == [])

    w._read_from_player(None)
    check("Einlesen im Folgen-Modus gesperrt", "Erst „Player folgen“ ausschalten" in MESSAGES)

    w._draw_next()
    check("Werbung wird ignoriert", wait(lambda: state()["pos"] == 1) and wait(lambda: w.now_playing is None)
          and drawn() == [])
    w._draw_next()
    check("nächster Titel gezogen", wait(lambda: drawn() == ["Mariah Carey"]))
    w._draw_next()
    w._draw_next()
    check("fremder Titel → Warnung", wait(lambda: w.warning_revealer.get_reveal_child())
          and "Highway to Hell" in w.warning_label.get_text())
    check("fremder Titel nicht gezogen", drawn() == ["Mariah Carey", "Chris Rea"])
    # Regression: Die Warnung lag unter Anzeige und Prognose – auf einem 1366×768-Laptop unter dem sichtbaren
    # Bereich, „Überspringen“ war nur nach Scrollen zu erreichen. Jetzt direkt unter den Knöpfen.
    w._select_page("game")
    w.resize(1320, 662)  # mit Kopfleiste 728 px: Bildschirm minus 40-px-Leiste
    pump(1.0)
    scroller = w.warning_revealer.get_ancestor(Gtk.ScrolledWindow)
    _x, top = w.warning_revealer.translate_coordinates(scroller, 0, 0)
    bottom, visible = top + w.warning_revealer.get_allocated_height(), scroller.get_allocated_height()
    check(f"Warnung mit „Überspringen“ ist auf 1366×768 ohne Scrollen zu sehen (y {top}…{bottom} von {visible} px)",
          bottom - top > 40 and top >= 0 and bottom <= visible and w.warning_skip_button.get_visible())
    w._skip_unmatched(None)
    check("Überspringen blendet Warnung aus", wait(lambda: not w.warning_revealer.get_reveal_child()))
    check("Wiederholung zieht Wham neu (war zurückgenommen)", wait(lambda: drawn() == ["Mariah Carey", "Chris Rea", "Wham!"]))

    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Folgen-Einstellung gespeichert", saved["settings"]["follow_player"] is True)

    w.follow_switch.set_active(False)
    check("Folgen aus trennt Player", w.player is None)
    opened = []
    gtk_app.open_uri = opened.append
    w.service.game.caller.draw_next()
    w._render_caller()
    w._play_audio(None)
    check("ohne Link: Spotify-Suche geöffnet", opened and ":search" in opened[0] or "/search/" in opened[0])

    calls_before = len(state()["calls"])
    caller = w.service.game.caller
    caller.order[caller.index] = Song("Last Christmas", "Wham!", "spotify:track:4uLU6hMCjMI75M1A2tKUQC")
    w._play_audio(None)
    check("mit Link: Spotify spielt Titel direkt (OpenUri)",
          wait(lambda: any(call[0] == "OpenUri" for call in state()["calls"][calls_before:])))

    w.target_buttons["youtube"].set_active(True)
    check("Zielwechsel trennt unpassenden Player", w.player is None)
    w.target_buttons["spotify"].set_active(True)

    w.follow_switch.set_active(True)
    check("erneut verbunden", w.player is not None)
    FAKE.terminate()
    FAKE.wait()
    check("Spotify beendet → Folgen aus, kein Absturz", wait(lambda: not w.follow_switch.get_active() and w.player is None, 6))
    w.follow_switch.set_active(True)
    check("ohne Player: sauberer Hinweis", not w.follow_switch.get_active() and "Kein passender Player gefunden" in MESSAGES)


try:
    run(scenario)
finally:
    if FAKE.poll() is None:
        FAKE.terminate()
