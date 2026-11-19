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
    w.service.create_cards(5, True, 30)
    w._render_cards()
    w._render_caller()
    w._select_page("cards")
    pump(0.6)
    check(f"Screenshot {THEME}-karten", screenshot(w, OUT / f"{THEME}-karten.png"))
    w._select_page("game")
    caller = w.service.game.caller
    card = w.service.game.cards[0]
    for song in card.songs[:5]:
        caller.draw_song(song)
    caller.draw_next()
    w._render_caller()
    pump(0.6)
    check(f"Screenshot {THEME}-spielleitung", screenshot(w, OUT / f"{THEME}-spielleitung.png"))
    game = w.service.game
    dialog_shot("dialog-bingo", lambda: dialogs.bingo_result_dialog(
        w, card, 1, "Gast", 5, True, {s.key for s in caller.drawn}, w.service.check_bingo(1),
        winning_cells(card, game.size, game.free_space, caller.drawn, False)))


run(scenario)
