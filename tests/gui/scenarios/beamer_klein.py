"""E2E: Beamer mit kleiner Auflösung (1280×720, 1024×768) – alles bleibt im Bild und überlappt nicht.

Regression: Die Schriftgrößen sind feste Pixelwerte. Mit zweizeiligem Titel plus Countdown oder BINGO-Banner
brauchte der Inhalt bis zu 890 px Höhe; auf einem 720er-Beamer lag „Zuletzt“ dann über dem Banner. Außerdem ließ
sich das Fenster nicht kleiner als 940–1500 px machen (Mindesthöhe wurde für die Mindestbreite berechnet).
Aufruf: beamer_klein.py [zielordner für Screenshots]
"""
import sys
from pathlib import Path

from common import check, forbid_network, patch_dialogs, pump, run, screenshot

forbid_network()
patch_dialogs()
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SONGS = [
    ("The Shoop Shoop Song (It's In His Kiss)", "Cher"),
    ("Time To Say Goodbye (Con te partirò)", "Sarah Brightman & Andrea Bocelli"),
    ("Prayer In C (Robin Schulz Remix)", "Lilly Wood & The Prick and Robin Schulz"),
    ("Friday (Dopamine Re-Edit)", "Riton x Nightcrawlers feat. Mufasa & Hypeman"),
    ("I Belong To You (Il ritmo della passione)", "Eros Ramazzotti & Anastacia"),
    ("Ich kenne nichts (das so schön ist wie du)", "RZA feat. Xavier Naidoo"),
    ("Killing Me Softly (With His Song)", "Fugees"),
]
STATES = (
    ("verdeckt mit Countdown", False, "", "läuft"),
    ("aufgedeckt mit Countdown", True, "", "auflösung"),
    ("aufgedeckt mit BINGO-Banner", True, "BINGO! Karte #123 · Maximilian Mustermann-Langname", "aus"),
)


def box(window, widget) -> tuple[int, int]:
    _x, y = widget.translate_coordinates(window, 0, 0)
    return y, y + widget.get_allocated_height()


def scenario(w):
    from musik_bingo.domain.caller import Caller
    from musik_bingo.domain.models import Song

    songs = [Song(t, a) for t, a in SONGS] + [Song(f"Titel {i}", f"Interpret {i}") for i in range(20)]
    w.song_buffer.set_text("\n".join(s.display_name for s in songs))
    w.title_entry.set_text("Weihnachtsfeier 2026")
    w.size_combo.set_active(0)
    w.count_spin.set_value(20)
    w._generate(None)
    game = w.service.game
    order = game.songs[1:7] + game.songs[:1] + game.songs[7:]  # Song 7 = zweizeiliger Titel, davor 5 lange Titel
    game.caller = Caller(game.songs, order, -1)
    w._select_page("game")
    w.timer_spin.set_value(15)
    w.iconify()
    w.beamer_button.set_active(True)
    pump(0.4)
    beamer = w.beamer
    for _ in range(7):
        game.caller.draw_next()
    w._new_song_started()
    for width, height in ((1280, 720), (1024, 768), (1920, 1080)):
        for name, revealed, banner, phase in STATES:
            w.timer.start()
            if phase == "auflösung":
                w.timer.phase, w.timer.remaining = "auflösung", 5
            elif phase == "aus":
                w.timer.stop()
            w.banner = banner
            w._set_revealed(revealed)
            w._update_beamer()
            beamer.move(0, 0)
            beamer.resize(width, height)
            pump(0.5)
            got = beamer.get_size()
            case = f"{width}×{height} {name}"
            check(f"{case}: Fenster lässt sich auf Beamer-Größe bringen ({got.width}×{got.height})",
                  (got.width, got.height) == (width, height))
            visible = [(label, box(beamer, widget)) for label, widget in (
                ("Feiertitel", beamer.event_label), ("Runde", beamer.round_label), ("Song", beamer.song_label),
                ("Titel", beamer.title_label), ("Interpret", beamer.artist_label), ("Countdown", beamer.timer_label),
                ("Banner", beamer.banner), ("Zuletzt", beamer.recent_label)) if widget.get_visible()]
            inside = all(0 <= top and bottom <= got.height for _label, (top, bottom) in visible)
            ordered = all(first[1][1] <= second[1][0] for first, second in zip(visible, visible[1:]))
            check(f"{case}: alle Zeilen im Bild und ohne Überlappung (Schriftstufe {getattr(beamer, 'scale', 1.0)})",
                  inside and ordered)
            if OUT is not None and height == 720:
                screenshot(beamer, OUT / f"beamer-klein-{phase}.png")
    # Auf einem großen Beamer und bei kurzen Titeln bleibt die volle Schriftgröße (Titelzeile ≈ 92 px Schrift)
    w.banner = ""
    game.caller.draw_next()  # „Titel 0 – Interpret 0“
    w._new_song_started()
    w._set_revealed(True)
    w._update_beamer()
    beamer.resize(1920, 1080)
    pump(0.5)
    full = beamer.title_label.get_allocated_height()
    beamer.resize(1280, 720)
    pump(0.5)
    check(f"kurzer Titel: auf 1280×720 genauso groß wie auf 1920×1080 ({full} px Zeilenhöhe)",
          beamer.title_label.get_text() == "Titel 0" and full >= 100
          and beamer.title_label.get_allocated_height() == full)
    w.beamer_button.set_active(False)


run(scenario)
