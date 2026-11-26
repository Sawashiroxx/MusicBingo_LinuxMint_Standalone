"""E2E: Korrekturen aus der Gesamtprüfung von 2.6.2 (Claude Fable 5.2).

- Gleichstand hinter einer „nicht vergebenen“ früheren Karte wurde nicht gemeldet
- BINGO-Banner blieb nach „Gewinner löschen“ auf dem Beamer
- Song ohne Spotify-Link: Die Steuerung drängte sich vor die Spotify-Suche, in der man den Titel anklicken muss
- „Spielstand exportieren“ an einen Ort ohne lokalen Pfad: Ausnahme, Dialog blieb offen, keine Meldung
- „Spielstand importieren“: Sicherungsordner als Lesezeichen
- Bildschirmschoner/Ruhezustand gesperrt, solange der Beamer offen ist
"""
from common import MESSAGES, GLib, Gtk, check, forbid_network, patch_dialogs, pump, run

forbid_network()
patch_dialogs()


def songs_text(count: int) -> str:
    return "\n".join(f"Song {i:02d} – Interpret {i}" for i in range(count))


def tie_behind_unassigned_card(w):
    from musik_bingo.domain.caller import Caller
    from musik_bingo.domain.models import BingoCard

    w.song_buffer.set_text(songs_text(30))
    w.size_combo.set_active(0)
    w.free_check.set_active(False)
    w.count_spin.set_value(3)
    w._generate(None)
    game = w.service.game
    s = game.songs
    # Karte 1 (Reserve) hat Reihe 1 nach Song 3, Karten 2 und 3 beide erst bei Song 4
    game.cards = [BingoCard(s[0:3] + s[10:16]), BingoCard([s[0], s[1], s[3]] + s[16:22]),
                  BingoCard([s[1], s[2], s[3]] + s[22:28])]
    game.caller = Caller(game.songs, s, -1)
    w._select_page("game")
    for _ in range(3):
        w._draw_next()
    pump(0.2)
    check("Song 3: Karte #1 oben gemeldet", "#1" in w.target_hint_label.get_text())
    w._ignore_hint_card(None)  # Karte 1 nicht vergeben
    w._draw_next()
    pump(0.2)
    hint, panel = w.target_hint_label.get_text(), w.target_status_label.get_text()
    check(f"Gleichstand der Karten 2 und 3 oben gemeldet ({hint})", "Gleichstand" in hint)
    check(f"Gleichstand im Panel bei Song 4 ({panel})", "Gleichstand: 2 Karten beim selben Song (Nr. 4)" in panel)
    # Erste Karte eingetragen: Die zweite bleibt ein Gleichstand
    w._register_winner(2, "")
    pump(0.2)
    check("Nach Eintragen von #2: #3 weiter als Gleichstand", "Gleichstand" in w.target_hint_label.get_text())


def banner_after_removing_winner(w):
    w.beamer_button.set_active(True)
    pump(0.3)
    w._register_winner(3, "Erna")
    pump(0.2)
    check("Banner nach Eintragen", w.beamer.banner_label.get_text().startswith("BINGO! Karte #3"))
    index = next(i for i, winner in enumerate(w.service.winners) if winner.card == 3)
    w._remove_winner(None, index)
    pump(0.2)
    check("Banner nach „Gewinner löschen“ weg",
          not w.beamer.banner.get_visible() or w.beamer.banner_label.get_text() == "")
    # Ein anderer Gewinner bleibt gefeiert, wenn ein älterer Eintrag gelöscht wird
    w._register_winner(3, "Erna")
    pump(0.2)
    index = next(i for i, winner in enumerate(w.service.winners) if winner.card == 2)
    w._remove_winner(None, index)
    pump(0.2)
    check("Löschen eines anderen Gewinners lässt das Banner stehen",
          w.beamer.banner_label.get_text().startswith("BINGO! Karte #3"))


