"""E2E: Abend nur mit „Volle Karte“ über mehrere Runden mit denselben Karten (3×3), auch im Folgen-Modus.

Regressionen aus der Abendprüfung 11/2026:
- Jede neue Runde begann wieder mit „1 Reihe“ – der Beamer zeigte den Gästen das falsche Ziel.
- Folgen-Modus mit Song-Timer: Nach eingetragenem Gewinner lief der Timer von selbst wieder an, sobald
  Spotify zum nächsten Titel wechselte (alle paar Sekunden „Weiter“ während der Ehrung).
- „Neue Runde“ im Folgen-Modus zählt den laufenden Titel sofort als ersten Song – ohne Hinweis in der Rückfrage.
"""
import json
import subprocess
import sys

from common import MESSAGES, ROOT, TMP, check, forbid_network, pump, run, wait

LOG = TMP / "fake.json"
FAKE = subprocess.Popen([sys.executable, str(ROOT / "tests" / "support" / "fake_player_process.py"), str(LOG), "spotify"],
                        stdout=subprocess.PIPE, text=True)
assert FAKE.stdout.readline().strip() == "ready"
forbid_network()
CONFIRMS: list[tuple[str, str]] = []


def scenario(w):
    from musik_bingo.presentation import dialogs

    dialogs.confirm = lambda parent, title, detail="", ok_label="": CONFIRMS.append((title, detail)) or True
    dialogs.message = lambda parent, kind, title, detail: MESSAGES.append(title)
    w.song_buffer.set_text("Last Christmas – Wham!\nAll I Want for Christmas Is You – Mariah Carey\n"
                           "Driving Home for Christmas – Chris Rea\n"
                           + "\n".join(f"Song {i} – Artist {i}" for i in range(12)))
    w.size_combo.set_active(0)  # 3×3 mit Freifeld: 8 Songs je Karte
    w.count_spin.set_value(20)
    w._generate(None)
    game = w.service.game
    w._select_page("game")
    w.win_buttons["volle_karte"].set_active(True)  # vor dem ersten Song: gilt für den ganzen Abend
    w.beamer_button.set_active(True)
    pump(0.4)
    check("Stufen-Knopf bietet direkt die neue Runde an", w.stage_button.get_label() == "Neue Runde (neu mischen)")

    def full_card_wins(number: int, name: str) -> None:
        for song in game.cards[number - 1].songs:
            w.service.draw_song(song)
        w._render_caller()
        dialogs.bingo_check_dialog = lambda parent, count, rule: (number, name)
        dialogs.bingo_result_dialog = lambda *args, **kwargs: True  # „Als Gewinner eintragen“
        w._verify_bingo(None)

    # --- Runde 1 ohne Player: Gewinner, dann neue Runde
    w._draw_next()
    full_card_wins(1, "Erika")
    check("Runde 1: Gewinner für „Volle Karte“ eingetragen",
          [(x.round, x.target, x.card) for x in w.service.winners] == [(1, "volle_karte", 1)])
    w._advance_stage()
    title, detail = CONFIRMS[-1]
    check("Rückfrage nennt das Ziel der neuen Runde", title == "Runde 2 starten?" and "„Volle Karte“" in detail
          and "1 Reihe" not in detail)
    check("Runde 2 beginnt wieder mit „Volle Karte“", (w.service.round_number, w.service.win_target) == (2, "volle_karte")
          and w.win_buttons["volle_karte"].get_active() and not game.caller.drawn)
    check("Beamer zeigt Runde 2 mit „Volle Karte“", w.beamer.round_label.get_text() == "Runde 2 · Ziel: Volle Karte")
    check("Kopfzeile und Statuszeile nennen „Volle Karte“", "Ziel: Volle Karte" in w.rule_pill.get_text()
          and w.status.get_text() == "Runde 2 · Ziel: Volle Karte")
    w._draw_next()
    w._reshuffle(None)  # „Neu mischen“ mitten in der Runde = Runde 3
    check("Neu mischen: Rückfrage und neue Runde nennen „Volle Karte“", "mit „Volle Karte“" in CONFIRMS[-1][1]
          and (w.service.round_number, w.service.win_target) == (3, "volle_karte"))

    # --- Runde 3 im Folgen-Modus mit Song-Timer
    w.timer_spin.set_value(30)
    w.follow_switch.set_active(True)
    drawn = lambda: [s.artist for s in game.caller.drawn]  # noqa: E731
    check("Folgen: laufender Titel gezogen, Timer läuft", wait(lambda: drawn() == ["Wham!"]) and w.timer.phase == "läuft")
    full_card_wins(1, "Erika")
    check("Gewinner Runde 3 eingetragen (Karte hatte schon gewonnen: nach Rückfrage)",
          [(x.round, x.card) for x in w.service.winners] == [(1, 1), (3, 1)] and CONFIRMS[-1][0] == "Karte hat schon gewonnen")
    check("Nach dem Eintragen steht der Timer", w.timer.phase == "aus")
    # Spotify schaltet von selbst weiter (Titel zu Ende) – die Spielleitung ist bei der Ehrung
    w.player.next()
    w.player.next()  # Werbung überspringen → „All I Want for Christmas Is You“
    check("Spotify ist beim nächsten Titel angekommen",
          wait(lambda: w.now_playing is not None and w.now_playing.artist == "Mariah Carey"))
    check("Der neue Titel zählt (gezogen)", "Mariah Carey" in drawn())
    pump(1.5)
    check("Timer bleibt nach dem Gewinner aus, bis die Spielleitung weitermacht", w.timer.phase == "aus")
    w._draw_next()  # Spielleitung: Leertaste = nächster Titel im Player
    check("Spielleitung macht weiter: Titel läuft, Timer startet wieder",
          wait(lambda: w.now_playing is not None and w.now_playing.artist == "Chris Rea") and w.timer.phase == "läuft")
    CONFIRMS.clear()
    w._advance_stage()
    check("Neue Runde im Folgen-Modus: Rückfrage warnt, dass der laufende Titel sofort zählt",
          len(CONFIRMS) == 1 and "zählt sofort" in CONFIRMS[0][1] and "pausieren" in CONFIRMS[0][1])
    check("Runde 4 wieder mit „Volle Karte“", (w.service.round_number, w.service.win_target) == (4, "volle_karte"))

    w._save_settings()
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Startziel gespeichert", saved["settings"]["round_start_target"] == "volle_karte"
          and saved["settings"]["round_number"] == 4)
    w.follow_switch.set_active(False)
    w.beamer_button.set_active(False)
    check("Keine Fehlermeldungen", MESSAGES == [])


try:
    run(scenario)
finally:
    if FAKE.poll() is None:
        FAKE.terminate()
