"""E2E: Spotify lehnt OpenUri ab und es gibt keinen spotify:-Handler → Titel im Webplayer öffnen."""
import subprocess
import sys

from common import ROOT, TMP, check, forbid_network, patch_dialogs, run, wait

FAKE = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "fake_player_process.py"),
                         str(TMP / "fake.json"), "spotify-ohne-openuri"], stdout=subprocess.PIPE, text=True)
assert FAKE.stdout.readline().strip() == "ready"
forbid_network()
patch_dialogs()


def scenario(w):
    from musik_bingo.domain.models import Song
    from musik_bingo.presentation import gtk_app

    w.song_buffer.set_text("\n".join(f"Song {i} – Artist {i}" for i in range(12)))
    w.size_combo.set_active(0)
    w.count_spin.set_value(3)
    w._generate(None)
    w.target_buttons["spotify"].set_active(True)
    w.spotify_scheme = False  # kein spotify:-Handler installiert
    opened = []
    gtk_app.open_uri = opened.append
    caller = w.service.game.caller
    caller.draw_next()
    caller.order[caller.index] = Song("Last Christmas", "Wham!", "spotify:track:4uLU6hMCjMI75M1A2tKUQC")
    w._render_caller()
    w._play_audio(None)
    check("mit Spotify verbunden", w.player is not None and w.player.info.is_spotify)
    # Regression (Fable 2.4): Rückfall öffnete wieder spotify:track:… statt des Webplayers
    check("Rückfall öffnet den Webplayer",
          wait(lambda: opened == ["https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"]))

    # Regression (Fable, 2. Prüfung): gescheitertes Einschalten von „Player folgen“ stoppte einen
    # normal laufenden Song-Timer
    w.target_buttons["youtube"].set_active(True)  # kein Browser-Player auf dem Bus
    w.timer_spin.set_value(30)
    w._new_song_started()
    w.follow_switch.set_active(True)
    check("Folgen ohne passenden Player bleibt aus", not w.follow_switch.get_active())
    check("Timer läuft weiter", w.timer.phase != "aus")


try:
    run(scenario)
finally:
    if FAKE.poll() is None:
        FAKE.terminate()
