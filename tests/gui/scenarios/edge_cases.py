"""E2E-Grenzfälle. Aufruf mit Modus: broken | deep | empty | big"""
import json
import sys
import time

from common import MESSAGES, TMP, check, forbid_network, patch_dialogs, run

MODE = sys.argv[1]
SAVE = TMP / "data" / "musik-bingo" / "spielstand.json"
SAVE.parent.mkdir(parents=True)
if MODE == "broken":
    SAVE.write_text('{"version": 1, "songs": "kaputt"}')
elif MODE == "deep":
    SAVE.write_text("[" * 100_000 + "]" * 100_000)
forbid_network()
patch_dialogs()


def scenario(w):
    if MODE in ("broken", "deep"):
        check(f"{MODE}: Warnung statt Absturz", "Spielstand konnte nicht geladen werden" in MESSAGES)
        check(f"{MODE}: App startet mit leerer Runde", not w.service.game.cards)
        w._generate(None)
        check(f"{MODE}: danach normal spielbar", len(w.service.game.cards) == 30)
    elif MODE == "empty":
        w.song_buffer.set_text("")
        w._generate(None)
        check("leere Liste → Hinweis", "Karten konnten nicht erzeugt werden" in MESSAGES)
        w._select_page("game")
        for action in (w._draw_next, w._undo, lambda: w._play_audio(None), lambda: w._pause_audio(None),
                       lambda: w._stop_audio(None), lambda: w._verify_bingo(None)):
            action()
        check("Spielleitung ohne Runde stabil", w.service.game.caller.index == -1)
        w.follow_switch.set_active(True)
        check("Folgen ohne Karten verweigert", not w.follow_switch.get_active())
        w.song_buffer.set_text("\n".join(f"S{i}" for i in range(9)))
        w.size_combo.set_active(0)
        w.free_check.set_active(False)
        w.count_spin.set_value(2)
        w._generate(None)
        check("zu wenige Kombinationen → Hinweis", MESSAGES.count("Karten konnten nicht erzeugt werden") == 2)
    elif MODE == "big":
        w.song_buffer.set_text("\n".join(f"Titel {i} – Interpret {i}" for i in range(2000)))
        w.count_spin.set_value(500)
        start = time.perf_counter()
        w._generate(None)
        check("500 Karten aus 2000 Songs in < 10 s", len(w.service.game.cards) == 500 and time.perf_counter() - start < 10)
        start = time.perf_counter()
        for _ in range(20):
            w._draw_next()
        check("20 Ziehungen bei 2000er Pool in < 10 s", len(w.service.game.caller.drawn) == 20
              and time.perf_counter() - start < 10)
        w._save()
        check("großer Spielstand gespeichert", len(json.loads(SAVE.read_text())["cards"]) == 500)


run(scenario)
