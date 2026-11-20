"""E2E: Tastenkürzel mit ECHTEN Tastendrücken (xdotool/XTEST), nicht per Direktaufruf.

Regression: GTK schaltet die Fokus-Anzeige bei jedem echten Tastendruck ein. Die App hielt den
Seitenleisten-Eintrag dann für „per Tab angesteuert“ und gab ihm die Leertaste – Kürzel taten nichts.
"""
import shutil
import subprocess
import sys

from common import check, forbid_network, patch_dialogs, pump, run

if not shutil.which("xdotool"):
    # Kein stilles „bestanden“: test_gui.py überspringt den Test vorher sichtbar (skipTest)
    print("FAIL xdotool fehlt – echte Tastendrücke nicht möglich")
    sys.exit(1)
forbid_network()
patch_dialogs()


def press(window, key: str) -> None:
    xid = window.get_window().get_xid()
    subprocess.run(["xdotool", "windowfocus", "--sync", str(xid)], check=False, timeout=10)
    subprocess.run(["xdotool", "key", "--clearmodifiers", key], check=False, timeout=10)
    pump(0.4)


def scenario(w):
    w.song_buffer.set_text("\n".join(f"Song {i} – Interpret {i}" for i in range(30)))
    w.count_spin.set_value(5)
    w._generate(None)
    w.nav.select_row(w.nav.get_row_at_index(2))  # wie ein Klick in der Seitenleiste
    pump(0.5)
    drawn = lambda: len(w.service.game.caller.drawn)  # noqa: E731

    press(w, "space")
    check("Leertaste zieht (Fokus auf Seitenleiste)", drawn() == 1)
    press(w, "t")
    check("T deckt auf", w.reveal_button.get_active())
    press(w, "T")
    check("T verbirgt wieder", not w.reveal_button.get_active())
    press(w, "BackSpace")
    check("Rücktaste nimmt zurück", drawn() == 0)

    w.draw_button.clicked()
    press(w, "space")
    check("Leertaste nach Klick auf „Nächsten Song ziehen“", drawn() == 2)

    w.timer_spin.set_value(30)
    w._new_song_started()
    w.timer_spin.grab_focus()  # nach Klick auf +/- im Timer-Feld
    press(w, "p")
    check("P pausiert auch mit Fokus im Timer-Feld", w.timer.paused)
    press(w, "p")
    check("P setzt fort", not w.timer.paused)
    before = drawn()
    press(w, "space")
    check("Leertaste zieht auch mit Fokus im Timer-Feld", drawn() == before + 1)

    w.pool_search.grab_focus()
    before = drawn()
    press(w, "space")
    press(w, "t")
    check("Suchfeld bekommt Leertaste und Buchstaben", drawn() == before and " t" in w.pool_search.get_text())
    w.pool_search.set_text("")

    # Wer per Tab navigiert, bedient das fokussierte Element – kein Song wird gezogen
    w.draw_button.grab_focus()
    press(w, "Tab")
    focused = w.get_focus()
    before = drawn()
    press(w, "space")
    # Nach dem Ziehen-Knopf kommt „Zurück“: Die Leertaste drückt diesen Knopf, das Kürzel zieht nicht
    check("nach Tab bedient die Leertaste das fokussierte Element",
          focused is w.undo_button and drawn() == before - 1)

    # Mausklick beendet die Tab-Navigation wieder
    w._on_pointer(w, None)
    w.nav.get_row_at_index(2).grab_focus()
    before = drawn()
    press(w, "space")
    check("nach Mausklick wirkt die Leertaste wieder als Kürzel", drawn() == before + 1)

    # Beamer hat den Fokus (zweiter Bildschirm): Tasten wirken trotzdem
    w.beamer_button.set_active(True)
    pump(0.5)
    before = drawn()
    press(w.beamer, "space")
    check("Leertaste im Beamer-Fenster zieht", drawn() == before + 1)
    press(w.beamer, "t")
    check("T im Beamer-Fenster deckt auf", w.reveal_button.get_active())
    w.beamer_button.set_active(False)


run(scenario)
