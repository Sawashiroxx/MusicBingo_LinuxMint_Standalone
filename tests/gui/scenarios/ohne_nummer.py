"""E2E: Bingo prüfen ohne Kartennummer – Songs der Gewinnreihe anhaken, Karte wird gefunden.

Fälle: eine Gewinnerkarte; zwei Karten mit erreichtem Ziel (beide angeboten); „falsches Bingo“
(angehakte Songs stehen auf der Karte, Ziel aber nicht erreicht → kein Gewinner).
"""
from common import GLib, Gtk, check, forbid_network, patch_dialogs, pump, run

forbid_network()
patch_dialogs()
SEEN = {}


def collect(root, kind):
    found = []

    def walk(widget):
        if isinstance(widget, kind):
            found.append(widget)
        if isinstance(widget, Gtk.Container):
            widget.foreach(walk)
    walk(root)
    return found


def open_dialog(title):
    return next((top for top in Gtk.Window.list_toplevels()
                 if isinstance(top, Gtk.Dialog) and top.get_visible() and top.get_title() == title), None)


def combo_entries(combo) -> dict[str, str]:
    """Kartennummer → angezeigter Text (ComboBoxText: Spalte 0 Text, Spalte 1 ID)."""
    return {row[1]: row[0] for row in combo.get_model()}


def find_by_songs(w, songs, choose, seen) -> None:
    """„Ohne Kartennummer prüfen“ bedienen: Songs anhaken, Angebot merken, Karte `choose` wählen."""
    def operate() -> bool:
        dialog = open_dialog("Ohne Kartennummer prüfen")
        if dialog is None:
            return True
        boxes = {box.get_label(): box for box in collect(dialog, Gtk.CheckButton)}
        for song in songs:
            boxes[song.display_name].set_active(True)
        combo = collect(dialog, Gtk.ComboBoxText)[0]
        seen["entries"] = combo_entries(combo)
        seen["active"] = combo.get_active_id()
        seen["chosen"] = combo.set_active_id(str(choose))
        dialog.response(Gtk.ResponseType.OK)
        return False
    GLib.timeout_add(400, operate)
    w._verify_bingo(None)
    pump(0.3)


