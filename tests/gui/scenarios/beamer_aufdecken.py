"""E2E: „Titel auf dem Beamer aufdecken“ an/aus.

Aus: Die Gäste sehen nie einen Songtitel – weder per Taste T noch in der Auflösung des Song-Timers oder
unter „Zuletzt“. Die Spielleitung sieht den Titel weiter im Hauptfenster. Die Einstellung wird gespeichert.
"""
import json

from common import MESSAGES, TMP, check, forbid_network, pump, run

forbid_network()


def scenario(w):
    from musik_bingo.application.beamer_state import HIDDEN
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
    check("Standard: Aufdecken ist an", w.beamer_reveal_check.get_active() and w.reveal_button.get_sensitive())

    w._draw_next()
    first = w.service.game.caller.current
    w.reveal_button.set_active(True)  # wie Taste T
    check("An: Beamer zeigt den aufgedeckten Titel", w.beamer.title_label.get_text() == first.title)
    w._draw_next()
    check("An: „Zuletzt“ nennt den vorherigen Song", first.display_name in w.beamer.recent_label.get_text())

    w.beamer_reveal_check.set_active(False)
    current = w.service.game.caller.current
    check("Aus: Aufdecken-Knopf gesperrt", not w.reveal_button.get_sensitive())
    w._set_revealed(True)  # so löst der Song-Timer auf
    pump(0.1)
    check("Aus: Beamer zeigt keinen Titel, auch nicht in der Auflösung",
          w.beamer.title_label.get_text() == HIDDEN and not w.beamer.artist_label.get_visible())
    check("Aus: „Zuletzt“ ist leer", w.beamer.recent_label.get_text() == "")
    check("Aus: Spielleitung sieht den Titel weiter", w.song_label.get_text() == current.title)
    w.reveal_button.set_active(False)
    w._on_key(w, _key("t"))
    check("Aus: Taste T deckt nichts auf", not w.reveal_button.get_active()
          and w.beamer.title_label.get_text() == HIDDEN)

    w._save_settings()
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Einstellung gespeichert", saved["settings"]["beamer_reveal"] is False)
    from musik_bingo.application.game_service import GameService
    w._apply_service_to_widgets(GameService.from_dict(saved))
    check("Nach dem Laden: Haken aus, Aufdecken gesperrt", not w.beamer_reveal_check.get_active()
          and not w.reveal_button.get_sensitive() and not w.service.beamer_reveal)
    w._draw_next()
    current = w.service.game.caller.current

    w.beamer_reveal_check.set_active(True)
    w._set_revealed(True)
    check("Wieder an: Titel erscheint", w.beamer.title_label.get_text() == current.title
          and w.reveal_button.get_sensitive())
    w.beamer_button.set_active(False)
    check("Keine Fehlermeldungen", MESSAGES == [])


def _key(name: str):
    from gi.repository import Gdk
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = Gdk.keyval_from_name(name)
    return event


run(scenario)
