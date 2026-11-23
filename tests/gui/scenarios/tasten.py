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


def type_text(text: str) -> None:
    subprocess.run(["xdotool", "type", "--delay", "60", text], check=False, timeout=10)
    pump(0.4)


def click(window, widget) -> None:
    """Echter Mausklick mitten auf das Widget."""
    x, y = widget.translate_coordinates(window, 0, 0)
    _ok, origin_x, origin_y = window.get_window().get_origin()
    allocation = widget.get_allocation()
    subprocess.run(["xdotool", "mousemove", str(origin_x + x + allocation.width // 2),
                    str(origin_y + y + allocation.height // 2), "click", "1"], check=False, timeout=10)
    pump(0.9)  # länger als die Doppelklick-Sperre


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

    # Regression: Eingetippte Sekunden (ohne Enter/Tab) galten beim Ziehen nicht. Knöpfe und Kürzel nehmen dem
    # Zahlenfeld den Fokus nicht, es übernahm die Zahl also nie – im Feld stand „15“, der Timer blieb aus.
    w.timer_spin.set_value(0)
    w.timer_spin.grab_focus()  # markiert den alten Wert, Tippen ersetzt ihn
    type_text("15")
    press(w, "space")
    check("eingetippter Song-Timer (15) gilt beim Ziehen mit der Leertaste",
          w.service.timer_seconds == 15 and w.timer.phase == "läuft" and w.timer.remaining >= 13)
    w.reveal_spin.grab_focus()
    type_text("7")
    click(w, w.draw_button)
    check("eingetippte Auflösung (7) gilt beim Ziehen per Mausklick",
          w.service.reveal_seconds == 7 and w.timer.reveal_seconds == 7 and w.timer.phase == "läuft")
    # Schaltet der Timer selbst weiter, während das Feld gerade leer ist (mitten im Tippen), bleibt der alte Wert –
    # ein leeres Feld hieße sonst 0 = „Timer aus“ und der Ablauf bliebe stehen.
    w.timer_spin.set_text("")
    w._draw_next(by_timer=True)
    check("leeres Feld mitten im Tippen schaltet den laufenden Timer nicht ab",
          w.service.timer_seconds == 15 and w.timer.phase == "läuft")
    w.timer_spin.set_value(0)  # Timer aus: die folgenden Schritte sollen nicht in eine Auflösung laufen

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

    # Regression: Auch ein ECHTER Klick auf einen Knopf beendet die Tab-Navigation. Knöpfe verbrauchen den Klick
    # selbst – das Fenster sah ihn nie, und die nächste Leertaste schaltete z. B. das Gewinnziel um.
    w.win_buttons["volle_karte"].set_active(True)
    w.nav.get_row_at_index(2).grab_focus()
    press(w, "Tab")
    check("Tab schaltet die Tastatur-Navigation ein", w.keyboard_navigating)
    click(w, w.draw_button)
    before = drawn()
    press(w, "space")
    check("echter Klick auf „Nächsten Song ziehen“ beendet die Tab-Navigation",
          not w.keyboard_navigating and drawn() == before + 1 and w.service.win_target == "volle_karte")

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
