"""E2E: „Zuletzt“ auf dem Beamer – Anzahl (0–5, Standard 3) und Schriftgröße einstellbar.

Für weit entfernte Plätze: weniger Songs, größere Schrift. Auch mit „Sehr groß“, langen Titeln und BINGO-Banner
bleibt auf 1280×720 und 1920×1080 alles im Bild und überlappt nicht (notfalls wird der ganze Inhalt verkleinert).
Ohne „Titel auf dem Beamer aufdecken“ ruhen die Einstellungen.
Aufruf: beamer_zuletzt.py [zielordner für Screenshots]
"""
import sys
from pathlib import Path

from common import check, forbid_network, patch_dialogs, pump, run, screenshot

forbid_network()
patch_dialogs()
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
LONG = [
    ("The Shoop Shoop Song (It's In His Kiss)", "Cher"),
    ("Time To Say Goodbye (Con te partirò)", "Sarah Brightman & Andrea Bocelli"),
    ("Prayer In C (Robin Schulz Remix)", "Lilly Wood & The Prick and Robin Schulz"),
    ("Friday (Dopamine Re-Edit)", "Riton x Nightcrawlers feat. Mufasa & Hypeman"),
    ("I Belong To You (Il ritmo della passione)", "Eros Ramazzotti & Anastacia"),
    ("Ich kenne nichts (das so schön ist wie du)", "RZA feat. Xavier Naidoo"),
]


def box(window, widget) -> tuple[int, int]:
    _x, y = widget.translate_coordinates(window, 0, 0)
    return y, y + widget.get_allocated_height()


def scenario(w):
    from musik_bingo.domain.caller import Caller
    from musik_bingo.domain.models import Song

    songs = [Song(t, a) for t, a in LONG] + [Song(f"Titel {i}", f"Interpret {i}") for i in range(20)]
    w.song_buffer.set_text("\n".join(s.display_name for s in songs))
    w.title_entry.set_text("Weihnachtsfeier 2026")
    w.size_combo.set_active(0)
    w.count_spin.set_value(20)
    w._generate(None)
    game = w.service.game
    game.caller = Caller(game.songs, list(game.songs), -1)  # erst die sechs langen Titel
    w._select_page("game")
    w.iconify()
    w.beamer_button.set_active(True)
    pump(0.4)
    beamer = w.beamer
    for _ in range(7):
        game.caller.draw_next()
    w._new_song_started()
    w._set_revealed(True)
    w._update_beamer()
    check("Standard: 3 frühere Songs, normale Größe",
          w.recent_count_spin.get_value_as_int() == 3 and w.recent_size_combo.get_active_id() == "normal"
          and beamer.recent_label.get_text().splitlines()[1:] == list(w.beamer.state.recent)
          and len(w.beamer.state.recent) == 3)

    for count in (0, 1, 5):
        w.recent_count_spin.set_value(count)
        text = beamer.recent_label.get_text()
        check(f"Anzahl {count}: Beamer nennt genau {count} Songs",
              (text == "" and not count) or (text.startswith("Zuletzt\n") and len(text.splitlines()) == count + 1))
    w.recent_count_spin.set_value(3)

    beamer.move(0, 0)
    beamer.resize(1920, 1080)
    pump(0.5)
    heights = {}
    for size in ("normal", "gross", "sehr_gross"):
        w.recent_size_combo.set_active_id(size)
        pump(0.3)
        heights[size] = beamer.recent_label.get_allocated_height()
    check(f"Größe wirkt: Normal < Groß < Sehr groß ({heights})",
          heights["normal"] < heights["gross"] < heights["sehr_gross"])

    for width, height in ((1280, 720), (1920, 1080)):
        for banner in ("", "BINGO! Karte #123 · Maximilian Mustermann-Langname"):
            for size in ("normal", "sehr_gross"):
                w.recent_size_combo.set_active_id(size)
                w.banner = banner
                w._update_beamer()
                beamer.resize(width, height)
                pump(0.5)
                got = beamer.get_size()
                visible = [(name, box(beamer, widget)) for name, widget in (
                    ("Feiertitel", beamer.event_label), ("Runde", beamer.round_label), ("Song", beamer.song_label),
                    ("Titel", beamer.title_label), ("Interpret", beamer.artist_label),
                    ("Countdown", beamer.timer_label), ("Banner", beamer.banner), ("Zuletzt", beamer.recent_label))
                    if widget.get_visible()]
                inside = all(0 <= top and bottom <= got.height for _name, (top, bottom) in visible)
                ordered = all(first[1][1] <= second[1][0] for first, second in zip(visible, visible[1:]))
                case = f"{width}×{height} {size}{' mit Banner' if banner else ''}"
                check(f"{case}: alles im Bild, ohne Überlappung (Stufe {beamer.scale})",
                      (got.width, got.height) == (width, height) and inside and ordered)
                if OUT is not None and banner and size == "sehr_gross":
                    screenshot(beamer, OUT / f"beamer-zuletzt-{height}.png")
    w.banner = ""

    w.beamer_reveal_check.set_active(False)
    check("Ohne Aufdecken: „Zuletzt“ leer, Einstellungen ruhen",
          beamer.recent_label.get_text() == "" and not w.recent_count_spin.get_sensitive()
          and not w.recent_size_combo.get_sensitive())
    w.beamer_reveal_check.set_active(True)
    check("Wieder an: Einstellungen bedienbar", w.recent_count_spin.get_sensitive())
    w.beamer_button.set_active(False)


run(scenario)
