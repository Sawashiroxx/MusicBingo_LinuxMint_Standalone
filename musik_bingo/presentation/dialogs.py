"""Dialoge der Oberfläche: Import, Zufallsmix, Abgleich, Bingo-Ergebnis."""
from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from musik_bingo.domain.catalog import Catalog, MixResult, random_mix, unique_songs
from musik_bingo.domain.models import BingoCard, Song
from musik_bingo.domain.playlist import (
    ORDER_ARTIST_TITLE,
    ORDER_AUTO,
    ORDER_TITLE_ARTIST,
    ImportResult,
    parse_playlist,
)

MAX_FILE_BYTES = 5 * 1024 * 1024
MODE_REPLACE = "replace"
MODE_APPEND = "append"


def escape(text: str) -> str:
    return GLib.markup_escape_text(text)


def add_class(widget: Gtk.Widget, *names: str) -> Gtk.Widget:
    context = widget.get_style_context()
    for name in names:
        context.add_class(name)
    return widget


def label(text: str = "", *classes: str, wrap: bool = False, xalign: float = 0.0, markup: bool = False) -> Gtk.Label:
    widget = Gtk.Label()
    if markup:
        widget.set_markup(text)
    else:
        widget.set_text(text)
    widget.set_xalign(xalign)
    if wrap:
        widget.set_line_wrap(True)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    add_class(widget, *classes)
    return widget


def field(title: str, widget: Gtk.Widget, hint: str = "") -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(label(f"<b>{escape(title)}</b>", markup=True), False, False, 0)
    box.pack_start(widget, False, False, 0)
    if hint:
        box.pack_start(label(hint, "muted", "small", wrap=True), False, False, 0)
    return box


def read_text_file(path: Path) -> str:
    """Liest Text robust (UTF-8 mit/ohne BOM, sonst Latin-1), höchstens 5 MB."""
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Die Datei ist größer als 5 MB und wird nicht eingelesen.")
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def base_dialog(parent: Gtk.Window, title: str, ok_label: str | None = "Übernehmen",
                width: int = 560) -> tuple[Gtk.Dialog, Gtk.Box, Gtk.Widget | None]:
    dialog = Gtk.Dialog(title=title, transient_for=parent, modal=True, use_header_bar=True)
    dialog.set_default_size(width, -1)
    dialog.add_button("Abbrechen" if ok_label else "Schließen", Gtk.ResponseType.CANCEL)
    ok = None
    if ok_label:
        ok = dialog.add_button(ok_label, Gtk.ResponseType.OK)
        add_class(ok, "primary")
        dialog.set_default_response(Gtk.ResponseType.OK)
    content = dialog.get_content_area()
    content.set_spacing(14)
    content.set_border_width(20)
    return dialog, content, ok


def message(parent: Gtk.Window, kind: Gtk.MessageType, title: str, detail: str) -> None:
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=kind,
                               buttons=Gtk.ButtonsType.OK, text=title)
    dialog.format_secondary_text(detail)
    dialog.run()
    dialog.destroy()


