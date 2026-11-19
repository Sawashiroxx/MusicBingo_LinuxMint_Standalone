"""E2E: YouTube-Music-Anbindung gegen eine simulierte YouTube-Music-App (privater D-Bus)."""
import json
import subprocess
import sys

from common import (MESSAGES, ROOT, TMP, check, forbid_network, patch_dialogs, run, wait)

LOG = TMP / "fake.json"
FAKE = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "fake_player_process.py"), str(LOG),
                         "ytmusic"], stdout=subprocess.PIPE, text=True)
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
                           + "\n".join(f"Song {i} – Artist {i}" for i in range(10)))
    w.size_combo.set_active(0)
    w.free_check.set_active(False)
    w.count_spin.set_value(5)
    w._generate(None)
    check("Karten erzeugt", len(w.service.game.cards) == 5)

    w.target_buttons["ytmusic"].set_active(True)
    check("Ziel YouTube Music gesetzt", w.service.playback_target == "ytmusic")
    w.follow_switch.set_active(True)
    check("Folgen behält YouTube Music", w.service.playback_target == "ytmusic")
    check("mit YouTube-Music-App verbunden", w.player is not None and w.player.info.is_youtube_music_app)
    drawn = lambda: [s.artist for s in w.service.game.caller.drawn]  # noqa: E731
    check("laufender Titel automatisch gezogen", wait(lambda: drawn() == ["Wham!"]))
    check("Video-Link aus YouTube Music erkannt",
          w.now_playing and w.now_playing.url == "https://www.youtube.com/watch?v=E8gmARGvPlI")
    check("Quelle zeigt den Player", "YouTube Music" in w.audio_status.get_text())

    w._draw_next()
    check("Weiter → nächster Titel in der App", wait(lambda: drawn() == ["Wham!", "Mariah Carey"]))
    check("Next an die App gesendet", any(call[0] == "Next" for call in state()["calls"]))
    w._draw_next()
    check("fremder Titel → Warnung", wait(lambda: w.warning_revealer.get_reveal_child())
          and "Highway to Hell" in w.warning_label.get_text())
    w._skip_unmatched(None)
    check("Überspringen blendet Warnung aus", wait(lambda: not w.warning_revealer.get_reveal_child()))

    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Ziel YouTube Music gespeichert", saved["settings"]["playback_target"] == "ytmusic")

    w.follow_switch.set_active(False)
    check("Folgen aus trennt Player", w.player is None)
    opened = []
    gtk_app.open_uri = opened.append
    caller = w.service.game.caller
    if caller.current is None:
        caller.draw_next()
    caller.order[caller.index] = Song("Last Christmas", "Wham!", "https://youtu.be/E8gmARGvPlI")
    w._render_caller()
    w._play_audio(None)
    check("mit Link: exakter Titel in YouTube Music",
          opened == ["https://music.youtube.com/watch?v=E8gmARGvPlI"])
    caller.order[caller.index] = Song("Feliz Navidad", "José Feliciano")
    w._play_audio(None)
    check("ohne Link: YouTube-Music-Suche",
          opened[-1] == "https://music.youtube.com/search?q=Jos%C3%A9%20Feliciano%20Feliz%20Navidad")

    w.target_buttons["spotify"].set_active(True)
    w.target_buttons["ytmusic"].set_active(True)
    w.follow_switch.set_active(True)
    check("erneut verbunden", w.player is not None)
    FAKE.terminate()
    FAKE.wait()
    check("App beendet → Folgen aus, kein Absturz",
          wait(lambda: not w.follow_switch.get_active() and w.player is None, 6))
    w.follow_switch.set_active(True)
    check("ohne Player: sauberer Hinweis",
          not w.follow_switch.get_active() and "Kein passender Player gefunden" in MESSAGES)


try:
    run(scenario)
finally:
    if FAKE.poll() is None:
        FAKE.terminate()
