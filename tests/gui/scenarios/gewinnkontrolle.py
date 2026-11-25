"""E2E: Gewinnkontrolle – die Spielleitung sieht nach jedem Song, welche Karten das Gewinnziel erreicht haben.

Ablauf wie am Abend mit 3×3-Karten und nur „Volle Karte“: Songs ziehen, Hinweis „fehlt nur noch ein Song“,
Karte voll → Knopf „Karte #n prüfen“ öffnet die Bingo-Prüfung, Eintragen, Löschen, Gleichstand.
Der Beamer zeigt davon nichts.
"""
import os
from pathlib import Path

from common import MESSAGES, TMP, check, forbid_network, pump, run, screenshot

forbid_network()


def buttons(w) -> list[str]:
    return [child.get_child().get_label() for child in w.target_cards.get_children()
            if hasattr(child.get_child(), "get_label")]


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
    w.beamer_button.set_active(True)
    pump(0.3)
    check("Vor dem ersten Song: Hinweis statt Karten", "Noch kein Song gezogen" in w.target_status_label.get_text()
          and buttons(w) == [])

    first, second = game.cards[0], game.cards[1]
    for song in first.songs[:-1]:
        w.service.draw_song(song)
    w._render_caller()
    text = w.target_status_label.get_text()
    check("Karte #1 fehlt ein Song: Hinweis, aber noch kein Prüfknopf",
          "fehlt nur noch ein Song" in text and "Karte #1 prüfen" not in buttons(w))

    w.service.draw_song(first.songs[-1])
    w._render_caller()
    reached = w.service.target_status().reached
    check("Karte #1 voll: Prüfknopf erscheint", 1 in reached and "Karte #1 prüfen" in buttons(w))
    check("Anzeige stimmt mit der Einzelprüfung aller Karten überein",
          list(reached) == [n for n in range(1, len(game.cards) + 1) if w.service.check_win(n)[0]])
    check("Beamer verrät keine Kartennummern", "#1" not in w.beamer.round_label.get_text())
    target = os.environ.get("SCREENSHOT_DIR")
    screenshot(w, (Path(target) if target else TMP) / "gewinnkontrolle.png")

    opened = []

    def result_dialog(parent, card, number, *args, **kwargs):
        opened.append(number)
        return True  # „Als Gewinner eintragen“
    dialogs.bingo_result_dialog = result_dialog
    button = next(child.get_child() for child in w.target_cards.get_children()
                  if child.get_child().get_label() == "Karte #1 prüfen")
    button.clicked()
    pump(0.2)
    check("Klick öffnet die Bingo-Prüfung für Karte #1", opened == [1])
    check("Karte #1 ist eingetragen und kein Prüfknopf mehr",
          [(x.card, x.target) for x in w.service.winners] == [(1, "volle_karte")]
          and "Karte #1 prüfen" not in buttons(w) and "eingetragen: #1" in w.target_status_label.get_text())
    check("Timer bleibt nach dem Eintragen aus", w.timer.phase == "aus")

    w._remove_winner(None, 0)
    check("Eintrag gelöscht: Prüfknopf ist wieder da", "Karte #1 prüfen" in buttons(w))

    for song in second.songs:
        w.service.draw_song(song)
    w._render_caller()
    status = w.service.target_status()
    check("Mehrere volle Karten: Gleichstand wird angezeigt",
          len(status.reached) >= 2 and "Gleichstand" in w.target_status_label.get_text()
          and "Karte #2 prüfen" in buttons(w))

    w.win_buttons["reihe"].set_active(True)
    check("Zielwechsel: Anzeige folgt dem neuen Ziel", "Ziel: 1 Reihe" in w.target_status_label.get_text())
    w.beamer_button.set_active(False)
    check("Keine Fehlermeldungen", MESSAGES == [])


run(scenario)
