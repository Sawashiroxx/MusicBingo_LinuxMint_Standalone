"""E2E „wie am Abend“: Laptop mit 1366×768, ECHTE Dialoge, echte Tasten und Mausklicks.

Anders als die übrigen Szenarien werden Rückfragen und Meldungen hier nicht automatisch bestätigt:
Jeder Dialog muss wirklich erscheinen, den erwarteten Titel tragen und auf den Bildschirm passen.
Deckt die Fehler ab, die in der Gesamtprüfung 11/2026 durch die „netten“ GUI-Tests gerutscht sind:

- gehaltene Leertaste/Rücktaste/T und Doppelklick lösen mehrfach aus (F-02)
- Ziehen-Knopf springt bei unterschiedlich langen Titeln unter der Maus weg (F-01)
- Tippfehler bei der Kartennummer prüft still eine andere Karte (F-09)
- Ergebnisdialog wird höher als der Bildschirm (F-11), Beamer breiter als 1280 px (F-10)
- Speicherfehler fällt nicht auf (F-04)
"""
import shutil
import subprocess
import sys

from common import GLib, Gtk, check, forbid_network, pump, run

if not shutil.which("xdotool"):
    # Kein stilles „bestanden“: test_gui.py überspringt den Test vorher sichtbar (skipTest)
    print("FAIL xdotool fehlt – echte Tastendrücke nicht möglich")
    sys.exit(1)
forbid_network()

SCREEN_HEIGHT = 768
LONG_SONGS = [
    ("Happy Xmas (War Is Over) - Remastered 2010", "John Lennon, Yoko Ono, The Plastic Ono Band, The Harlem Community Choir"),
    ("Santa Claus Is Comin' to Town - Live at C.W. Post College", "Bruce Springsteen"),
    ("Wonderful Christmastime - Edited Version / Remastered 2011", "Paul McCartney"),
    ("Do They Know It's Christmas? (Feed the World) – 1984 Version", "Band Aid"),
    ("Fairytale of New York (feat. Kirsty MacColl)", "The Pogues, Kirsty MacColl"),
    ("Baby, It's Cold Outside (feat. Meghan Trainor)", "Brett Eldredge, Meghan Trainor"),
    ("Thank You (Not So Bad)", "Dimitri Vegas & Like Mike, Tiësto, W&W & Dido"),
    ("It's Beginning to Look a Lot Like Christmas", "Michael Bublé"),
]
SHORT_SONGS = [("Last Christmas", "Wham!"), ("Stille Nacht", "Traditional"), ("Santa Tell Me", "Ariana Grande")]


# ---------------------------------------------------------------- Hilfen: echte Eingaben ----------------
def xdo(*args: str) -> None:
    subprocess.run(["xdotool", *args], check=False, timeout=20, capture_output=True)


def focus(window) -> None:
    xdo("windowfocus", "--sync", str(window.get_window().get_xid()))


def hold(window, key: str, seconds: float) -> None:
    """Taste wirklich gedrückt halten – der X-Server schickt dann Tastenwiederholungen."""
    focus(window)
    xdo("keydown", key)
    pump(seconds)
    xdo("keyup", key)
    pump(0.4)


def screen_box(window, widget) -> tuple[int, int, int, int]:
    x, y = widget.translate_coordinates(window, 0, 0)
    _ok, ox, oy = window.get_window().get_origin()
    allocation = widget.get_allocation()
    return ox + x, oy + y, allocation.width, allocation.height


# ---------------------------------------------------------------- Hilfen: echte Dialoge -----------------
def visible_dialog():
    for top in Gtk.Window.list_toplevels():
        if isinstance(top, Gtk.Dialog) and top.get_visible() and top.get_mapped():
            return top
    return None


def dialog_text(dialog) -> str:
    """Titel bzw. Haupttext eines Dialogs (MessageDialog: Text, sonst Fenstertitel)."""
    if isinstance(dialog, Gtk.MessageDialog):
        return dialog.get_property("text") or ""
    return dialog.get_title() or ""


def find_button(widget, text: str):
    if isinstance(widget, Gtk.Button) and (widget.get_label() or "") == text:
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = find_button(child, text)
            if found is not None:
                return found
    return None


def find_widget(widget, kind):
    if isinstance(widget, kind):
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = find_widget(child, kind)
            if found is not None:
                return found
    return None


