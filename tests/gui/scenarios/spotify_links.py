"""E2E: Link-Übersicht – Chip „Spotify: x von y“, Dialog „Spotify-Links“, Links aus dem Playlist-Abgleich.

Aufruf: spotify_links.py <dark|light> [screenshot-ordner]
"""
import sys
from pathlib import Path
from types import SimpleNamespace

THEME = sys.argv[1] if len(sys.argv) > 1 else "dark"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else None
from common import MESSAGES, TMP, GLib, Gtk, check, forbid_network, patch_dialogs, pump, run, screenshot  # noqa: E402

(TMP / "config" / "musik-bingo").mkdir(parents=True, exist_ok=True)
(TMP / "config" / "musik-bingo" / "theme").write_text(THEME)
forbid_network()
patch_dialogs()
SEEN: dict = {}


def track(i: int) -> str:
    return f"spotify:track:{i:02d}" + "A" * 20


def widgets(root, kind):
    found = []

    def collect(widget):
        if isinstance(widget, kind):
            found.append(widget)
        if isinstance(widget, Gtk.Container):
            widget.foreach(collect)
    collect(root)
    return found


def open_dialog() -> Gtk.Dialog | None:
    return next((top for top in Gtk.Window.list_toplevels()
                 if isinstance(top, Gtk.Dialog) and top.get_visible() and top.get_title() == "Spotify-Links"), None)


