"""Screenshots aller Bereiche und Dialoge (dunkel/hell). Aufruf: screenshots.py <dark|light> <zielordner>"""
import sys
from pathlib import Path

THEME, OUT = sys.argv[1], Path(sys.argv[2])
from common import TMP, GLib, Gtk, check, forbid_network, pump, run, screenshot  # noqa: E402

(TMP / "config" / "musik-bingo").mkdir(parents=True, exist_ok=True)
(TMP / "config" / "musik-bingo" / "theme").write_text(THEME)
forbid_network()


def dialog_shot(name, opener):
    def snap():
        for top in Gtk.Window.list_toplevels():
            if isinstance(top, Gtk.Dialog) and top.get_visible():
                check(f"Screenshot {THEME}-{name}", screenshot(top, OUT / f"{THEME}-{name}.png"))
                top.response(Gtk.ResponseType.CANCEL)
                return False
        return True
    GLib.timeout_add(700, snap)
    opener()


def scenario(w):
    from musik_bingo.domain.card_generator import winning_cells
    from musik_bingo.presentation import dialogs
    w.resize(1320, 820)
    pump(0.6)
    check(f"Screenshot {THEME}-songs", screenshot(w, OUT / f"{THEME}-songs.png"))
    dialog_shot("dialog-mix", lambda: dialogs.mix_dialog(w, w.catalogs))
    dialog_shot("dialog-import", lambda: dialogs.import_playlist_dialog(w))
    w.service.set_song_text(w._song_text())
    w.service.create_cards(5, True, 160)
    w._update_forecast()
    w._render_cards()
    w._render_caller()
    w._select_page("cards")
    pump(0.6)
    check(f"Screenshot {THEME}-karten", screenshot(w, OUT / f"{THEME}-karten.png"))
    w._select_page("game")
    pump(0.3)
    minimum = w.get_preferred_width()[0]
    print(f"Mindestbreite Spielleitung: {minimum}px")
    # Regression: vier Wiedergabeziele in einer Zeile machten das Fenster breiter als 1366er-Bildschirme
    check(f"{THEME}: Spielleitung ist schmal genug für 1366-px-Bildschirme (mit Rahmen)", minimum <= 1320)
    caller = w.service.game.caller
    card = w.service.game.cards[0]
    for song in card.songs[:5]:
        caller.draw_song(song)
    caller.draw_next()
    w._render_caller()
    pump(0.6)
    check(f"Screenshot {THEME}-spielleitung", screenshot(w, OUT / f"{THEME}-spielleitung.png"))
    w.service.set_event_title("Weihnachtsfeier 2026")
    w.timer_spin.set_value(45)
    w._new_song_started()
    w.beamer_button.set_active(True)
    w.beamer.move(0, 0)
    w.beamer.resize(1280, 720)
    pump(0.8)
    check(f"Screenshot {THEME}-beamer", screenshot(w.beamer, OUT / f"{THEME}-beamer.png"))
    w.beamer_button.set_active(False)
    w.timer_spin.set_value(0)
    game = w.service.game
    dialog_shot("dialog-bingo", lambda: dialogs.bingo_result_dialog(
        w, card, 1, "Gast", 5, True, {s.key for s in caller.drawn}, w.service.check_bingo(1),
        winning_cells(card, game.size, game.free_space, caller.drawn, False)))
    check_minimum_size(w)


def check_minimum_size(w):
    """Regression: Die Songliste erzwang ~960 px Fensterhöhe – auf 1366×768-Laptops ragte das Fenster
    unten aus dem Bildschirm. Jede Seite muss mit jedem Wiedergabeziel in 1320×700 passen
    (Platz für Rahmen, Titelleiste und Panel)."""
    for target in ("lokal", "spotify", "youtube"):
        w.target_buttons[target].set_active(True)
        for page in ("songs", "cards", "game"):
            w._select_page(page)
            pump(0.3)
            w.resize(1, 1)
            pump(0.4)
            width, height = w.get_size()
            print(f"Mindestgröße {target}/{page}: {width}×{height}px")
            check(f"{THEME}: {page} mit {target} passt auf 1366×768 ({width}×{height} ≤ 1320×700)",
                  width <= 1320 and height <= 700)
    w.target_buttons["lokal"].set_active(True)
    # Regression: Die Vorschau von 3×3-Karten erzwang drei Karten pro Zeile – das Fenster war damit auf jeder
    # Seite mindestens 1380 px breit, breiter als ein 1366-px-Bildschirm.
    w.service.create_cards(3, True, 160)
    w._render_cards()
    w._render_caller()
    for page in ("songs", "cards", "game"):
        w._select_page(page)
        pump(0.3)
        w.resize(1, 1)
        pump(0.4)
        width, height = w.get_size()
        print(f"Mindestgröße 3×3/{page}: {width}×{height}px")
        check(f"{THEME}: {page} mit 3×3-Karten passt auf 1366×768 ({width}×{height} ≤ 1320×700)",
              width <= 1320 and height <= 700)
    w.resize(1320, 820)
    pump(0.3)


run(scenario)
