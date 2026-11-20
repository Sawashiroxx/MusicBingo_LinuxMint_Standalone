"""Dialoge der Oberfläche: Import, Zufallsmix, Abgleich, Bingo-Ergebnis, Spotify-Links."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from musik_bingo.domain.catalog import Catalog, MixResult, random_mix, unique_songs
from musik_bingo.domain.link_coverage import LinkCoverage, link_coverage
from musik_bingo.domain.links import is_spotify, parse_user_link
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
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # Excel „Unicode-Text“
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Windows-Dateien („ANSI“): cp1252 kennt – ’ „ “ …; Latin-1 machte daraus Steuerzeichen
        return data.decode("cp1252", errors="replace")


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


RESPONSE_WITHOUT_NUMBER = 1
WITHOUT_NUMBER = 0  # Rückgabe statt Kartennummer: „Ohne Kartennummer prüfen“ gewählt
MAX_LISTED_CARDS = 8


def bingo_check_dialog(parent: Gtk.Window, card_count: int, rule: str) -> tuple[int, str] | None:
    """Rückgabe (Kartennummer, Name); Kartennummer WITHOUT_NUMBER = Prüfung über die Songs."""
    dialog, content, _ok = base_dialog(parent, "Bingo prüfen", "Prüfen", 420)
    dialog.add_button("Ohne Kartennummer …", RESPONSE_WITHOUT_NUMBER)
    content.pack_start(label("Nummer der gedruckten Karte eingeben. Geprüft werden nur bereits gezogene Songs.",
                             wrap=True), False, False, 0)
    # Bereich bewusst größer als die Kartenzahl: Der SpinButton kappt Eingaben sonst still auf den Bereich –
    # „1600“ würde als Karte 160 geprüft, ein leeres Feld als Karte 1. So meldet die Prüfung „Ungültige Kartennummer“.
    number = Gtk.SpinButton.new_with_range(0, 99999, 1)
    number.set_value(1)
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
    # 0 = leeres/ungültiges Feld → -1, damit der Aufrufer „Ungültige Kartennummer“ meldet (0 heißt „ohne Nummer“)
    result = (number.get_value_as_int() or -1, name.get_text().strip())
    dialog.destroy()
    if response == RESPONSE_WITHOUT_NUMBER:
        return WITHOUT_NUMBER, result[1]
    return result if response == Gtk.ResponseType.OK else None


def find_card_dialog(parent: Gtk.Window, songs: list[Song], drawn_keys: set[str],
                     find: Callable[[list[Song]], list[tuple[int, bool]]]) -> int | None:
    """Prüfen ohne Kartennummer: Songs der Gewinnreihe anhaken → passende Karte finden.

    ``find(ausgewählte Songs)`` liefert [(Kartennummer, Ziel erreicht)]. Rückgabe: gewählte Karte.
    """
    dialog, content, ok = base_dialog(parent, "Ohne Kartennummer prüfen", "Karte anzeigen", 620)
    ok.set_sensitive(False)
    content.pack_start(label(
        "Lass dir die Songs der Gewinnreihe vorlesen und hake sie hier an. Die App zeigt sofort, "
        "ob sie schon gespielt wurden, und sucht die passende Karte.", wrap=True), False, False, 0)
    search = Gtk.SearchEntry()
    search.set_placeholder_text("Song oder Interpret suchen …")
    content.pack_start(search, False, False, 0)
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_min_content_height(300)
    rows = Gtk.ListBox()
    rows.set_selection_mode(Gtk.SelectionMode.NONE)
    scroller.add(rows)
    content.pack_start(scroller, True, True, 0)
    status = label("", wrap=True)
    content.pack_start(status, False, False, 0)
    cards = Gtk.ComboBoxText()
    cards.set_no_show_all(True)
    content.pack_start(cards, False, False, 0)
    checks: list[tuple[Gtk.CheckButton, Song]] = []

    def selected() -> list[Song]:
        return [song for check, song in checks if check.get_active()]

    def update(*_args) -> None:
        chosen = selected()
        cards.remove_all()
        cards.hide()
        ok.set_sensitive(False)
        if not chosen:
            status.set_text("Noch nichts angehakt.")
            return
        missing = [song.display_name for song in chosen if song.key not in drawn_keys]
        parts = [f"{len(chosen)} angehakt · "
                 + ("alle schon gespielt ✓" if not missing else "noch NICHT gespielt: " + ", ".join(missing))]
        matches = find(chosen)
        if len(matches) > MAX_LISTED_CARDS:
            # Viele Karten enthalten die Songs – wer „Bingo“ ruft, muss das Ziel aber erreicht haben
            winners = [item for item in matches if item[1]]
            if 0 < len(winners) <= MAX_LISTED_CARDS:
                parts.append(f"{len(matches)} Karten enthalten diese Songs, {len(winners)} davon mit "
                             "erreichtem Gewinnziel.")
                matches = winners
        if not matches:
            parts.append("Keine Karte enthält alle angehakten Songs – bitte die Auswahl prüfen.")
        elif len(matches) > MAX_LISTED_CARDS:
            parts.append(f"{len(matches)} Karten passen – weitere Songs der Reihe anhaken.")
        else:
            matches = sorted(matches, key=lambda item: (not item[1], item[0]))
            for number, reached in matches:
                cards.append(str(number), f"Karte #{number}" + (" – Gewinnziel erreicht ✓" if reached else ""))
            cards.set_active(0)
            cards.show()
            ok.set_sensitive(True)
            parts.append("Passende Karte gefunden." if len(matches) == 1
                         else f"{len(matches)} Karten passen – bitte die richtige wählen.")
        status.set_text(" ".join(parts))

    # Gespielte Songs zuerst – nur sie können in einer Gewinnreihe stehen
    for song in sorted(songs, key=lambda item: (item.key not in drawn_keys, item.display_name.casefold())):
        row = Gtk.Box(spacing=10)
        check = Gtk.CheckButton(label=song.display_name)
        check.connect("toggled", update)
        row.pack_start(check, True, True, 0)
        played = song.key in drawn_keys
        row.pack_end(label("gespielt ✓" if played else "noch nicht", "small", "muted" if played else "warning-text"),
                     False, False, 0)
        rows.add(row)
        checks.append((check, song))

    def visible(row) -> bool:
        text = search.get_text().strip().casefold()
        return not text or text in checks[row.get_index()][1].display_name.casefold()

    rows.set_filter_func(visible)
    search.connect("search-changed", lambda *_: rows.invalidate_filter())
    update()
    dialog.set_default_size(620, 560)
    dialog.show_all()
    search.grab_focus()
    response = dialog.run()
    number = cards.get_active_id()
    dialog.destroy()
    return int(number) if response == Gtk.ResponseType.OK and number else None


def bingo_result_dialog(parent: Gtk.Window, card: BingoCard, number: int, name: str, size: int,
                        free_space: bool, drawn_keys: set[str], wins: list[str],
                        winning_cells: set[int], target_label: str = "", reached: bool | None = None,
                        full: bool = False) -> bool:
    """Zeigt die geprüfte Karte. Rückgabe True = „Als Gewinner eintragen“ gewählt."""
    if reached is None:  # ohne Gewinnziel: jede volle Linie zählt
        reached = bool(wins)
        target_label = target_label or "1 Reihe"
    title = "BINGO bestätigt!" if reached else "Noch kein Bingo"
    dialog, content, _ok = base_dialog(parent, title, None, 640)
    if reached:
        register = dialog.add_button("Als Gewinner eintragen", Gtk.ResponseType.OK)
        add_class(register, "primary")
        dialog.set_default_response(Gtk.ResponseType.OK)
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
        cell = label(text, "bingo-cell", wrap=True, xalign=0.5)
        cell.set_justify(Gtk.Justification.CENTER)
        cell.set_size_request(96, 52)
        cell.set_max_width_chars(14)
        cell.set_lines(4)  # ein überlanger Titel macht sonst alle Reihen hoch → Dialog höher als 768 px
        cell.set_ellipsize(Pango.EllipsizeMode.END)
        cell.set_tooltip_text(text)
        if is_free:
            add_class(cell, "bingo-cell-free")
        elif text.casefold() in drawn_keys:
            hits += 1
            add_class(cell, "bingo-cell-line" if index in winning_cells else "bingo-cell-hit")
        grid.attach(cell, index % size, index // size, 1, 1)
    content.pack_start(frame, False, False, 0)
    content.pack_start(label(f"{hits} gezogene Songs auf dieser Karte · grün = gezogen · gold = Gewinnlinie",
                             "muted", "small"), False, False, 0)
    dialog.show_all()
    response = dialog.run()
    dialog.destroy()
    return bool(reached) and response == Gtk.ResponseType.OK


# ------------------------------------------------------------ Spotify-Links nachtragen


LINK_HINT = ("Spotify-Link bekommst du in Spotify per Rechtsklick auf den Titel → Teilen → Songlink kopieren. "
             "Schneller für viele Songs: Playlist in Spotify abspielen → ‚Vom Player einlesen‘ → "
             "‚Mit Playlist abgleichen‘.")


def coverage_text(coverage: LinkCoverage) -> str:
    if coverage.complete:
        return f"✓ Spotify: alle {coverage.total} Songs direkt abspielbar"
    return f"Spotify: {coverage.spotify} von {coverage.total} Songs direkt abspielbar"


def link_status(value: str) -> tuple[str, bool]:
    """(Anzeigetext, gültig?) für ein Link-Eingabefeld."""
    try:
        link = parse_user_link(value)
    except ValueError as error:
        return f"⚠ {error}", False
    if is_spotify(link):
        return "✓ Spotify-Titel – wird direkt abgespielt", True
    if link:
        return "✓ YouTube-Video – für Spotify fehlt noch der Link", True
    return "Kein Link – Spotify sucht nach Titel und Interpret", True


def spotify_links_dialog(parent: Gtk.Window, songs: list[Song], source: str) -> dict[str, str] | None:
    """Links pro Song einfügen. Rückgabe: geänderte Links (Song.key → Link, "" = entfernen)."""
    dialog, content, ok = base_dialog(parent, "Spotify-Links", "Übernehmen", 720)
    coverage = link_coverage(songs)
    headline = label("", "panel-title", wrap=True)
    content.pack_start(headline, False, False, 0)
    content.pack_start(label(LINK_HINT, "muted", wrap=True), False, False, 0)
    search = Gtk.SearchEntry()
    search.set_placeholder_text("Song oder Interpret suchen …")
    content.pack_start(search, False, False, 0)
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_min_content_height(360)
    rows = Gtk.ListBox()
    rows.set_selection_mode(Gtk.SelectionMode.NONE)
    scroller.add(rows)
    content.pack_start(scroller, True, True, 0)
    status = label("", "small", wrap=True)
    content.pack_start(status, False, False, 0)
    missing_keys = {song.key for song in coverage.missing_spotify}
    unique: dict[str, Song] = {}
    for song in songs:
        unique.setdefault(song.key, song)
    # Songs ohne Spotify-Link zuerst, sonst Reihenfolge der Liste
    ordered = sorted(unique.values(), key=lambda song: song.key not in missing_keys)
    entries: list[tuple[Gtk.Entry, Song, Gtk.Label]] = []

    def update(*_args) -> None:
        errors = 0
        changes = 0
        spotify = 0
        for entry, song, hint in entries:
            text, valid = link_status(entry.get_text())
            hint.set_text(text)
            hint_context = hint.get_style_context()
            for name in ("ok-text", "warning-text", "muted"):
                hint_context.remove_class(name)
            hint_context.add_class("warning-text" if not valid else "ok-text" if text.startswith("✓ Spotify")
                                   else "muted")
            if not valid:
                errors += 1
                continue
            link = parse_user_link(entry.get_text())
            spotify += is_spotify(link)
            changes += link != song.link
        text = f"{coverage_text(coverage)} ({source})"
        if changes and not errors:
            text += f"\nNach „Übernehmen“: {spotify} von {len(entries)}"
        headline.set_text(text)
        parts = [f"{changes} Änderung(en)" if changes else "Noch keine Änderung"]
        if errors:
            parts.append(f"{errors} Link(s) ungültig – bitte korrigieren oder leeren")
        status.set_text(" · ".join(parts))
        ok.set_sensitive(changes > 0 and not errors)

    for song in ordered:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        row.set_margin_end(10)
        row.pack_start(label(f"<b>{escape(song.display_name)}</b>", markup=True, wrap=True), False, False, 0)
        entry = Gtk.Entry()
        entry.set_text(song.link)
        entry.set_placeholder_text("Songlink hier einfügen (Strg+V)")
        entry.song_key = song.key
        row.pack_start(entry, False, False, 0)
        hint = label("", "small", wrap=True)
        row.pack_start(hint, False, False, 0)
        entry.connect("changed", update)
        rows.add(row)
        entries.append((entry, song, hint))

    def visible(row) -> bool:
        text = search.get_text().strip().casefold()
        return not text or text in entries[row.get_index()][1].display_name.casefold()

    rows.set_filter_func(visible)
    search.connect("search-changed", lambda *_: rows.invalidate_filter())
    update()
    dialog.set_default_size(720, 640)
    dialog.show_all()
    if entries:
        entries[0][0].grab_focus()
    response = dialog.run()
    result: dict[str, str] = {}
    for entry, song, _hint in entries:
        try:
            link = parse_user_link(entry.get_text())
        except ValueError:
            continue
        if link != song.link:
            result[song.key] = link
    dialog.destroy()
    return result if response == Gtk.ResponseType.OK and result else None