def idle_inhibit(w):
    app = w.get_application()
    calls = []
    real_inhibit, real_uninhibit = app.inhibit, app.uninhibit
    app.inhibit = lambda window, flags, reason: calls.append(("an", int(flags), reason)) or 42
    app.uninhibit = lambda cookie: calls.append(("aus", cookie))
    w.beamer_button.set_active(False)
    pump(0.2)
    calls.clear()
    w.beamer_button.set_active(True)
    pump(0.2)
    flags = int(Gtk.ApplicationInhibitFlags.IDLE | Gtk.ApplicationInhibitFlags.SUSPEND)
    check("Beamer offen: Bildschirmschoner und Ruhezustand gesperrt",
          calls == [("an", flags, "Musik Bingo: Der Beamer ist offen")] and w.inhibit_cookie == 42)
    w.beamer_button.set_active(True)
    w._update_beamer()
    check("Kein doppeltes Sperren", len(calls) == 1)
    w.beamer_button.set_active(False)
    pump(0.2)
    check("Beamer zu: Sperre aufgehoben", calls[-1] == ("aus", 42) and w.inhibit_cookie == 0)
    w.beamer_button.set_active(True)
    pump(0.2)
    beamer = w.beamer
    beamer.emit("delete-event", None)  # Beamer-Fenster direkt schließen (Alt+F4)
    beamer.destroy()
    pump(0.2)
    check("Beamer-Fenster geschlossen: Sperre aufgehoben", calls[-1] == ("aus", 42) and w.inhibit_cookie == 0)
    app.inhibit, app.uninhibit = real_inhibit, real_uninhibit


def no_refocus_without_link(w):
    from musik_bingo.presentation import gtk_app

    opened, presents = [], []
    real_open = gtk_app.open_uri
    gtk_app.open_uri = opened.append
    w.spotify_scheme = True
    w.song_buffer.set_text(songs_text(40))  # ohne Links
    w.size_combo.set_active(0)
    w.count_spin.set_value(10)
    w._generate(None)
    w._select_page("game")
    w.target_buttons["spotify"].set_active(True)
    w.auto_play_check.set_active(True)
    active = {"own": True}
    w._own_window_active = lambda: active["own"]
    w.present_with_time = lambda _time: presents.append(1)
    w._draw_next()  # öffnet die Spotify-Suche
    active["own"] = False  # Spotify vorn, die Spielleitung klickt dort den Titel an
    pump(3.0)
    check("Spotify-Suche geöffnet", any("search" in uri for uri in opened))
    check(f"Steuerung drängt sich nicht vor die Suche ({len(presents)}× nach vorn)", presents == [])
    gtk_app.open_uri = real_open
    del w.present_with_time
    del w._own_window_active
    w.auto_play_check.set_active(False)
    w.target_buttons["lokal"].set_active(True)


def export_without_local_path(w):
    def answer():
        for top in Gtk.Window.list_toplevels():
            if isinstance(top, Gtk.FileChooserDialog) and top.get_visible():
                top.get_filename = lambda: None  # wie bei mtp://… oder smb://… ohne lokalen Pfad
                top.response(Gtk.ResponseType.ACCEPT)
        return False

    MESSAGES.clear()
    GLib.timeout_add(400, answer)
    try:
        w._export(None)
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    pump(0.3)
    left = [t for t in Gtk.Window.list_toplevels() if isinstance(t, Gtk.FileChooserDialog) and t.get_visible()]
    check("Export ohne lokalen Pfad: keine Ausnahme, Dialog zu, Meldung",
          not raised and not left and MESSAGES == ["Export fehlgeschlagen"])
    MESSAGES.clear()


def import_shows_backups(w):
    w._backup("test")  # Sicherungsordner sicher anlegen
    found = {}

    def answer():
        for top in Gtk.Window.list_toplevels():
            if isinstance(top, Gtk.FileChooserDialog) and top.get_visible():
                found["folders"] = list(top.list_shortcut_folders())
                top.response(Gtk.ResponseType.CANCEL)
        return False

    GLib.timeout_add(400, answer)
    w._import(None)
    pump(0.2)
    check("Import: Sicherungsordner als Lesezeichen", str(w.store.backup_dir) in found.get("folders", []))


def scenario(w):
    tie_behind_unassigned_card(w)
    banner_after_removing_winner(w)
    idle_inhibit(w)
    no_refocus_without_link(w)
    export_without_local_path(w)
    import_shows_backups(w)
    w.beamer_button.set_active(False)
    check("Keine unerwarteten Fehlermeldungen", MESSAGES == [])


run(scenario)