def confirm(parent: Gtk.Window, title: str, detail: str, ok_label: str = "Fortfahren") -> bool:
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.QUESTION,
                               buttons=Gtk.ButtonsType.CANCEL, text=title)
    dialog.format_secondary_text(detail)
    dialog.add_button(ok_label, Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    result = dialog.run()
    dialog.destroy()
    return result == Gtk.ResponseType.OK


def mode_selector(default_append: bool = False) -> tuple[Gtk.Box, Gtk.RadioButton]:
    box = Gtk.Box(spacing=16)
    replace = Gtk.RadioButton.new_with_label(None, "Songliste ersetzen")
    append = Gtk.RadioButton.new_with_label_from_widget(replace, "An Songliste anhängen")
    append.set_active(default_append)
    box.pack_start(replace, False, False, 0)
    box.pack_start(append, False, False, 0)
    return box, append


# ------------------------------------------------------------ Playlist-Import


def import_playlist_dialog(parent: Gtk.Window) -> tuple[ImportResult, str] | None:
    dialog, content, ok = base_dialog(parent, "Playlist importieren", "Importieren", 640)
    content.pack_start(label(
        "Am zuverlässigsten: Playlist in Spotify anlegen, als CSV exportieren (z. B. mit Exportify) "
        "und hier einlesen. Dann stehen auf den Karten genau die Titel der Playlist, inklusive "
        "Spotify-Links für die direkte Wiedergabe. YouTube-Titel kannst du einfach kopieren und einfügen.",
        "muted", wrap=True), False, False, 0)

    switcher = Gtk.StackSwitcher()
    stack = Gtk.Stack()
    stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    stack.set_vhomogeneous(False)
    switcher.set_stack(stack)
    switcher.set_halign(Gtk.Align.START)
    content.pack_start(switcher, False, False, 0)

    file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    chooser = Gtk.FileChooserButton(title="Playlist-Datei wählen", action=Gtk.FileChooserAction.OPEN)
    playlist_filter = Gtk.FileFilter()
    playlist_filter.set_name("Playlists (CSV, M3U, Text)")
    for pattern in ("*.csv", "*.tsv", "*.m3u", "*.m3u8", "*.txt", "*.CSV", "*.M3U", "*.TXT"):
        playlist_filter.add_pattern(pattern)
    chooser.add_filter(playlist_filter)
    all_filter = Gtk.FileFilter()
    all_filter.set_name("Alle Dateien")
    all_filter.add_pattern("*")
    chooser.add_filter(all_filter)
    file_box.pack_start(field("Datei", chooser,
                              "CSV mit Spalten wie „Track Name“, „Artist Name(s)“, „Track URI“ · M3U/M3U8 · "
                              "Textdatei mit einem Song pro Zeile"), False, False, 0)
    stack.add_titled(file_box, "file", "Datei")

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    text_view = Gtk.TextView()
    text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    for setter in (text_view.set_left_margin, text_view.set_right_margin, text_view.set_top_margin):
        setter(8)
    scroll = Gtk.ScrolledWindow()
    scroll.set_min_content_height(200)
    scroll.add(text_view)
    add_class(scroll, "editor")
    text_box.pack_start(label("Ein Song pro Zeile, z. B. „Wham! - Last Christmas (Official Video)“. "
                              "YouTube-/Spotify-Links in der Zeile werden übernommen.", "muted", "small", wrap=True),
                        False, False, 0)
    text_box.pack_start(scroll, True, True, 0)
    stack.add_titled(text_box, "text", "Text einfügen")
    content.pack_start(stack, False, False, 0)

    order = Gtk.ComboBoxText()
    order.append(ORDER_AUTO, "Automatisch („Titel – Interpret“ bzw. „Interpret - Titel“)")
    order.append(ORDER_ARTIST_TITLE, "Interpret - Titel (YouTube, die meisten Exporte)")
    order.append(ORDER_TITLE_ARTIST, "Titel - Interpret")
    order.set_active_id(ORDER_AUTO)
    content.pack_start(field("Reihenfolge in Textzeilen", order,
                             "Gilt nicht für CSV-Dateien mit Spaltenüberschriften."), False, False, 0)
    mode_box, append = mode_selector()
    content.pack_start(mode_box, False, False, 0)
    preview = label("Noch nichts ausgewählt.", "muted", wrap=True)
    content.pack_start(preview, False, False, 0)
    ok.set_sensitive(False)
    state: dict = {"result": None}

    def update(*_args) -> None:
        state["result"] = None
        try:
            if stack.get_visible_child_name() == "file":
                filename = chooser.get_filename()
                if not filename:
                    preview.set_text("Noch keine Datei ausgewählt.")
                    ok.set_sensitive(False)
                    return
                result = parse_playlist(read_text_file(Path(filename)), filename, order.get_active_id())
            else:
                buffer = text_view.get_buffer()
                text = buffer.get_text(*buffer.get_bounds(), True)
                result = parse_playlist(text, "", order.get_active_id())
        except Exception as error:  # noqa: BLE001 – jede kaputte Datei sauber melden
            preview.set_text(f"⚠ {error}")
            ok.set_sensitive(False)
            return
        state["result"] = result
        parts = [f"{len(result.songs)} Songs erkannt"]
        linked = sum(1 for song in result.songs if song.link)
        if linked:
            parts.append(f"{linked} mit Spotify-/YouTube-Link")
        if result.duplicates:
            parts.append(f"{result.duplicates} doppelt")
        if result.skipped:
            parts.append(f"{len(result.skipped)} übersprungen")
        sample = ", ".join(song.display_name for song in result.songs[:3])
        preview.set_text(" · ".join(parts) + (f"\nz. B.: {sample}" if sample else ""))
        ok.set_sensitive(bool(result.songs))

    chooser.connect("file-set", update)
    text_view.get_buffer().connect("changed", update)
    order.connect("changed", update)
    stack.connect("notify::visible-child", update)
    dialog.show_all()
    response = dialog.run()
    result = state["result"]
    mode = MODE_APPEND if append.get_active() else MODE_REPLACE
    dialog.destroy()
    if response != Gtk.ResponseType.OK or result is None or not result.songs:
        return None
    return result, mode


# ------------------------------------------------------------ Zufallsmix


def mix_dialog(parent: Gtk.Window, catalogs: list[Catalog]) -> tuple[MixResult, str] | None:
    dialog, content, ok = base_dialog(parent, "Zufallsmix: Charts & Weihnachten", "Mix erstellen", 600)
    content.pack_start(label(
        "Stellt eine zufällige Songliste aus den mitgelieferten Listen zusammen (offline gespeichert, "
        "Stand der Charts: KW 47/2026). Danach die Liste als Playlist exportieren und in "
        "Spotify/YouTube anlegen, damit Musik und Karten übereinstimmen.", "muted", wrap=True), False, False, 0)

    total = Gtk.SpinButton.new_with_range(9, 500, 1)
    total.set_value(75)
    content.pack_start(field("Anzahl Songs", total, "Faustregel 5×5: ca. 1 Song pro Minute, volle Karte nach "
                                                   "≈ 85 % der Songs. 75 Songs ≈ 1 Stunde."), False, False, 0)
    share = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
    share.set_value(40)
    share.set_value_pos(Gtk.PositionType.RIGHT)
    share.set_digits(0)
    share.connect("format-value", lambda _scale, value: f"{int(value)} % Weihnachten")
    content.pack_start(field("Verhältnis", share, "0 % = nur Charts · 100 % = nur Weihnachtslieder"), False, False, 0)

    lists = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24, homogeneous=True)
    checks: list[tuple[Gtk.CheckButton, Catalog]] = []
    for category, title in (("weihnachten", "Weihnachten"), ("charts", "Charts")):
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        column.pack_start(label(f"<b>{title}</b>", markup=True), False, False, 0)
        for catalog in catalogs:
            if catalog.category != category:
                continue
            check = Gtk.CheckButton(label=f"{catalog.name} ({len(catalog.songs)})")
            check.set_active(True)
            check.set_tooltip_text(catalog.source)
            column.pack_start(check, False, False, 0)
            checks.append((check, catalog))
        lists.pack_start(column, True, True, 0)
    content.pack_start(lists, False, False, 0)
    mode_box, append = mode_selector()
    content.pack_start(mode_box, False, False, 0)
    info = label("", "muted", wrap=True)
    content.pack_start(info, False, False, 0)

    def pools() -> tuple[list[Song], list[Song]]:
        chosen = [catalog for check, catalog in checks if check.get_active()]
        return (unique_songs([c for c in chosen if c.category == "weihnachten"]),
                unique_songs([c for c in chosen if c.category == "charts"]))

    def update(*_args) -> None:
        xmas, charts = pools()
        info.set_text(f"Verfügbar: {len(xmas)} Weihnachtslieder · {len(charts)} Chart-Hits (Doppelte zusammengefasst)")
        ok.set_sensitive(bool(xmas or charts))

    for check, _catalog in checks:
        check.connect("toggled", update)
    update()
    dialog.show_all()
    response = dialog.run()
    result = None
    if response == Gtk.ResponseType.OK:
        xmas, charts = pools()
        result = random_mix(xmas, charts, total.get_value_as_int(), int(share.get_value()))
    mode = MODE_APPEND if append.get_active() else MODE_REPLACE
    dialog.destroy()
    if result is None or not result.songs:
        return None
    return result, mode