class DialogRobot:
    """Bedient die Dialoge, die die App öffnet – wie eine Person vor dem Bildschirm.

    expect() legt die nächsten Schritte fest: (erwarteter Titel, Aktion(dialog)). Läuft die ganze Zeit mit:
    Ein Dialog, der nicht erwartet wird, wird notiert und abgebrochen – so kann das Szenario nie hängen.
    """

    def __init__(self):
        self.steps: list = []
        self.seen: list[str] = []
        self.heights: dict[str, int] = {}
        self.unexpected: list[str] = []
        GLib.timeout_add(150, self._tick)

    def expect(self, steps) -> None:
        self.steps = list(steps)
        self.seen = []

    def _tick(self) -> bool:
        dialog = visible_dialog()
        if dialog is None:
            return True
        title = dialog_text(dialog)
        pump(0.3)  # fertig aufbauen lassen, dann messen
        self.seen.append(title)
        self.heights[title] = max(self.heights.get(title, 0), dialog.get_window().get_height())
        if self.steps and self.steps[0][0] in title:
            _expected, action = self.steps.pop(0)
            action(dialog)
        else:
            self.unexpected.append(title)
            dialog.response(Gtk.ResponseType.CANCEL)
        return True


def entries(widget) -> list:
    found = [widget] if isinstance(widget, Gtk.Entry) else []
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found += entries(child)
    return found


def enter_number(text: str, name: str = ""):
    """Kartennummer (und Namen) eintippen und „Prüfen“ klicken."""
    def action(dialog):
        spin = find_widget(dialog, Gtk.SpinButton)
        spin.set_text(text)
        for entry in entries(dialog):
            if not isinstance(entry, Gtk.SpinButton):
                entry.set_text(name)
        find_button(dialog, "Prüfen").clicked()
    return action


def press_button(text: str):
    def action(dialog):
        button = find_button(dialog, text)
        if button is None:
            check(f"Knopf „{text}“ im Dialog vorhanden", False)
            dialog.response(Gtk.ResponseType.CANCEL)
        else:
            button.clicked()
    return action


def close_message(dialog) -> None:
    dialog.response(Gtk.ResponseType.OK)