def scenario(w):
    from musik_bingo.domain.models import Song
    from musik_bingo.infrastructure.file_store import FileStore
    from musik_bingo.presentation import dialogs

    w.resize(1320, 860)
    lines = []
    for i in range(40):
        line = f"Song {i:02d} – Interpret {i}"
        if i == 5:
            line += " | https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        elif i not in (12, 30):
            line += f" | {track(i)}"
        lines.append(line)
    w.song_buffer.set_text("\n".join(lines))
    pump(0.3)
    check("Chip auf der Songliste sichtbar", w.link_chip.get_visible())
    check("Chip zählt 37 von 40", w.link_chip.get_label().startswith("Spotify: 37 von 40 Songs direkt abspielbar"))
    w._generate(None)
    w.target_buttons["spotify"].set_active(True)
    w._select_page("game")
    pump(0.3)
    check("Hinweis in der Spielleitung bei Ziel Spotify", w.game_link_hint.get_visible()
          and "37 von 40" in w.game_link_hint.get_label())
    if OUT is not None:
        w.queue_draw()
        pump(1.0)
        for top in Gtk.Window.list_toplevels():  # Tooltip unter dem Xvfb-Mauszeiger verdeckt sonst das Bild
            if type(top).__name__ == "GtkTooltipWindow":
                top.hide()
        pump(0.3)
        check(f"Screenshot links-spielleitung-{THEME}.png", screenshot(w, OUT / f"links-spielleitung-{THEME}.png"))
    w.target_buttons["lokal"].set_active(True)
    pump(0.1)
    check("kein Hinweis bei lokaler Wiedergabe", not w.game_link_hint.get_visible())
    w.target_buttons["spotify"].set_active(True)
    game = w.service.game
    current = next(song for song in game.songs if song.title == "Song 12")
    w.service.draw_song(current)
    w._render_caller()
    card_keys = [[s.key for s in card.songs] for card in game.cards]
    wins = [w.service.check_bingo(n) for n in range(1, len(game.cards) + 1)]

    def operate() -> bool:
        dialog = open_dialog()
        if dialog is None:
            return True
        entries = [e for e in widgets(dialog, Gtk.Entry) if hasattr(e, "song_key")]
        SEEN["count"] = len(entries)
        SEEN["first"] = [e.song_key for e in entries[:3]]
        labels = lambda: [label.get_text() for label in widgets(dialog, Gtk.Label)]  # noqa: E731
        SEEN["hint"] = any(text.startswith("Spotify-Link bekommst du in Spotify per Rechtsklick") for text in labels())
        ok = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        SEEN["ok_initial"] = ok.get_sensitive()
        entries[0].set_text("https://open.spotify.com/album/" + "B" * 22)
        SEEN["album_error"] = any("Album" in text and text.startswith("⚠") for text in labels())
        SEEN["ok_with_error"] = ok.get_sensitive()
        entries[0].set_text("https://open.spotify.com/intl-de/track/" + "C" * 22 + "?si=abc123")
        SEEN["valid"] = any(text.startswith("✓ Spotify-Titel") for text in labels())
        entries[1].set_text("spotify:track:" + "D" * 22)
        entries[2].set_text("https://open.spotify.com/playlist/" + "E" * 22)
        if OUT is not None:  # alle Zustände: ✓ Spotify, YouTube, Fehler, kein Link
            entries[3].set_text("")
            pump(0.2)
            SEEN["shot"] = screenshot(dialog, OUT / f"links-{THEME}.png")
            entries[3].set_text(track(0))
        entries[2].set_text("https://open.spotify.com/track/" + "E" * 22)
        search = widgets(dialog, Gtk.SearchEntry)[0]
        search.set_text("song 30")
        pump(0.3)
        rows = widgets(dialog, Gtk.ListBox)[0].get_children()
        SEEN["filtered"] = sum(1 for row in rows if row.get_child_visible())
        search.set_text("")
        pump(0.2)
        SEEN["ok_final"] = ok.get_sensitive()
        dialog.response(Gtk.ResponseType.OK)
        return False

    GLib.timeout_add(500, operate)
    w.game_link_hint.clicked()
    pump(0.3)
    check("Dialog zeigt alle 40 Songs", SEEN.get("count") == 40)
    check("Songs ohne Spotify-Link zuerst (stabile Reihenfolge)",
          SEEN.get("first") == ["song 05 – interpret 5", "song 12 – interpret 12", "song 30 – interpret 30"])
    check("Hinweistext steht im Dialog", SEEN.get("hint"))
    check("Übernehmen erst nach Änderung aktiv", SEEN.get("ok_initial") is False)
    check("Album-Link wird sofort abgelehnt", SEEN.get("album_error"))
    check("ungültiger Link sperrt Übernehmen", SEEN.get("ok_with_error") is False)
    check("gültiger Link wird mit ✓ bestätigt", SEEN.get("valid"))
    check("Suche filtert die Liste", SEEN.get("filtered") == 1)
    check("Übernehmen aktiv mit gültigen Links", SEEN.get("ok_final") is True)
    if OUT is not None:
        check(f"Screenshot links-{THEME}.png", SEEN.get("shot"))
    check("aktueller Song (Song 12) hat jetzt den Link", game.caller.current.title == "Song 12"
          and game.caller.current.link == "spotify:track:" + "D" * 22)
    check("Link aus intl-de-Adresse mit ?si= vereinheitlicht",
          next(s for s in game.songs if s.title == "Song 05").link == "spotify:track:" + "C" * 22)
    check("Editorzeile enthält den Link",
          f"Song 12 – Interpret 12 | spotify:track:{'D' * 22}" in w._song_text().splitlines())
    check("Karten tragen den Link", all(s.link == "spotify:track:" + "D" * 22 for card in game.cards
                                         for s in card.songs if s.title == "Song 12"))
    check("Karten und Gewinnprüfung unverändert", [[s.key for s in card.songs] for card in game.cards] == card_keys
          and [w.service.check_bingo(n) for n in range(1, len(game.cards) + 1)] == wins)
    check("Chip: alle 40 Songs direkt abspielbar", w.link_chip.get_label().startswith("✓ Spotify: alle 40 Songs"))
    check("Hinweis in der Spielleitung verschwindet", not w.game_link_hint.get_visible())
    loaded = FileStore().load()
    check("Links gespeichert und wieder ladbar",
          next(s for s in loaded.game.songs if s.title == "Song 30").link == "spotify:track:" + "E" * 22
          and loaded.game.caller.current.link == "spotify:track:" + "D" * 22)

    # „Mit Playlist abgleichen“ überträgt Spotify-Links auf vorhandene Songs ohne Link
    w.service.set_song_links({"song 07 – interpret 7": "", "song 08 – interpret 8": ""})
    w._apply_service_to_widgets(w.service)
    pump(0.2)
    check("nach Entfernen: 38 von 40", w.link_chip.get_label().startswith("Spotify: 38 von 40"))
    playlist = [Song(s.title, s.artist, track(int(s.title[5:]))) for s in game.songs]
    dialogs.import_playlist_dialog = lambda parent: (SimpleNamespace(songs=playlist), dialogs.MODE_REPLACE)
    MESSAGES.clear()
    w._compare_playlist(None)
    pump(0.2)
    check("Abgleich meldet: Playlist passt", MESSAGES == ["Playlist passt genau"])
    check("Abgleich hat Links übernommen", next(s for s in game.songs if s.title == "Song 07").link == track(7)
          and next(s for s in game.songs if s.title == "Song 08").link == track(8))
    check("Abgleich überschreibt keine vorhandenen Links",
          next(s for s in game.songs if s.title == "Song 05").link == "spotify:track:" + "C" * 22)
    check("Abgleich: Karten nicht neu erzeugt", [[s.key for s in card.songs] for card in game.cards] == card_keys)
    check("Abgleich: Karten tragen die Links", all(s.link == track(7) for card in game.cards
                                                    for s in card.songs if s.title == "Song 07"))
    check("Abgleich: Editorzeile aktualisiert", f"Song 07 – Interpret 7 | {track(7)}" in w._song_text().splitlines())
    check("Abgleich gespeichert", next(s for s in FileStore().load().game.songs if s.title == "Song 08").link
          == track(8))
    # Regression: „1 Links aus der Playlist übernommen“ / „1 Links gespeichert“ (Einzahl/Mehrzahl)
    w.service.set_song_links({"song 07 – interpret 7": ""})
    w._apply_service_to_widgets(w.service)
    pump(0.2)
    details = []
    dialogs.message = lambda parent, kind, title, detail: details.append(detail)
    w._compare_playlist(None)
    pump(0.2)
    check("Abgleich mit einem Link: Einzahl in der Meldung",
          len(details) == 1 and details[0].endswith(" 1 Link aus der Playlist übernommen.")
          and "Links" not in details[0])
    check("Abgleich mit einem Link: Einzahl in der Statuszeile",
          w.status.get_text() == "Mit Playlist abgeglichen: 1 Link übernommen")
    patch_dialogs()
    w.service.set_song_links({"song 07 – interpret 7": "", "song 08 – interpret 8": ""})
    w._apply_service_to_widgets(w.service)
    pump(0.2)
    dialogs.spotify_links_dialog = lambda parent, songs, source: {"song 07 – interpret 7": track(7)}
    w._edit_links()
    check("ein Link gespeichert: Einzahl", w.status.get_text().startswith("1 Link gespeichert · "))
    dialogs.spotify_links_dialog = lambda parent, songs, source: {"song 07 – interpret 7": track(9),
                                                                  "song 08 – interpret 8": track(8)}
    w._edit_links()
    check("zwei Links gespeichert: Mehrzahl", w.status.get_text().startswith("2 Links gespeichert · "))
    if OUT is not None:
        w._select_page("songs")
        pump(0.4)
        check(f"Screenshot links-songs-{THEME}.png", screenshot(w, OUT / f"links-songs-{THEME}.png"))


run(scenario)