# ------------------------------------------------------------ Listen-Anzeige


def list_dialog(parent: Gtk.Window, title: str, intro: str, sections: list[tuple[str, list[str]]]) -> None:
    dialog, content, _ok = base_dialog(parent, title, None, 620)
    content.pack_start(label(intro, wrap=True), False, False, 0)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for heading, items in sections:
        box.pack_start(label(f"<b>{escape(heading)}</b> ({len(items)})", markup=True), False, False, 0)
        if not items:
            box.pack_start(label("– keine –", "muted"), False, False, 0)
        for item in items[:400]:
            box.pack_start(label(f"• {item}", wrap=True), False, False, 0)
        if len(items) > 400:
            box.pack_start(label(f"… und {len(items) - 400} weitere", "muted"), False, False, 0)
    scroll = Gtk.ScrolledWindow()
    scroll.set_min_content_height(320)
    scroll.add(box)
    content.pack_start(scroll, True, True, 0)
    dialog.show_all()
    dialog.run()
    dialog.destroy()


# ------------------------------------------------------------ Bingo-Prüfung


def bingo_check_dialog(parent: Gtk.Window, card_count: int, rule: str) -> tuple[int, str] | None:
    dialog, content, _ok = base_dialog(parent, "Bingo prüfen", "Prüfen", 420)
    content.pack_start(label("Nummer der gedruckten Karte eingeben. Geprüft werden nur bereits gezogene Songs.",
                             wrap=True), False, False, 0)
    number = Gtk.SpinButton.new_with_range(1, max(1, card_count), 1)
    number.set_activates_default(True)
    content.pack_start(field("Kartennummer", number), False, False, 0)
    name = Gtk.Entry()
    name.set_placeholder_text("optional")
    name.set_activates_default(True)
    content.pack_start(field("Name", name), False, False, 0)
    content.pack_start(label(f"Gewinnregel dieser Runde: {rule}.", "muted", "small", wrap=True), False, False, 0)
    dialog.show_all()
    number.grab_focus()
    response = dialog.run()
    number.update()
    result = (number.get_value_as_int(), name.get_text().strip())
    dialog.destroy()
    return result if response == Gtk.ResponseType.OK else None