# ---------------------------------------------------------------- Szenario -----------------------------
def scenario(w):
    from musik_bingo.domain.caller import Caller
    robot = DialogRobot()
    from musik_bingo.domain.models import Song

    w.resize(1320, 700)  # maximiertes Fenster auf 1366×768 (Platz für Rahmen, Kopfleiste, Panel)
    songs = [Song(t, a) for t, a in LONG_SONGS + SHORT_SONGS] + [Song(f"Titel {i}", f"Interpret {i}") for i in range(64)]
    w.song_buffer.set_text("\n".join(s.display_name for s in songs))
    w.count_spin.set_value(160)
    w._generate(None)
    game = w.service.game
    # Feste Reihenfolge: langer Titel, kurzer Titel, langer Titel … (bringt den Knopf zum Springen, wenn er es kann)
    long, short, rest = game.songs[:8], game.songs[8:11], game.songs[11:]
    order = [long[0], short[0], long[1], short[1], long[2], short[2], long[3], rest[0], long[4], rest[1],
             long[5], rest[2], long[6], long[7]] + rest[3:]
    game.caller = Caller(game.songs, order, -1)
    w._render_caller()
    w._select_page("game")
    pump(0.6)
    drawn = lambda: len(game.caller.drawn)  # noqa: E731

    # 1. Gehaltene Tasten lösen genau einmal aus (F-02)
    hold(w, "space", 1.5)
    check("Leertaste 1,5 s gehalten: genau 1 Song gezogen", drawn() == 1)
    hold(w, "space", 0.1)
    before = drawn()
    hold(w, "BackSpace", 1.2)
    check("Rücktaste 1,2 s gehalten: genau 1 Song zurückgenommen", before - drawn() == 1)
    hold(w, "space", 0.1)
    toggles = []
    handler = w.reveal_button.connect("toggled", lambda b: toggles.append(b.get_active()))
    hold(w, "t", 1.2)
    w.reveal_button.disconnect(handler)
    check("T 1,2 s gehalten: Titel genau einmal umgeschaltet", len(toggles) == 1)

    # 2. Ziehen-Knopf bleibt unter der Maus, echte Klicks ziehen jeweils genau einen Song (F-01)
    x, y, width, height = screen_box(w, w.draw_button)
    xdo("mousemove", str(x + width // 2), str(y + height // 2))
    stage = w.service.win_target
    tops = []
    for _ in range(6):
        before = drawn()
        xdo("click", "1")
        pump(0.8)  # länger als die Doppelklick-Sperre
        tops.append(screen_box(w, w.draw_button)[1])
        check(f"Mausklick auf dieselbe Stelle zieht genau 1 Song (Song {drawn()})", drawn() == before + 1)
    check("Ziehen-Knopf springt nicht (lange und kurze Titel im Wechsel)", max(tops) - min(tops) <= 2)
    check("Kein Klick hat aus Versehen das Gewinnziel weitergeschaltet", w.service.win_target == stage)

    # 3. Doppelklick zieht nur einen Song
    before = drawn()
    xdo("click", "--repeat", "2", "--delay", "120", "1")
    pump(0.8)
    check("Doppelklick auf „Ziehen“: genau 1 Song", drawn() == before + 1)

    # 4. Bingo prüfen mit echten Dialogen (F-09, F-11)
    for song in game.cards[0].songs:  # Karte 1 komplett gezogen → Bingo
        w.service.draw_song(song)
    w._render_caller()
    robot.expect([
        ("Bingo prüfen", enter_number("1600")), ("Ungültige Kartennummer", close_message),
        ("Bingo prüfen", enter_number("")), ("Ungültige Kartennummer", close_message),
        ("Bingo prüfen", enter_number("1", "Maximilian Mustermann-Langname")), ("BINGO bestätigt", press_button("Als Gewinner eintragen")),
    ])
    for _ in range(3):
        w._verify_bingo(None)
        pump(0.3)
    check("Tippfehler „1600“ und leeres Feld melden „Ungültige Kartennummer“",
          robot.seen.count("Ungültige Kartennummer") == 2)
    check("Gültige Nummer zeigt „BINGO bestätigt!“", any("BINGO bestätigt" in t for t in robot.seen))
    check("Karte 1 steht in der Gewinnerliste", [winner.card for winner in w.service.winners] == [1])
    # Ergebnisdialog mit einer Karte voller langer Spotify-Titel (mehrere Interpreten) – der schlimmste Fall
    from musik_bingo.domain.models import BingoCard
    from musik_bingo.presentation import dialogs
    long_card = BingoCard([Song(f"{t} ({n})", a) for n in ("Live", "Remix", "Acoustic") for t, a in LONG_SONGS])
    robot.expect([("BINGO bestätigt", press_button("Schließen"))])
    dialogs.bingo_result_dialog(w, long_card, 7, "Gast", 5, True, {x.key for x in long_card.songs[:5]},
                                ["Reihe 1"], {0, 1, 2, 3, 4}, "1 Reihe", True, False)
    pump(0.3)
    tallest = max(robot.heights.values(), default=0)
    check(f"Alle Dialoge passen auf 768 px Höhe (höchster: {tallest} px)", 0 < tallest <= SCREEN_HEIGHT - 40)

    # 5. Beamer mit langem Gewinnernamen bleibt schmaler als ein 1280er-Beamer (F-10)
    w.service.set_event_title("Weihnachtsfeier der Abteilung Kundenservice und Vertrieb 2026")
    w.beamer_button.set_active(True)
    pump(0.6)
    w._update_beamer()
    check("Beamer zeigt das BINGO-Banner mit Gewinnernamen", "Mustermann" in w.beamer.banner_label.get_text())
    pump(0.6)
    minimum = w.beamer.get_preferred_width()[0]
    check(f"Beamer braucht höchstens 1280 px Breite ({minimum} px)", minimum <= 1280)
    w.beamer_button.set_active(False)
    pump(0.3)

    # 6. Speicherfehler (z. B. Platte voll) wird sichtbar gemeldet (F-04)
    def disk_full(_service):
        raise OSError(28, "No space left on device")
    w.store.save = disk_full
    robot.expect([("Spielstand wird nicht gespeichert", close_message)])
    w._draw_next()
    pump(1.0)
    check("Speicherfehler: Fehlerdialog erscheint", "Spielstand wird nicht gespeichert" in robot.seen)
    check("Speicherfehler: Kopfzeile zeigt „NICHT GESPEICHERT“", "NICHT GESPEICHERT" in w.privacy_pill.get_text())
    check(f"Kein unerwarteter Dialog im ganzen Ablauf ({robot.unexpected})", not robot.unexpected)


run(scenario)