def scenario(w):
    from musik_bingo.domain.card_generator import winning_lines
    from musik_bingo.presentation import dialogs

    from musik_bingo.domain.forecast import card_status

    w.song_buffer.set_text("\n".join(f"Song {i:02d} – Interpret {i}" for i in range(40)))
    w.size_combo.set_active(2)  # 5×5
    w.count_spin.set_value(160)
    for _attempt in range(50):
        w._generate(None)
        game = w.service.game
        target = game.cards[41]  # Karte #42
        line = target.songs[:5]  # erste Reihe (Freifeld liegt in der Mitte)
        # Mittlere Reihe/Spalte brauchen wegen des Freifelds nur 4 Songs: In rund 2 % der zufälligen Kartensätze
        # erreicht eine zweite Karte mit denselben 5 Songs „1 Reihe“ – dann stimmen die Erwartungen unten nicht.
        if not any(card_status(card, 5, True, line)[0] for number, card in enumerate(game.cards, start=1) if number != 42):
            break
    for song in line:
        game.caller.draw_song(song)
    w._render_caller()
    check("Karte #42 hat das Ziel erreicht", w.service.check_win(42)[0])

    dialogs.bingo_check_dialog = lambda parent, count, rule: (dialogs.WITHOUT_NUMBER, "Anna")
    result = {}

    def result_dialog(parent, card, number, name, *args, **kwargs):
        result.update(number=number, name=name, reached=args[-2] if len(args) >= 2 else None)
        return True  # „Als Gewinner eintragen“
    original_result_dialog = dialogs.bingo_result_dialog
    dialogs.bingo_result_dialog = result_dialog

    def operate() -> bool:
        dialog = next((top for top in Gtk.Window.list_toplevels()
                       if isinstance(top, Gtk.Dialog) and top.get_visible()
                       and top.get_title() == "Ohne Kartennummer prüfen"), None)
        if dialog is None:
            return True
        boxes = []

        def collect(widget):
            if isinstance(widget, Gtk.CheckButton):
                boxes.append(widget)
            elif isinstance(widget, Gtk.Container):
                widget.foreach(collect)
        collect(dialog)
        combos = []

        def collect_combo(widget):
            if isinstance(widget, Gtk.ComboBoxText):
                combos.append(widget)
            elif isinstance(widget, Gtk.Container):
                widget.foreach(collect_combo)
        collect_combo(dialog)
        SEEN["songs"] = len(boxes)
        names = {song.display_name for song in line}
        boxes_by_name = {box.get_label(): box for box in boxes}
        boxes_by_name[line[0].display_name].set_active(True)
        # Ein Song steht auf vielen Karten – vorgeschlagen werden nur die mit erreichtem Ziel
        SEEN["after_one"] = combos[0].get_active_id()
        for name in names:
            boxes_by_name[name].set_active(True)
        SEEN["combo_visible"] = combos[0].get_visible()
        SEEN["active"] = combos[0].get_active_id()
        not_played = next(box for name, box in boxes_by_name.items()
                          if name not in {s.display_name for s in game.caller.drawn})
        not_played.set_active(True)
        labels = []

        def collect_labels(widget):
            if isinstance(widget, Gtk.Label):
                labels.append(widget.get_text())
            elif isinstance(widget, Gtk.Container):
                widget.foreach(collect_labels)
        collect_labels(dialog)
        SEEN["with_unplayed"] = any("noch NICHT gespielt" in text for text in labels)
        not_played.set_active(False)
        dialog.response(Gtk.ResponseType.OK)
        return False

    GLib.timeout_add(400, operate)
    w._verify_bingo(None)
    pump(0.3)
    check("alle 40 Songs zur Auswahl", SEEN.get("songs") == 40)
    check("ein Song: nur die Karte mit erreichtem Ziel vorgeschlagen", SEEN.get("after_one") == "42")
    check("ganze Reihe angehakt → Karte vorgeschlagen", SEEN.get("combo_visible") is True)
    check("vorgeschlagen ist Karte #42", SEEN.get("active") == "42")
    check("noch nicht gespielter Song wird deutlich gemeldet", SEEN.get("with_unplayed") is True)
    check("Ergebnis zeigt Karte #42 mit Name", result.get("number") == 42 and result.get("name") == "Anna")
    check("als Gewinner eingetragen", [x.card for x in w.service.winners] == [42])
    check("Gewinnlinie stimmt", bool(winning_lines(target, 5, True, game.caller.drawn, game.diagonal_wins)))

    # Zwei Karten erreichen das Ziel mit denselben Songs: beide werden angeboten (mit „erreicht ✓“)
    from musik_bingo.domain.card_generator import cards_containing
    from musik_bingo.domain.models import BingoCard
    game.cards[6] = BingoCard(list(line) + list(reversed(target.songs[5:])))  # Karte #7: gleiche erste Reihe
    check("Karte #7 hat das Ziel ebenfalls erreicht", w.service.check_win(7)[0])
    expected = {str(n) for n in cards_containing(game.cards, line) if w.service.check_win(n)[0]}
    check("genau Karte #7 und #42 mit erreichtem Ziel", expected == {"7", "42"})
    two = {}
    result.clear()
    find_by_songs(w, line, 7, two)
    entries = two.get("entries", {})
    reached_offered = {number for number, text in entries.items() if text.endswith("Gewinnziel erreicht ✓")}
    print("Angebot zwei Karten:", entries)
    check("zwei Karten: beide angeboten mit „Gewinnziel erreicht ✓“", reached_offered == {"7", "42"})
    check("zwei Karten: Text nennt die Karte", entries.get("7") == "Karte #7 – Gewinnziel erreicht ✓"
          and entries.get("42") == "Karte #42 – Gewinnziel erreicht ✓")
    check("zwei Karten: Karten mit erreichtem Ziel stehen vorn", list(entries)[:2] == ["7", "42"]
          and two.get("active") == "7")
    check("zwei Karten: Karte #7 wählbar und geprüft", two.get("chosen") is True and result.get("number") == 7
          and result.get("reached") is True)
    check("zwei Karten: #7 zusätzlich eingetragen", [x.card for x in w.service.winners] == [42, 7])

    # „Falsches Bingo“: angehakte Songs stehen auf der Karte, das Ziel ist aber nicht erreicht
    dialogs.bingo_result_dialog = original_result_dialog
    wrong = next(n for n in range(1, len(game.cards) + 1)
                 if n not in (7, 42) and not w.service.check_win(n)[0]
                 and any(s.key not in {d.key for d in game.caller.drawn} for s in game.cards[n - 1].songs[:5]))
    # Erste zwei Reihen: Fünf Songs stehen bei 40 Songs auf rund zehn Karten (dann „weitere Songs anhaken“)
    wrong_songs = game.cards[wrong - 1].songs[:10]
    false_bingo = {}

    def close_result() -> bool:
        dialog = open_dialog("Noch kein Bingo")
        if dialog is None:
            return "result" not in false_bingo and open_dialog("BINGO bestätigt!") is None
        false_bingo["result"] = True
        false_bingo["buttons"] = [b.get_label() for b in collect(dialog, Gtk.Button)]
        false_bingo["labels"] = [lbl.get_text() for lbl in collect(dialog, Gtk.Label)]
        dialog.response(Gtk.ResponseType.OK)  # selbst „OK“ (Enter) darf nichts eintragen
        return False
    GLib.timeout_add(900, close_result)
    find_by_songs(w, wrong_songs, wrong, false_bingo)
    print("Angebot falsches Bingo:", false_bingo.get("entries"))
    check("falsches Bingo: Karte angeboten, ohne „erreicht ✓“",
          false_bingo.get("chosen") is True
          and false_bingo.get("entries", {}).get(str(wrong)) == f"Karte #{wrong}")
    check("falsches Bingo: Ergebnis „Noch kein Bingo“", false_bingo.get("result") is True)
    check("falsches Bingo: Dialog meldet Ziel nicht erreicht",
          any("noch nicht erreicht" in text for text in false_bingo.get("labels", [])))
    check("falsches Bingo: kein „Als Gewinner eintragen“",
          "buttons" in false_bingo and "Als Gewinner eintragen" not in false_bingo["buttons"])
    check("falsches Bingo: kein Gewinner eingetragen", [x.card for x in w.service.winners] == [42, 7])


run(scenario)
