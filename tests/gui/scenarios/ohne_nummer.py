"""E2E: Bingo prüfen ohne Kartennummer – Songs der Gewinnreihe anhaken, Karte wird gefunden."""
from common import GLib, Gtk, check, patch_dialogs, pump, run

patch_dialogs()
SEEN = {}


def scenario(w):
    from musik_bingo.domain.card_generator import winning_lines
    from musik_bingo.presentation import dialogs

    w.song_buffer.set_text("\n".join(f"Song {i:02d} – Interpret {i}" for i in range(40)))
    w.size_combo.set_active(2)  # 5×5
    w.count_spin.set_value(160)
    w._generate(None)
    game = w.service.game
    target = game.cards[41]  # Karte #42
    line = target.songs[:5]  # erste Reihe (Freifeld liegt in der Mitte)
    for song in line:
        game.caller.draw_song(song)
    w._render_caller()
    check("Karte #42 hat das Ziel erreicht", w.service.check_win(42)[0])

    dialogs.bingo_check_dialog = lambda parent, count, rule: (dialogs.WITHOUT_NUMBER, "Anna")
    result = {}

    def result_dialog(parent, card, number, name, *args, **kwargs):
        result.update(number=number, name=name, reached=args[-2] if len(args) >= 2 else None)
        return True  # „Als Gewinner eintragen“
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


run(scenario)
