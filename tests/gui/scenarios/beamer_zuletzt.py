"""E2E: „Zuletzt“ auf dem Beamer – Anzahl (0–5, Standard 3) und Schriftgröße einstellbar.

Für weit entfernte Plätze: weniger Songs, größere Schrift. Auch mit „Sehr groß“, langen Titeln, Countdown und
BINGO-Banner bleibt auf 1280×720, 1024×768 und 1920×1080 alles im Bild und überlappt nicht (notfalls wird der ganze
Inhalt verkleinert). Jeder Song steht in genau einer Zeile – zu lange Zeilen enden mit „…“, statt umzubrechen.
Ohne „Titel auf dem Beamer aufdecken“ ruhen die Einstellungen. Speichern und Laden der Einstellungen.
Aufruf: beamer_zuletzt.py [zielordner für Screenshots]
"""
import json
import sys
from pathlib import Path

from common import MESSAGES, TMP, check, forbid_network, patch_dialogs, pump, run, screenshot

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
    from musik_bingo.application.beamer_state import build_beamer_state
    from musik_bingo.application.game_service import GameService
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

    # Regression: „Zuletzt“ brach lange Zeilen um. Die zentrierte Fortsetzung („& Anastacia“) sah wie ein eigener
    # Song aus und kostete Höhe – der Songtitel wurde dafür unnötig verkleinert.
    smallest = 1.0
    for width, height in ((1280, 720), (1024, 768), (1920, 1080)):
        for banner in ("", "BINGO! Karte #123 · Maximilian Mustermann-Langname"):
            for size in ("normal", "sehr_gross"):
                for count in (3, 5):
                    for countdown in ("", "Auflösung · nächster Song in 5 s"):
                        w.recent_size_combo.set_active_id(size)
                        w.recent_count_spin.set_value(count)
                        w.banner = banner
                        beamer.update(build_beamer_state(w.service, True, countdown, banner))
                        beamer.resize(width, height)
                        pump(0.4)
                        got = beamer.get_size()
                        visible = [(name, box(beamer, widget)) for name, widget in (
                            ("Feiertitel", beamer.event_label), ("Runde", beamer.round_label),
                            ("Song", beamer.song_label), ("Titel", beamer.title_label),
                            ("Interpret", beamer.artist_label), ("Countdown", beamer.timer_label),
                            ("Banner", beamer.banner), ("Zuletzt", beamer.recent_label))
                            if widget.get_visible()]
                        inside = all(0 <= top and bottom <= got.height for _name, (top, bottom) in visible)
                        ordered = all(first[1][1] <= second[1][0] for first, second in zip(visible, visible[1:]))
                        lines = beamer.recent_label.get_layout().get_line_count()
                        smallest = min(smallest, beamer.scale)
                        case = (f"{width}×{height} {size}, {count} Songs{' mit Banner' if banner else ''}"
                                f"{' und Countdown' if countdown else ''}")
                        check(f"{case}: alles im Bild, ohne Überlappung (Stufe {beamer.scale})",
                              (got.width, got.height) == (width, height) and inside and ordered
                              and bool(countdown) == beamer.timer_label.get_visible())
                        check(f"{case}: ein Song pro Zeile ({lines} Zeilen für „Zuletzt“ + {count} Songs)",
                              lines == count + 1)
                        check(f"{case}: Songtitel vollständig (ohne „…“)",
                              not beamer.title_label.get_layout().is_ellipsized())
                        if OUT is not None and banner and size == "sehr_gross" and count == 3 and countdown:
                            screenshot(beamer, OUT / f"beamer-zuletzt-{height}.png")
    check(f"Schrift nie unter 50 % (kleinste Stufe {smallest})", smallest >= 0.5)

    # Nur die Größe ändert sich (sonst nichts): Der Beamer passt neu ein, und die Größe von „Zuletzt“ bleibt im
    # Verhältnis zum übrigen Text – sie wird mit der Einpass-Stufe mitverkleinert.
    def line_ratio() -> float:
        layout = beamer.recent_label.get_layout()
        return (layout.get_pixel_size()[1] / layout.get_line_count()) / beamer.round_label.get_allocated_height()

    w.banner = "BINGO! Karte #123 · Maximilian Mustermann-Langname"
    w.recent_count_spin.set_value(5)
    ratios = {}
    for width, height in ((1920, 1080), (1280, 720)):
        w.recent_size_combo.set_active_id("normal")
        w._update_beamer()
        beamer.resize(width, height)
        pump(0.5)
        before = beamer.scale
        w.recent_size_combo.set_active_id("sehr_gross")  # einzige Änderung am Beamer-Inhalt
        pump(0.1)  # keine Größenänderung des Fensters: Einpassen muss von update() kommen
        bottom = box(beamer, beamer.recent_label)[1]
        ratios[height] = line_ratio()
        check(f"{width}×{height}: Wechsel auf „Sehr groß“ passt neu ein (Stufe {before} → {beamer.scale}, "
              f"unten {bottom} von {height})", bottom <= height and (height == 1080 or beamer.scale < before))
    check(f"„Sehr groß“ ist auf 1280×720 im Verhältnis so groß wie auf 1920×1080 ({ratios})",
          abs(ratios[720] / ratios[1080] - 1) < 0.15)
    w.recent_size_combo.set_active_id("sehr_gross")
    w.recent_count_spin.set_value(3)
    beamer.resize(1024, 768)
    pump(0.4)
    check("1024×768 „Sehr groß“: zu lange Zeile endet mit „…“",
          beamer.recent_label.get_layout().is_ellipsized()
          and beamer.recent_label.get_text().splitlines()[1:] == list(beamer.state.recent))
    w.recent_size_combo.set_active_id("normal")
    beamer.resize(1920, 1080)
    pump(0.4)
    check("1920×1080 „Normal“: nichts gekürzt", not beamer.recent_label.get_layout().is_ellipsized())
    w.banner = ""

    w.beamer_reveal_check.set_active(False)
    check("Ohne Aufdecken: „Zuletzt“ leer, Einstellungen ruhen",
          beamer.recent_label.get_text() == "" and not w.recent_count_spin.get_sensitive()
          and not w.recent_size_combo.get_sensitive())
    w.beamer_reveal_check.set_active(True)
    check("Wieder an: Einstellungen bedienbar",
          w.recent_count_spin.get_sensitive() and w.recent_size_combo.get_sensitive())

    # Speichern über _save_settings (nicht nur über die Bedienelemente) und Laden in beide Richtungen
    w.recent_count_spin.set_value(1)
    w.recent_size_combo.set_active_id("gross")
    w.service.beamer_recent_count, w.service.beamer_recent_size = 5, "normal"  # _save_settings muss übernehmen
    w._save_settings()
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("_save_settings übernimmt Anzahl und Größe",
          (saved["settings"]["beamer_recent_count"], saved["settings"]["beamer_recent_size"]) == (1, "gross"))
    saved["settings"].update(beamer_recent_count=4, beamer_recent_size="sehr_gross", beamer_reveal=False)
    w._apply_service_to_widgets(GameService.from_dict(saved))
    check("Laden (4, Sehr groß, Aufdecken aus): Bedienelemente zeigen die Werte und sind gesperrt",
          w.recent_count_spin.get_value_as_int() == 4 and w.recent_size_combo.get_active_id() == "sehr_gross"
          and not w.recent_count_spin.get_sensitive() and not w.recent_size_combo.get_sensitive()
          and (w.service.beamer_recent_count, w.service.beamer_recent_size) == (4, "sehr_gross"))
    for key in ("beamer_recent_count", "beamer_recent_size", "beamer_reveal"):
        del saved["settings"][key]
    w._apply_service_to_widgets(GameService.from_dict(saved))
    w._update_beamer()
    check("Laden eines alten Spielstands (ohne die Felder): 3, Normal, bedienbar",
          w.recent_count_spin.get_value_as_int() == 3 and w.recent_size_combo.get_active_id() == "normal"
          and w.recent_count_spin.get_sensitive() and w.recent_size_combo.get_sensitive()
          and (w.service.beamer_recent_count, w.service.beamer_recent_size) == (3, "normal")
          and beamer.recent_scale == 1.0)
    # Leeres Zahlenfeld (Rücktaste mit Fokus im Feld) gilt nie als 0 – weder beim Speichern noch beim Ziehen
    w.recent_count_spin.set_text("")
    w._save_settings()
    check("Leeres Feld beim Speichern: Anzahl bleibt 3",
          w.service.beamer_recent_count == 3 and w.recent_count_spin.get_text() == "3")
    check("Keine Fehlermeldungen", MESSAGES == [])
    w.beamer_button.set_active(False)


run(scenario)
