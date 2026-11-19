"""E2E: kompletter Spielablauf – Liste, Import, Mix, Karten, PDF-Druck, Ziehen, Tastatur, Bingo, Speichern."""
import json
import re
import zlib

from common import (MESSAGES, TMP, Gdk, Gtk, check, forbid_network, patch_dialogs, pump, run)

forbid_network()
patch_dialogs()


def pdf_page_count(data: bytes) -> int:
    """Zählt Seiten auch in komprimierten Objekt-Streams (Cairo schreibt PDF 1.7)."""
    chunks = [data]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            chunks.append(zlib.decompress(match.group(1)))
        except zlib.error:
            pass
    return sum(len(re.findall(rb"/Type\s*/Page(?![s\w])", chunk)) for chunk in chunks)


def key(window, keyval):
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = keyval
    window.set_focus(None)
    return window._on_key(window, event)


def scenario(w):
    from musik_bingo.domain.catalog import unique_songs, random_mix
    from musik_bingo.domain.playlist import parse_playlist
    from musik_bingo.domain.song_list import parse_songs
    from musik_bingo.presentation import dialogs

    check("Start mit Standardliste (75 Songs, Charts + Weihnachten)", len(parse_songs(w._song_text())) == 75)
    check("Seitenleiste zeigt Songliste", w.summary_values["list"].get_text() == "75 Songs")
    check("Datenschutz-Hinweis „offline“ sichtbar", "offline" in w.privacy_pill.get_text())

    csv = ('"Track URI","Track Name","Artist Name(s)"\n'
           + "".join(f'"spotify:track:{i:022d}","Hit {i} - Remastered","Band {i}"\n' for i in range(30)))
    imported = parse_playlist(csv, "playlist.csv")
    w._set_song_list(imported.songs, "replace")
    songs = parse_songs(w._song_text())
    check("CSV-Import ersetzt Liste (30 Songs, bereinigt)", len(songs) == 30 and songs[0].title == "Hit 0")
    check("Spotify-Links im Editor erhalten", all(song.link.startswith("spotify:track:") for song in songs))
    added, duplicates = w._set_song_list(imported.songs[:5], "append")
    check("Anhängen erkennt Doppelte", (added, duplicates) == (0, 5))

    xmas = unique_songs([c for c in w.catalogs if c.category == "weihnachten"])
    charts = unique_songs([c for c in w.catalogs if c.category == "charts"])
    check("Kataloge geladen (beide Kategorien)", len(xmas) > 50 and len(charts) > 50)
    mix = random_mix(xmas, charts, 40, 50)
    w._set_song_list(mix.songs, "replace")
    check("Zufallsmix 20/20", (mix.christmas, mix.charts) == (20, 20) and len(parse_songs(w._song_text())) == 40)

    w.size_combo.set_active(2)
    w.free_check.set_active(True)
    w.count_spin.set_value(30)
    w._generate(None)
    check("30 Karten 5×5 erzeugt", len(w.service.game.cards) == 30 and w.service.game.size == 5)
    check("Ansicht wechselt zu Karten", w.stack.get_visible_child_name() == "cards")
    check("Vorschau zeigt 18 Karten", len(w.cards_flow.get_children()) == 18)
    check("Spielprognose angezeigt", w.cards_forecast.get_text().startswith("Prognose:")
          and "Volle Karte" in w.forecast_label.get_text())
    check("Gewinngarantie erfüllt", w.service.guarantee().ok)

    pdf = TMP / "karten.pdf"
    operation = Gtk.PrintOperation()
    operation.set_n_pages(15)
    operation.set_export_filename(str(pdf))
    operation.connect("draw-page", w._draw_print_page)
    operation.run(Gtk.PrintOperationAction.EXPORT, w)
    data = pdf.read_bytes() if pdf.exists() else b""
    pages = pdf_page_count(data)
    check(f"PDF-Druck: 15 Seiten für 30 Karten (gefunden {pages})", pages == 15)

    w._select_page("game")
    pump()
    check("Spielleitung aktiv", w.stack.get_visible_child_name() == "game")
    for _ in range(5):
        key(w, Gdk.KEY_space)
    check("Leertaste zieht 5 Songs", len(w.service.game.caller.drawn) == 5)
    key(w, Gdk.KEY_BackSpace)
    check("Rücktaste nimmt zurück", len(w.service.game.caller.drawn) == 4)
    check("Fortschritt angezeigt", w.progress_label.get_text() == "4/40")

    card = w.service.game.cards[0]
    for song in card.songs[:5]:
        w.service.draw_song(song)
    shown = {}
    dialogs.bingo_check_dialog = lambda parent, count, rule: (1, "Oma")
    dialogs.bingo_result_dialog = lambda *args: shown.update(wins=args[7], cells=args[8])
    w._verify_bingo(None)
    check("Bingo-Prüfung erkennt Reihe 1", "Reihe 1" in shown.get("wins", []))
    check("Gewinnfelder markiert", {0, 1, 2, 3, 4} <= shown.get("cells", set()))
    dialogs.bingo_check_dialog = lambda parent, count, rule: (2, "")
    w._verify_bingo(None)

    open_song = next(s for s in w.service.game.caller.pool if not w.service.game.caller.is_drawn(s))
    row = next(r for r in w.pool_list.get_children() if r.song.key == open_song.key)
    before = len(w.service.game.caller.drawn)
    w._pool_row_activated(w.pool_list, row)
    check("Doppelklick markiert Song von Hand", len(w.service.game.caller.drawn) == before + 1)
    w.pool_search.set_text(open_song.title)
    pump(0.3)
    visible = [r for r in w.pool_list.get_children() if r.get_child_visible() and r.get_mapped()]
    check("Suche filtert Songpool", 1 <= len(visible) < 40)

    # Gewinnziel „Volle Karte“: erst nach allen Songs der Karte erfüllt
    w.win_buttons["volle_karte"].set_active(True)
    check("Gewinnziel umgestellt", w.service.win_target == "volle_karte")
    check("Gewinnziel in der Kopfzeile sichtbar", "Volle Karte" in w.rule_pill.get_text())
    before_switch = len(w.service.game.caller.drawn)
    tab = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    tab.keyval = Gdk.KEY_Tab
    w._on_key(w, tab)  # Tastatur-Navigation beginnt
    w.follow_switch.grab_focus()
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = Gdk.KEY_space
    check("Leertaste auf per Tab angesteuertem Schalter zieht keinen Song", not w._on_key(w, event)
          and len(w.service.game.caller.drawn) == before_switch)
    w._on_pointer(w, None)  # Mausklick beendet die Tastatur-Navigation
    result = {}
    dialogs.bingo_check_dialog = lambda parent, count, rule: (1, "Oma")
    dialogs.bingo_result_dialog = lambda *args: result.update(reached=args[10], full=args[11], label=args[9])
    w._verify_bingo(None)
    check("Volle Karte noch nicht erreicht", result.get("reached") is False and result.get("label") == "Volle Karte")
    while w.service.game.caller.draw_next():
        pass
    w._render_caller()
    winners = [n for n in range(1, len(w.service.game.cards) + 1) if w.service.check_win(n)[0]]
    check("alle Songs gespielt → jede Karte gewinnt (Garantie)", len(winners) == len(w.service.game.cards))
    w._verify_bingo(None)
    check("Bingo-Prüfung bestätigt Volle Karte", result.get("reached") is True and result.get("full") is True)

    # Neue Karten nach dem Druck: alte Runde wird automatisch gesichert
    old_first_card = list(w.service.game.cards[0].songs)
    w._generate(None)
    backups = w.store.backups()
    check("Sicherung vor neuen Karten angelegt", len(backups) == 1)
    from musik_bingo.infrastructure.file_store import FileStore
    check("Sicherung enthält die alten Karten", FileStore.import_from(backups[0]).game.cards[0].songs == old_first_card)
    w.win_buttons["volle_karte"].set_active(True)

    w._save_settings()
    saved = json.loads((TMP / "data" / "musik-bingo" / "spielstand.json").read_text())
    check("Spielstand gespeichert (Index, Karten, Links)",
          saved["caller_index"] == w.service.game.caller.index and len(saved["cards"]) == 30
          and saved["settings"]["win_target"] == "volle_karte")
    w._toggle_theme(None)
    check("Design umschaltbar und gemerkt", (TMP / "config" / "musik-bingo" / "theme").read_text() == "light")
    check("Keine Fehlermeldungen", MESSAGES == [])


run(scenario)