def bingo_result_dialog(parent: Gtk.Window, card: BingoCard, number: int, name: str, size: int,
                        free_space: bool, drawn_keys: set[str], wins: list[str],
                        winning_cells: set[int], target_label: str = "", reached: bool | None = None,
                        full: bool = False) -> None:
    if reached is None:  # ohne Gewinnziel: jede volle Linie zählt
        reached = bool(wins)
        target_label = target_label or "1 Reihe"
    title = "BINGO bestätigt!" if reached else "Noch kein Bingo"
    dialog, content, _ok = base_dialog(parent, title, None, 640)
    who = f"Karte #{number}" + (f" · {name}" if name else "")
    headline = label(f"<span size='x-large' weight='heavy'>{escape(who)}</span>", markup=True)
    content.pack_start(headline, False, False, 0)
    done = ("Volle Karte!" if full else "") or (("Vollständig: " + ", ".join(wins)) if wins else "")
    if reached:
        box = add_class(Gtk.Box(), "info-box")
        box.pack_start(label(f"Gewinnziel „{target_label}“ erreicht. {done}", wrap=True), True, True, 0)
    else:
        box = add_class(Gtk.Box(), "warning-box")
        detail = done or "Noch keine Reihe/Spalte vollständig gezogen."
        box.pack_start(label(f"Gewinnziel „{target_label}“ noch nicht erreicht. {detail}", wrap=True),
                       True, True, 0)
    content.pack_start(box, False, False, 0)
    grid = Gtk.Grid(column_spacing=4, row_spacing=4, column_homogeneous=True, row_homogeneous=True)
    frame = add_class(Gtk.Box(), "bingo-card")
    frame.pack_start(grid, True, True, 0)
    free = free_space and size % 2 == 1
    songs = iter(card.songs)
    hits = 0
    for index in range(size * size):
        is_free = free and index == size * size // 2
        text = "★ FREI" if is_free else next(songs).display_name
        cell = label(text, "cell", wrap=True, xalign=0.5)
        cell.set_justify(Gtk.Justification.CENTER)
        cell.set_size_request(96, 52)
        cell.set_max_width_chars(14)
        if is_free:
            add_class(cell, "cell-free")
        elif text.casefold() in drawn_keys:
            hits += 1
            add_class(cell, "cell-line" if index in winning_cells else "cell-hit")
        grid.attach(cell, index % size, index // size, 1, 1)
    content.pack_start(frame, False, False, 0)
    content.pack_start(label(f"{hits} gezogene Songs auf dieser Karte · grün = gezogen · gold = Gewinnlinie",
                             "muted", "small"), False, False, 0)
    dialog.show_all()
    dialog.run()
    dialog.destroy()
