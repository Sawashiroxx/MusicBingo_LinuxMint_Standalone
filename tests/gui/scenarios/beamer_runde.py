"""E2E: „Runde auf dem Beamer zeigen“ an/aus.

Aus: Oben auf dem Beamer steht nur das Gewinnziel („Ziel: Volle Karte“), keine Rundennummer – etwa wenn beim
Ausprobieren schon „Runde 10“ erreicht ist. Die Spielleitung sieht die Runde weiter. Gespeichert im Spielstand.
Läuft auf 1366×768: Der neue Schalter darf das Fenster nicht breiter als den Laptop-Bildschirm machen.
"""
import json

from common import MESSAGES, TMP, check, forbid_network, pump, run

forbid_network()


def scenario(w):
    from musik_bingo.application.game_service import GameService
    from musik_bingo.presentation import dialogs

    dialogs.confirm = lambda *args, **kwargs: True
    dialogs.message = lambda parent, kind, title, detail: MESSAGES.append(title)
    w.song_buffer.set_text("\n".join(f"Song {i} – Artist {i}" for i in range(20)))
    w.size_combo.set_active(0)
    w.count_spin.set_value(20)
    w._generate(None)
    w._select_page("game")
    w.beamer_button.set_active(True)
    pump(0.3)

    # Regression: In der Zeile neben „Titel auf dem Beamer aufdecken“ machte der Schalter das Fenster
    # mindestens 1466 px breit. Grenze wie in screenshots.py: 1320 px (Platz für Rahmen und Panel).
    w.resize(1, 1)
    pump(0.4)
    width, height = w.get_size()
    check(f"Spielleitung passt in die Breite von 1366 px ({width} ≤ 1320)", width <= 1320)
    w.resize(1320, 700)
    pump(0.3)
    check("Standard: Runde wird gezeigt", w.beamer_round_check.get_active() and w.service.beamer_round)
    check("Schalter ist sichtbar und bedienbar",
          w.beamer_round_check.get_mapped() and w.beamer_round_check.get_sensitive())
    allocation = w.beamer_round_check.get_allocation()
    origin = w.beamer_round_check.translate_coordinates(w, 0, 0)
    check("Schalter liegt waagrecht im Fenster",
          origin is not None and origin[0] >= 0 and origin[0] + allocation.width <= w.get_allocated_width())

    # Testrunden wie beim Ausprobieren: mehrfach „Neu mischen“ nach dem ersten Song
    for _ in range(9):
        w._draw_next()
        w._reshuffle(None)
    w._draw_next()
    pump(0.1)
    round_number = w.service.round_number
    check(f"Nach Testrunden: Runde {round_number} auf dem Beamer",
          round_number == 10 and w.beamer.round_label.get_text().startswith("Runde 10 · Ziel: "))

    w.beamer_round_check.set_active(False)
    pump(0.1)
    target_text = w.beamer.round_label.get_text()
    check("Aus: Beamer zeigt nur das Ziel", target_text.startswith("Ziel: ") and "Runde" not in target_text
          and "10" not in target_text)
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Aus: sofort gespeichert", saved["settings"]["beamer_round"] is False)
    check("Aus: Rundennummer bleibt im Spiel erhalten", w.service.round_number == 10)

    w.win_buttons["volle_karte"].set_active(True)
    pump(0.1)
    check("Aus: Zielwechsel kommt auf dem Beamer an", w.beamer.round_label.get_text() == "Ziel: Volle Karte")
    w._draw_next()
    w._reshuffle(None)  # neue Runde
    pump(0.1)
    check("Aus: auch nach neuer Runde keine Rundennummer",
          w.service.round_number == 11 and "Runde" not in w.beamer.round_label.get_text())

    w.beamer_round_check.set_active(True)
    pump(0.1)
    check("Wieder an: Runde erscheint sofort", w.beamer.round_label.get_text().startswith("Runde 11 · Ziel: "))

    # Speichern über _save_settings (nicht nur über den Schalter) und Laden in beide Richtungen
    w.beamer_round_check.set_active(False)
    w.service.beamer_round = True  # Schalter sagt „aus“ – _save_settings muss das übernehmen
    w._save_settings()
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("_save_settings übernimmt den Schalter", saved["settings"]["beamer_round"] is False)
    w.beamer_round_check.set_active(True)
    w._apply_service_to_widgets(GameService.from_dict(saved))
    pump(0.1)
    check("Laden „aus“ in ein Fenster mit Haken an: Haken aus, Beamer ohne Runde",
          not w.beamer_round_check.get_active() and not w.service.beamer_round
          and "Runde" not in w.beamer.round_label.get_text())
    saved["settings"]["beamer_round"] = True
    w._apply_service_to_widgets(GameService.from_dict(saved))
    pump(0.1)
    check("Laden „an“ in ein Fenster mit Haken aus: Haken an, Beamer mit Runde",
          w.beamer_round_check.get_active() and w.service.beamer_round
          and w.beamer.round_label.get_text().startswith("Runde "))
    del saved["settings"]["beamer_round"]
    w.beamer_round_check.set_active(False)
    w._apply_service_to_widgets(GameService.from_dict(saved))
    pump(0.1)
    check("Alter Spielstand ohne Einstellung: Haken an, Beamer mit Runde",
          w.beamer_round_check.get_active() and w.beamer.round_label.get_text().startswith("Runde "))
    w.beamer_button.set_active(False)
    check("Keine Fehlermeldungen", MESSAGES == [])


run(scenario)
