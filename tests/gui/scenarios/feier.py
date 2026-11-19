"""E2E: Funktionen für den Abend – Titel, Beamer, Timer, Gewinnerliste, Stufen/Runden."""
import json
import shutil
import subprocess
import time

from common import MESSAGES, TMP, Gdk, Gtk, check, forbid_network, patch_dialogs, pump, run, wait

forbid_network()
patch_dialogs()


def key(window, keyval):
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = keyval
    window.set_focus(None)
    return window._on_key(window, event)


def scenario(w):
    from musik_bingo.application.beamer_state import HIDDEN
    from musik_bingo.presentation import dialogs

    # Titel der Feier
    w.title_entry.set_text("  Weihnachtsfeier\t2026 <b>&</b> ")
    check("Titel bereinigt übernommen", w.service.event_title == "Weihnachtsfeier 2026 <b>&</b>")
    w.size_combo.set_active(2)
    w.count_spin.set_value(40)
    w._generate(None)
    heads = [child.get_child().get_children()[0].get_children()[0].get_text() for child in w.cards_flow.get_children()]
    check("Titel im Kartenkopf (wörtlich, nicht als Markup)", heads and heads[0] == "♪ WEIHNACHTSFEIER 2026 <B>&</B>")
    pdf = TMP / "karten.pdf"
    operation = Gtk.PrintOperation()
    operation.set_n_pages(1)
    operation.set_export_filename(str(pdf))
    operation.connect("draw-page", w._draw_print_page)
    operation.run(Gtk.PrintOperationAction.EXPORT, w)
    if shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
        check("Titel auf der gedruckten Karte", "WEIHNACHTSFEIER 2026" in text and "Gewinnziel sagt die Spielleitung an" in text)
    else:
        print("HINWEIS pdftotext fehlt – Drucktext nicht geprüft (in CI installiert)")

    # Beamer
    w._select_page("game")
    w.beamer_button.set_active(True)
    pump(0.5)
    check("Beamer-Fenster offen", w.beamer is not None and w.beamer.get_visible())
    w._draw_next()
    w._draw_next()
    state = w.beamer.state
    current = w.service.game.caller.current
    check("Beamer: Titel verdeckt", state.title == HIDDEN and current.display_name not in state.recent)
    check("Beamer: Titel/Runde/Song", state.event_title.startswith("Weihnachtsfeier") and state.song_line == "Song 2"
          and state.round_line == "Runde 1 · Ziel: 1 Reihe")
    key(w, Gdk.KEY_t)
    check("Taste T deckt Titel auf", w.revealed and w.beamer.state.title == current.title)
    w._draw_next()
    check("Neuer Song verdeckt den Titel wieder", not w.revealed and w.beamer.state.title == HIDDEN)

    # Timer: 2 s Spielzeit, 1 s Auflösung → automatisch weiter
    w.timer_spin.set_value(2)
    w.reveal_spin.set_value(1)
    w._draw_next()
    before = len(w.service.game.caller.drawn)
    check("Timer zeigt Countdown", w.timer_label.get_text().startswith("noch"))
    revealed_seen = wait(lambda: w.revealed, 4)
    check("Timer deckt am Ende auf", revealed_seen)
    check("Timer zieht automatisch den nächsten Song", wait(lambda: len(w.service.game.caller.drawn) == before + 1, 4))
    key(w, Gdk.KEY_p)
    paused_at = len(w.service.game.caller.drawn)
    pump(3.5)
    check("Taste P pausiert den Timer", w.timer.paused and len(w.service.game.caller.drawn) == paused_at)
    key(w, Gdk.KEY_p)
    # Offener Dialog: Timer darf nicht weiterziehen
    modal = Gtk.Dialog(title="Rückfrage", transient_for=w, modal=True)
    modal.show()
    w.timer.start()
    during = len(w.service.game.caller.drawn)
    pump(3.5)
    check("Offener Dialog hält den Timer an", len(w.service.game.caller.drawn) == during
          and w.timer.remaining == w.timer.seconds)
    modal.destroy()
    w.timer_spin.set_value(0)
    check("Timer aus", w.timer.phase == "aus")

    # Regression: Fokus/Leertaste – nach Mausklick behält kein Knopf den Fokus
    buttons = [w.draw_button, w.undo_button, w.verify_button, w.stage_button, w.reveal_button, w.beamer_button,
               w.shuffle_button, w.follow_switch]
    check("Spielleitung: Klick setzt keinen Tastaturfokus", all(not b.get_focus_on_click() for b in buttons))
    w.timer_spin.set_value(0)
    w._draw_next()
    w.reveal_button.grab_focus()
    w.set_focus_visible(False)  # wie nach einem Mausklick
    count = len(w.service.game.caller.drawn)
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = Gdk.KEY_space
    w._on_key(w, event)
    check("Leertaste zieht, auch wenn „Titel aufdecken“ zuletzt geklickt war",
          len(w.service.game.caller.drawn) == count + 1 and not w.revealed)
    w.draw_button.grab_focus()
    event.keyval = Gdk.KEY_t
    w._on_key(w, event)
    check("T deckt auf, auch wenn ein Knopf den Fokus hat", w.revealed)
    w.reveal_button.set_active(False)
    w.beamer._on_key(w.beamer, event)
    check("T im Beamer-Fenster wirkt auf die Spielleitung", w.revealed)
    w.set_focus(None)

    # Regression: manuelle Pause bleibt nach „Bingo prüfen“ (abgebrochen) bestehen
    w.timer_spin.set_value(30)
    w._draw_next()
    w._toggle_timer_pause()
    dialogs.bingo_check_dialog = lambda parent, count, rule: None
    w._verify_bingo(None)
    check("Pause bleibt nach abgebrochener Bingo-Prüfung", w.timer.paused)
    w._toggle_timer_pause()

    # Regression: Folgen-Modus + Timer – bereits gezogener Titel hält den Timer nicht an
    from musik_bingo.domain.matching import PlayingTrack
    w.timer.stop()
    w.follow_switch.handler_block_by_func(w._follow_toggled)
    w.follow_switch.set_active(True)
    drawn_song = w.service.game.caller.drawn[0]
    w._follow_track(PlayingTrack(drawn_song.title, drawn_song.artist))
    check("Folgen: bereits gezogener Titel → Timer zählt weiter", w.timer.phase == "läuft")
    w.timer.stop()
    w._follow_track(PlayingTrack("Highway to Hell", "AC/DC"))
    check("Folgen: fremder Titel → Timer zählt weiter", w.timer.phase == "läuft")
    w._hide_warning()
    w.follow_switch.set_active(False)
    w.follow_switch.handler_unblock_by_func(w._follow_toggled)
    w.timer_spin.set_value(0)

    # Regression: Titeländerung erneuert die Kartenvorschau
    w.title_entry.set_text("Feier B")
    first_head = w.cards_flow.get_children()[0].get_child().get_children()[0].get_children()[0].get_text()
    check("Kartenvorschau zeigt neuen Titel", first_head == "♪ FEIER B")
    w.title_entry.set_text("Weihnachtsfeier 2026 <b>&</b>")

    # Gewinner: Karte 1, Reihe 1 vollständig ziehen
    for song in w.service.game.cards[0].songs[:5]:
        w.service.draw_song(song)
    w._render_caller()
    dialogs.bingo_check_dialog = lambda parent, count, rule: (1, "<i>Oma</i> Erna")
    dialogs.bingo_result_dialog = lambda *args: True  # „Als Gewinner eintragen“
    w._verify_bingo(None)
    check("Gewinner eingetragen", len(w.service.winners) == 1 and w.service.winners[0].name == "<i>Oma</i> Erna")
    check("Beamer zeigt BINGO-Banner", w.beamer.state.banner == "BINGO! Karte #1 · <i>Oma</i> Erna")
    rows = w.winners_list.get_children()
    row_text = rows[0].get_child().get_children()[0].get_text() if rows else ""
    check("Gewinnerliste zeigt Namen wörtlich", "Karte #1 · <i>Oma</i> Erna" in row_text)
    w._verify_bingo(None)
    check("Gleiche Karte, gleiche Stufe: kein zweiter Eintrag", len(w.service.winners) == 1
          and "Schon eingetragen" in MESSAGES)
    dialogs.bingo_check_dialog = lambda parent, count, rule: (2, "")
    dialogs.bingo_result_dialog = lambda *args: True
    w._verify_bingo(None)
    check("Karte ohne Bingo wird nicht eingetragen", len(w.service.winners) == 1)

    # Stufen und Runden
    drawn = len(w.service.game.caller.drawn)
    w._advance_stage()
    check("Weiter zu 2 Reihen, Ziehung läuft weiter", w.service.win_target == "zwei_reihen"
          and len(w.service.game.caller.drawn) == drawn and w.win_buttons["zwei_reihen"].get_active())
    check("Stufen-Button zeigt nächstes Ziel", w.stage_button.get_label() == "Weiter: Volle Karte")
    check("Banner nach Stufenwechsel weg", w.beamer.state.banner == "")
    w._advance_stage()
    w._advance_stage()
    check("Neue Runde: Runde 2, neu gemischt, wieder 1 Reihe",
          w.service.round_number == 2 and w.service.win_target == "reihe" and not w.service.game.caller.drawn)
    check("Kopfzeile zeigt Runde 2", w.rule_pill.get_text().startswith("Runde 2 · Ziel: 1 Reihe"))
    check("Gewinnerliste bleibt über Runden", len(w.service.winners) == 1)

    # Speichern
    w._save_settings()
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Spielstand: Titel, Runde, Timer, Gewinner", saved["settings"]["round_number"] == 2
          and saved["settings"]["event_title"].startswith("Weihnachtsfeier") and len(saved["winners"]) == 1)

    # Regression: „Neu mischen“ mitten im Spiel startet eine neue Runde
    w._draw_next()
    w._reshuffle(None)
    check("Neu mischen = neue Runde 3", w.service.round_number == 3 and w.win_buttons["reihe"].get_active())

    # Regression: Aufdecken-Knopf nach Import synchron
    w.reveal_button.set_active(True)
    from musik_bingo.application.game_service import GameService
    w._apply_service_to_widgets(GameService.from_dict(w.service.to_dict()))
    check("Nach Import: Titel verdeckt und Knopf nicht aktiv", not w.revealed and not w.reveal_button.get_active())

    # Neue Karten setzen den Abend zurück (alte liegen in der Sicherung)
    w._generate(None)
    check("Neue Karten: Gewinnerliste leer, Runde 1", w.service.winners == [] and w.service.round_number == 1)
    check("Sicherung mit alten Gewinnern vorhanden", any(
        json.loads(p.read_text()).get("winners") for p in w.store.backups()))

    # Beamer schließen und Programmende ohne hängende Timer
    w.beamer_button.set_active(False)
    check("Beamer geschlossen", w.beamer is None)
    w._before_close(w, None)
    check("Timer-Quelle beim Schließen entfernt", w.timer_source == 0)
    start = time.monotonic()
    pump(0.3)
    check("Kein Absturz nach dem Schließen", time.monotonic() - start < 5)


run(scenario)
