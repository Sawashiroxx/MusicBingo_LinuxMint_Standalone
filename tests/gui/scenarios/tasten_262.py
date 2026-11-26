"""E2E mit ECHTEN Tastendrücken (xdotool): Korrekturen aus der Gesamtprüfung von 2.6.2.

- Pfeiltaste mit Fokus in der Seitenleiste (dort steht er nach dem Start): Pfeil runter schaltete die Kürzel ab
  (die nächste Leertaste zog nichts), Pfeil hoch/runter wechselte mitten im Spiel die Seite.
- Gehaltenes Enter aus „Bingo prüfen“ bestätigte per Tastenwiederholung sofort „Als Gewinner eintragen“,
  ohne dass jemand die Karte gesehen hatte. Ein bewusstes Enter danach trägt weiter ein.
"""
import shutil
import subprocess
import sys

from common import GLib, Gtk, check, forbid_network, patch_dialogs, pump, run

if not shutil.which("xdotool"):
    print("FAIL xdotool fehlt – echte Tastendrücke nicht möglich")
    sys.exit(1)
forbid_network()
patch_dialogs()


def xdo(*args: str) -> None:
    subprocess.run(["xdotool", *args], check=False, timeout=20, capture_output=True)


def press(window, key: str) -> None:
    xdo("windowfocus", "--sync", str(window.get_window().get_xid()))
    xdo("key", "--clearmodifiers", key)
    pump(0.4)


def remove_source(source_id: int) -> None:
    """Zeitgeber entfernen, falls er noch nicht gelaufen ist."""
    if GLib.MainContext.default().find_source_by_id(source_id) is not None:
        GLib.source_remove(source_id)


def visible_dialog():
    for top in Gtk.Window.list_toplevels():
        if isinstance(top, Gtk.Dialog) and top.get_visible() and top.get_mapped():
            return top
    return None


def arrows_on_game_page(w):
    w.song_buffer.set_text("\n".join(f"Song {i} – Interpret {i}" for i in range(40)))
    w.size_combo.set_active(0)
    w.count_spin.set_value(30)
    w._generate(None)
    w.nav.select_row(w.nav.get_row_at_index(2))  # wie ein Klick in der Seitenleiste
    pump(0.5)
    drawn = lambda: len(w.service.game.caller.drawn)  # noqa: E731
    for key in ("Down", "Up", "Down", "Left", "Right"):
        before = drawn()
        press(w, key)
        check(f"{key}: Seite bleibt „Spielleitung“", w.stack.get_visible_child_name() == "game")
        press(w, "space")
        check(f"{key}, dann Leertaste: genau ein Song gezogen", drawn() == before + 1)
    # Auf anderen Seiten bleiben Pfeiltasten normale Navigation
    w._select_page("songs")
    w.nav.get_row_at_index(0).grab_focus()
    pump(0.3)
    press(w, "Down")
    check("Seite „Songs“: Pfeil runter navigiert weiter", w.stack.get_visible_child_name() != "songs"
          or w.get_focus() is not w.nav.get_row_at_index(0))
    w._select_page("game")
    w.nav.select_row(w.nav.get_row_at_index(2))
    pump(0.3)


def held_enter_does_not_confirm(w):
    from musik_bingo.presentation import dialogs

    dialogs.confirm = lambda *args, **kwargs: True
    for song in w.service.game.cards[4].songs:
        w.service.draw_song(song)
    w._render_caller()
    pump(0.3)
    seen = []

    def tick():
        dialog = visible_dialog()
        if dialog is None:
            return True
        title = dialog.get_title() or ""
        if title not in seen:
            seen.append(title)
            if title == "Bingo prüfen":
                xdo("windowfocus", "--sync", str(dialog.get_window().get_xid()))
                xdo("keydown", "Return")  # Enter gedrückt halten …
                GLib.timeout_add(1200, lambda: xdo("keyup", "Return") or False)  # … 1,2 s lang
        return True

    source = GLib.timeout_add(100, tick)
    closer = GLib.timeout_add(4000, lambda: [d.response(Gtk.ResponseType.CANCEL) for d in [visible_dialog()] if d]
                              and False)
    w._verify_bingo(None, preset=5)
    pump(0.5)
    GLib.source_remove(source)
    remove_source(closer)
    check(f"Ergebnis wurde angezeigt ({seen})", any(title.startswith("BINGO") for title in seen))
    check("Gehaltenes Enter trägt keinen Gewinner ein", [winner.card for winner in w.service.winners] == [])

    # Bewusst: kurzes Enter zum Prüfen, Karte ansehen, nach 1,1 s Enter → eingetragen
    state = {}

    def tick_ok():
        dialog = visible_dialog()
        if dialog is None:
            return True
        title = dialog.get_title() or ""
        if title == "Bingo prüfen" and "prüfen" not in state:
            state["prüfen"] = True
            xdo("windowfocus", "--sync", str(dialog.get_window().get_xid()))
            xdo("key", "Return")
        elif title.startswith("BINGO") and "ergebnis" not in state:
            state["ergebnis"] = True
            GLib.timeout_add(1100, lambda: xdo("key", "Return") or False)
        return True

    source = GLib.timeout_add(150, tick_ok)
    closer = GLib.timeout_add(8000, lambda: [d.response(Gtk.ResponseType.CANCEL) for d in [visible_dialog()] if d]
                              and False)
    w._verify_bingo(None, preset=5)
    pump(0.5)
    GLib.source_remove(source)
    remove_source(closer)
    check("Kurzes Enter, Karte ansehen, Enter: Gewinner eingetragen", [x.card for x in w.service.winners] == [5])


def scenario(w):
    arrows_on_game_page(w)
    held_enter_does_not_confirm(w)


run(scenario)
