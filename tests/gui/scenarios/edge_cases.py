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
ORIGINAL = SAVE.read_bytes() if SAVE.exists() else b""
forbid_network()
patch_dialogs()


def scenario(w):
    if MODE in ("broken", "deep"):
        check(f"{MODE}: Warnung statt Absturz", "Spielstand konnte nicht geladen werden" in MESSAGES)
        check(f"{MODE}: App startet mit leerer Runde", not w.service.game.cards)
        # Regression (Fable 2.4): unlesbare Datei wurde beim Schließen/ersten Klick ohne Kopie überschrieben
        kept = sorted((SAVE.parent / "sicherungen").glob("unlesbar_*.json"))
        check(f"{MODE}: unveränderte Kopie der unlesbaren Datei", len(kept) == 1
              and kept[0].read_bytes() == ORIGINAL)
        w._generate(None)
        check(f"{MODE}: danach normal spielbar", len(w.service.game.cards) == 160)
    elif MODE == "defaults":
        from musik_bingo.domain.song_list import parse_songs
        check("Startliste: 75 Songs", len(parse_songs(w._song_text())) == 75)
        check("Standard: 160 Karten für ~140 Gäste", w.count_spin.get_value_as_int() == 160)
        w._generate(None)
        forecast = w.service.forecast(runs=200)
        check("Prognose 1 Reihe ≈ 12–22 Songs", 12 <= forecast.stages["reihe"].median <= 22)
        check("Prognose Volle Karte ≈ 58–68 Songs", 58 <= forecast.stages["volle_karte"].median <= 68)
        check("Garantie mit Standardwerten", w.service.guarantee().ok)
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
