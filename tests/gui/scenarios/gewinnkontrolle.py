"""E2E: Gewinnkontrolle – die Spielleitung sieht nach jedem Song, welche Karten das Gewinnziel erreicht haben.

Ablauf wie am Abend mit 3×3-Karten und nur „Volle Karte“: Songs ziehen, Hinweis „fehlt nur noch ein Song“,
Karte voll → Hinweiszeile direkt unter den Knöpfen und Prüfknopf im Panel. Der Knopf öffnet „Bingo prüfen“
mit vorbelegter Nummer (Name kann dazu), der Song-Timer steht währenddessen. Übersehener früherer Gewinn
steht vorn; „Gleichstand“ nur bei gleichem Song. Der Beamer zeigt davon nichts.
"""
import os
from pathlib import Path

from common import MESSAGES, TMP, check, forbid_network, pump, run, screenshot

forbid_network()


def panel_buttons(w) -> list:
    return [child.get_child() for child in w.target_cards.get_children()
            if hasattr(child.get_child(), "card_number")]


def scenario(w):
    from musik_bingo.presentation import dialogs

    dialogs.confirm = lambda *args, **kwargs: True
    dialogs.message = lambda parent, kind, title, detail: MESSAGES.append(title)
    w.song_buffer.set_text("\n".join(f"Song {i} – Artist {i}" for i in range(20)))
    w.size_combo.set_active(0)  # 3×3 mit Freifeld: 8 Songs je Karte
    w.count_spin.set_value(30)
    w._generate(None)
    game = w.service.game
    w._select_page("game")
    w.win_buttons["volle_karte"].set_active(True)
    w.timer_spin.set_value(30)
    w.beamer_button.set_active(True)
    pump(0.3)
    check("Vor dem ersten Song: Hinweis statt Karten", "Noch kein Song gezogen" in w.target_status_label.get_text()
          and panel_buttons(w) == [] and not w.target_hint.get_reveal_child())

    first = game.cards[0]
    w._draw_next()  # Timer läuft
    for song in first.songs[:-1]:
        w.service.draw_song(song)
    w._render_caller()
    status = w.service.target_status()
    check("Karte #1 fehlt ein Song: Hinweis mit exakter Zahl, aber kein Prüfknopf",
          f"{status.one_missing} Karte" in w.target_status_label.get_text()
          and 1 not in [b.card_number for b in panel_buttons(w)])

    w.service.draw_song(first.songs[-1])
    w._render_caller()
    pump(0.6)  # Revealer-Animation
    status = w.service.target_status()
    song_no = dict(status.reached)[1]
    check("Karte #1 voll: Prüfknopf mit Song-Nr.",
          any(b.card_number == 1 and f"seit Song {song_no}" in b.get_label() for b in panel_buttons(w)))
    check("Anzeige stimmt mit der Einzelprüfung aller Karten überein",
          sorted(n for n, _s in status.reached)
          == [n for n in range(1, len(game.cards) + 1) if w.service.check_win(n)[0]])
    hint_y = w.target_hint.translate_coordinates(w, 0, 0)[1]
    panel_y = w.target_status_label.translate_coordinates(w, 0, 0)[1]
    check("Hinweiszeile direkt unter den Knöpfen (auf 1366×768 ohne Scrollen sichtbar)",
          w.target_hint.get_reveal_child() and 0 < hint_y < 600 and hint_y < panel_y
          and w.target_hint_button.card_number == status.reached[0][0])
    check("Beamer verrät keine Kartennummern", "#1" not in w.beamer.round_label.get_text()
          and "#1" not in w.beamer.song_label.get_text())

    # Prüfknopf: erst abbrechen (Timer muss danach weiterlaufen), dann mit Namen eintragen
    calls = []

    def check_dialog(parent, count, rule, preset=None):
        calls.append((preset, w.timer.paused))
        return None if len(calls) == 1 else (preset, "Anna")
    dialogs.bingo_check_dialog = check_dialog
    dialogs.bingo_result_dialog = lambda *args, **kwargs: True  # „Als Gewinner eintragen“
    w.target_hint_button.clicked()
    check("Prüfknopf öffnet „Bingo prüfen“ mit vorbelegter Nummer, Timer steht und läuft danach weiter",
          calls == [(1, True)] and w.timer.phase == "läuft" and not w.timer.paused)
    next(b for b in panel_buttons(w) if b.card_number == 1).clicked()
    pump(0.2)
    check("Eintragen mit Namen", [(x.card, x.target, x.name) for x in w.service.winners] == [(1, "volle_karte", "Anna")]
          and w.banner == "BINGO! Karte #1 · Anna")
    check("Nach dem Eintragen: kein Prüfknopf mehr, Timer aus, Hinweiszeile zeigt nicht mehr #1",
          1 not in [b.card_number for b in panel_buttons(w)] and "eingetragen: #1" in w.target_status_label.get_text()
          and w.timer.phase == "aus" and w.timer_hold and w.target_hint_button.card_number != 1)

    w._undo()
    check("„Zurück“: eingetragene Karte als nicht mehr am Ziel markiert",
          "nicht mehr am Ziel: #1" in w.target_status_label.get_text())
    if not game.caller.is_drawn(first.songs[-1]):
        w.service.draw_song(first.songs[-1])
        w._render_caller()

    w._remove_winner(None, 0)
    check("Eintrag gelöscht: Prüfknopf ist wieder da", 1 in [b.card_number for b in panel_buttons(w)])

    second = next(card for number, card in enumerate(game.cards, start=1) if not w.service.check_win(number)[0])
    for song in second.songs:
        w.service.draw_song(song)
    w._render_caller()
    status = w.service.target_status()
    check("Später volle Karte: kein Gleichstand, früheste Karte steht vorn",
          len(status.reached) >= 2 and status.reached[0][0] == 1
          and "Gleichstand" not in w.target_status_label.get_text()
          and "Gleichstand" not in w.target_hint_label.get_text())

    w.beamer_button.set_active(False)
    pump(0.3)
    target = os.environ.get("SCREENSHOT_DIR")
    screenshot(w, (Path(target) if target else TMP) / "gewinnkontrolle.png")
    w.win_buttons["reihe"].set_active(True)
    check("Zielwechsel: Anzeige folgt dem neuen Ziel", "Ziel: 1 Reihe" in w.target_status_label.get_text())
    check("Keine Fehlermeldungen", MESSAGES == [])


run(scenario)
