from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from musik_bingo.application.beamer_state import build_beamer_state
from musik_bingo.application.game_service import GameService
from musik_bingo.application.song_timer import SongTimer
from musik_bingo.application.spotify_check import (
    NO_REPLY_NOTE,
    NO_TEST_SONG_NOTE,
    checklist,
    count_spotify_links,
    pick_test_song,
    report,
)
from musik_bingo.domain.catalog import Catalog, parse_catalog
from musik_bingo.domain.evening import DuplicateWinner, next_stage, next_stage_label, winners_csv
from musik_bingo.domain.forecast import WIN_TARGET_LABELS, WIN_TARGETS
from musik_bingo.domain.card_generator import (
    NotEnoughSongs,
    cards_containing,
    required_songs,
    unique_card_capacity,
    winning_cells,
)
from musik_bingo.domain.link_coverage import link_coverage
from musik_bingo.domain.links import is_spotify
from musik_bingo.domain.matching import PlayingTrack, SongMatcher, compare_with_playlist, links_from_playlist
from musik_bingo.domain.models import Song
from musik_bingo.domain.playlist import from_player_tracks, to_csv, to_m3u, to_text
from musik_bingo.domain.song_list import format_songs, parse_songs
from musik_bingo.domain.text import count_text
from musik_bingo.infrastructure import mpris, spotify
from musik_bingo.infrastructure.audio_matcher import match_audio_files
from musik_bingo.infrastructure.audio_player import AudioPlayer
from musik_bingo.infrastructure.file_store import FileStore
from musik_bingo.infrastructure.launcher import has_scheme_handler, open_uri, plan_launch
from musik_bingo.presentation import dialogs, printing
from musik_bingo.presentation.beamer import BeamerWindow
from musik_bingo.presentation.dialogs import MODE_APPEND, add_class, escape, field, label
from musik_bingo.presentation.theme import css_for

from musik_bingo.paths import CATALOG_DIR, DEFAULT_SONGS as DEFAULT_SONGS_PATH, ICON_PATH, ICON_SIZES, ICON_THEME_DIR

DEFAULT_SONGS = DEFAULT_SONGS_PATH.read_text(encoding="utf-8")
PAGES = ("songs", "cards", "game")
TARGET_LABELS = {"lokal": "Lokale Dateien", "spotify": "Spotify", "youtube": "YouTube"}
# Die Spotify-App für Linux holt sich bei jedem neuen Titel selbst nach vorn und verdeckt die Steuerung.
# Danach holt sich die Steuerung zurück – mehrmals, weil Spotify je nach Ladezeit später nach vorn springt.
REFOCUS_DELAYS_MS = (400, 1200, 2500)
REFOCUS_AUTOSTART_S = 20.0  # Spotify-Autostart: Das Spotify-Fenster erscheint erst nach Sekunden
EXTERNAL_TARGETS = ("spotify", "youtube")
NAVIGATION_KEYS = (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right)


def is_readable_file(path_text: str | None) -> bool:
    """Wie Path.is_file(), aber ohne Ausnahme bei fehlenden Rechten, toten Netzlaufwerken oder „~unbekannt“."""
    if not path_text:
        return False
    try:
        return os.path.isfile(os.path.expanduser(path_text))
    except (OSError, ValueError):
        return False


def default_window_size() -> tuple[int, int]:
    """Startgröße des Hauptfensters, die auf den Bildschirm passt.

    Die Kopfleiste (ca. 70 px) zählt bei set_default_size nicht mit: 1320×800 ergab ein rund 870 px hohes
    Fenster – auf einem 1366×768-Laptop lagen Statuszeile und untere Bedienelemente unter dem Bildschirmrand.
    """
    width, height = 1320, 800
    display = Gdk.Display.get_default()
    monitor = (display.get_primary_monitor() or display.get_monitor(0)) if display is not None else None
    if monitor is not None:
        area = monitor.get_workarea()
        width = max(1000, min(width, area.width - 20))
        height = max(564, min(height, area.height - 90))
    return width, height


def cairo_available() -> bool:
    """Druck braucht die Cairo-Brücke von PyGObject (Paket python3-gi-cairo)."""
    try:
        gi.require_foreign("cairo")
        return True
    except ImportError:
        return False


def load_catalogs() -> tuple[list[Catalog], list[str]]:
    catalogs: list[Catalog] = []
    errors: list[str] = []
    for path in sorted(CATALOG_DIR.glob("*.txt")):
        try:
            catalogs.append(parse_catalog(path.stem, path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            errors.append(f"{path.name}: {error}")
    order = {"weihnachten": 0, "charts": 1}
    catalogs.sort(key=lambda catalog: (order.get(catalog.category, 9), catalog.name))
    return catalogs, errors


class MusikBingoWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Musik Bingo")
        try:
            from gi.repository import GdkPixbuf
            icons = [GdkPixbuf.Pixbuf.new_from_file(str(ICON_THEME_DIR / f"{size}x{size}" / "apps" / "musik-bingo.png"))
                     for size in ICON_SIZES if size <= 256]
            self.set_icon_list(icons)
        except (GLib.Error, ValueError, ImportError):
            try:
                self.set_icon_from_file(str(ICON_PATH))
            except GLib.Error:
                self.set_icon_name("audio-x-generic")
        self.set_default_size(*default_window_size())
        self.set_size_request(1000, 640)
        self.store = FileStore()
        self.service = GameService()
        self.preview_count = 18
        self.print_per_page = 2
        self.song_save_source = 0
        self._loading_state = False
        self.is_fullscreen = False
        self.catalogs, catalog_errors = load_catalogs()
        self.audio_player = None
        self.audio_error = ""
        try:
            self.audio_player = AudioPlayer(on_finished=self._audio_finished, on_error=self._audio_failed)
        except RuntimeError as error:
            self.audio_error = str(error)
        # Externe Player (Spotify, Browser) über MPRIS – nur lokal.
        self.player: mpris.MprisPlayer | None = None
        self.player_watch = 0
        self.player_poll = 0
        self.last_track_identity = ""
        self.now_playing: PlayingTrack | None = None
        self.unmatched_track: PlayingTrack | None = None
        self.spotify_scheme = has_scheme_handler("spotify")
        self.reader: mpris.PlaylistReader | None = None
        # Spotify zuverlässig abspielen: Kontrolle nach OpenUri, Autostart, Selbsttest
        self.playback_check: spotify.PlaybackCheck | None = None
        self.refocus_generation = 0
        self.refocus_until = 0.0  # bis dahin gilt der Wunsch „Steuerung vorn behalten“ auch ohne Fokus
        self.play_generation = 0  # steigt bei jedem neuen Song: alte Rückmeldungen verfallen
        self.spotify_waiter: spotify.NameWaiter | None = None
        self.spotify_waiter_callbacks: list = []
        self.spotify_start_timeout_ms = spotify.START_TIMEOUT_MS
        self.playback_check_ms = spotify.CHECK_TIMEOUT_MS
        self.spotify_self_test: spotify.SelfTest | None = None
        self.spotify_test_player: mpris.MprisPlayer | None = None
        self.spotify_test_running = False
        self.spotify_test_notes: list[str] = []  # Hinweise für den Ergebnisdialog
        self.warning_kind = ""  # "follow" (Titel nicht auf den Karten), "spotify" oder "autoplay"
        # Hinweis „Song-Timer läuft, Musik startet nicht von selbst“ von Hand ausgeblendet: nicht bei jedem Song neu
        self.autoplay_hint_dismissed = False
        self.forecast_text = ""  # Prognose-Text der aktuellen Runde
        # Abend: Beamer, Aufdecken, Timer, Gewinner-Banner
        self.beamer: BeamerWindow | None = None
        self.revealed = False
        self.banner = ""
        self.timer = SongTimer()
        self.timer_source = 0
        # Gewinner eingetragen: Der Timer startet erst wieder, wenn die Spielleitung weitermacht – auch wenn der
        # Player im Folgen-Modus inzwischen von selbst zum nächsten Titel wechselt.
        self.timer_hold = False
        self.closing = False

        self.theme = "dark"
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        self.theme_path = config_home / "musik-bingo" / "theme"
        try:
            if self.theme_path.read_text(encoding="utf-8").strip() == "light":
                self.theme = "light"
        except OSError:
            pass
        self.css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._build()
        self._restore()
        self.timer_source = GLib.timeout_add_seconds(1, self._timer_tick)
        # Tastenkürzel: Wer per Tab/Pfeiltasten navigiert, bedient das fokussierte Element;
        # ein Mausklick beendet diesen Modus wieder.
        self.keyboard_navigating = False
        self._held_keys: dict[int, int] = {}   # Taste → Zeit des letzten Tastendrucks (ms, X-Server-Zeit)
        self._last_click_draw = 0.0
        self.connect("key-press-event", self._on_key)
        self.connect("key-release-event", self._on_key_release)
        self.connect("focus-out-event", lambda *_args: self._held_keys.clear() or False)
        # In der Einfangphase: Knöpfe verbrauchen den Klick selbst, das Fenster sähe ihn sonst nie –
        # nach einem versehentlichen Tab blieb der Tastaturmodus trotz Klick auf „Nächsten Song ziehen“ an.
        self._pointer_gesture = Gtk.GestureMultiPress.new(self)
        self._pointer_gesture.set_button(0)
        self._pointer_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._pointer_gesture.connect("pressed", lambda *_args: self._on_pointer(self, None))
        self.connect("button-press-event", self._on_pointer)
        self.connect("delete-event", self._before_close)
        if catalog_errors:
            self._set_status("Kataloge teilweise nicht lesbar: " + "; ".join(catalog_errors))

    # ================================================================ Aufbau

    def _build(self) -> None:
        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.set_title("Musik Bingo")
        self.header.set_subtitle("Private Veranstaltung · offline")
        self.set_titlebar(self.header)
        menu_button = Gtk.MenuButton()
        menu_button.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        menu_button.set_tooltip_text("Menü")
        popover = Gtk.Popover()
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        menu.set_border_width(8)
        self.theme_item = Gtk.ModelButton(text="")
        for text, handler in (
            ("Spielstand exportieren …", self._export),
            ("Spielstand importieren …", self._import),
            (None, None),
            ("__theme__", self._toggle_theme),
            ("Vollbild umschalten (F11)", lambda *_: self._toggle_fullscreen()),
            (None, None),
            ("Hilfe & Datenschutz", self._show_help),
        ):
            if text is None:
                menu.pack_start(Gtk.Separator(), False, False, 4)
                continue
            item = self.theme_item if text == "__theme__" else Gtk.ModelButton(text=text)
            item.connect("clicked", handler)
            menu.pack_start(item, False, False, 0)
        menu.show_all()
        popover.add(menu)
        menu_button.set_popover(popover)
        self.header.pack_end(menu_button)
        self.privacy_pill = label("● offline", "pill", "pill-ok", "small")
        self.privacy_pill.set_valign(Gtk.Align.CENTER)
        self.privacy_pill.set_tooltip_text(
            "Die App stellt keine Internetverbindung her und überträgt keine Daten. "
            "Spotify/YouTube werden nur lokal angesteuert bzw. per Klick im Browser geöffnet."
        )
        self.header.pack_end(self.privacy_pill)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        add_class(root, "main-bg")
        self.add(root)
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(body, True, True, 0)
        body.pack_start(self._build_sidebar(), False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        self.stack.add_named(self._scrollable(self._build_songs_page()), "songs")
        self.stack.add_named(self._scrollable(self._build_cards_page()), "cards")
        self.stack.add_named(self._scrollable(self._build_game_page()), "game")
        body.pack_start(self.stack, True, True, 0)

        status_bar = add_class(Gtk.Box(spacing=12), "statusbar")
        self.status = label("Bereit · Spielstände werden nur lokal gespeichert", "small")
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        status_bar.pack_start(self.status, True, True, 0)
        status_bar.pack_end(label("Leertaste: ziehen · Rücktaste: zurück · T: Titel aufdecken · P: Timer-Pause · F11: Vollbild", "small"), False, False, 0)
        root.pack_end(status_bar, False, False, 0)
        self._apply_theme()

    @staticmethod
    def _scrollable(page: Gtk.Widget) -> Gtk.Widget:
        """Seite scrollt bei Bedarf senkrecht, statt die Fensterhöhe zu erzwingen.

        Sonst wäre das Fenster mindestens so hoch wie die längste Seite (~960 px) und ragte auf
        1366×768-Laptops aus dem Bildschirm. Bei normaler Größe füllt die Seite den Platz wie bisher.
        """
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # Natürliche Größe der Seite weitergeben: Aufteilung neben der Seitenleiste bleibt wie bisher
        scroll.set_propagate_natural_width(True)
        scroll.set_propagate_natural_height(True)
        scroll.add(page)  # legt einen Gtk.Viewport an
        scroll.get_child().set_shadow_type(Gtk.ShadowType.NONE)
        return scroll

    def _build_sidebar(self) -> Gtk.Widget:
        sidebar = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "app-sidebar")
        sidebar.set_size_request(250, -1)
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        brand.set_margin_start(22)
        brand.set_margin_top(20)
        brand.set_margin_bottom(14)
        brand.pack_start(label("♪ Musik Bingo", "brand"), False, False, 0)
        brand.pack_start(label("Spieltisch für eure Feier", "muted", "small"), False, False, 0)
        sidebar.pack_start(brand, False, False, 0)
        self.nav = Gtk.ListBox()
        self.nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for number, (name, title, subtitle) in enumerate((
            ("songs", "Songs & Playlist", "Liste, Import, Zufallsmix"),
            ("cards", "Bingokarten", "Vorschau und Druck"),
            ("game", "Spielleitung", "Ziehen, abspielen, prüfen"),
        ), start=1):
            row = Gtk.ListBoxRow()
            row.page_name = name
            add_class(row, "nav-row")
            box = Gtk.Box(spacing=12)
            badge = label(str(number), "nav-number", xalign=0.5)
            badge.set_valign(Gtk.Align.CENTER)
            box.pack_start(badge, False, False, 0)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            texts.pack_start(label(title, "nav-title"), False, False, 0)
            texts.pack_start(label(subtitle, "muted", "small"), False, False, 0)
            box.pack_start(texts, True, True, 0)
            row.add(box)
            self.nav.add(row)
        self.nav.connect("row-selected", self._nav_selected)
        sidebar.pack_start(self.nav, False, False, 0)

        summary = add_class(Gtk.Grid(row_spacing=7, column_spacing=10), "summary")
        self.summary_values: dict[str, Gtk.Label] = {}
        for row_index, (key, title) in enumerate((
            ("list", "Songliste"), ("cards", "Karten"), ("drawn", "Gezogen"), ("player", "Wiedergabe"),
        )):
            summary.attach(label(title, "muted", "small"), 0, row_index, 1, 1)
            value = label("–", "summary-value", "small", xalign=1)
            value.set_hexpand(True)
            value.set_ellipsize(Pango.EllipsizeMode.END)
            value.set_max_width_chars(16)
            self.summary_values[key] = value
            summary.attach(value, 1, row_index, 1, 1)
        sidebar.pack_end(summary, False, False, 0)
        return sidebar

    def _page(self, title: str, subtitle: str) -> tuple[Gtk.Widget, Gtk.Box, Gtk.Box]:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_border_width(24)
        head = Gtk.Box(spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        titles.pack_start(label(title, "page-title"), False, False, 0)
        titles.pack_start(label(subtitle, "muted", wrap=True), False, False, 0)
        head.pack_start(titles, True, True, 0)
        outer.pack_start(head, False, False, 0)
        return outer, head, outer

    @staticmethod
    def _panel(title: str, subtitle: str = "") -> tuple[Gtk.Box, Gtk.Box]:
        frame = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "panel")
        frame.pack_start(label(title, "panel-title"), False, False, 0)
        if subtitle:
            frame.pack_start(label(subtitle, "muted", "small", wrap=True), False, False, 0)
        return frame, frame

    @staticmethod
    def _button(text: str, handler, *classes: str, icon: str = "", tooltip: str = "") -> Gtk.Button:
        button = Gtk.Button(label=text)
        if icon:
            button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            button.set_always_show_image(True)
        if tooltip:
            button.set_tooltip_text(tooltip)
        button.connect("clicked", handler)
        add_class(button, *classes)
        return button

    # ---------------------------------------------------------------- Seite 1

    def _build_songs_page(self) -> Gtk.Widget:
        page, _head, body = self._page(
            "Songs & Playlist",
            "Die Songliste ist die Grundlage der Karten. Damit Musik und Karten übereinstimmen: "
            "Playlist importieren oder Liste als Playlist exportieren.",
        )
        toolbar = Gtk.FlowBox()
        toolbar.set_selection_mode(Gtk.SelectionMode.NONE)
        toolbar.set_max_children_per_line(8)
        toolbar.set_column_spacing(8)
        toolbar.set_row_spacing(8)
        catalog_button = Gtk.MenuButton(label="Liste einfügen ▾")
        catalog_button.set_tooltip_text("Mitgelieferte Charts- und Weihnachtslisten anhängen")
        catalog_popover = Gtk.Popover()
        catalog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        catalog_box.set_border_width(8)
        for catalog in self.catalogs:
            item = Gtk.ModelButton(text=f"{catalog.name} ({len(catalog.songs)})")
            item.set_tooltip_text(catalog.source)
            item.connect("clicked", self._insert_catalog, catalog)
            catalog_box.pack_start(item, False, False, 0)
        catalog_box.show_all()
        catalog_popover.add(catalog_box)
        catalog_button.set_popover(catalog_popover)
        for widget in (
            self._button("Playlist importieren …", self._import_playlist, "primary", icon="document-open-symbolic",
                         tooltip="CSV (z. B. Spotify-Export), M3U oder kopierte YouTube-Titel"),
            self._button("Vom Player einlesen …", self._read_from_player, icon="media-playlist-consecutive-symbolic",
                         tooltip="Die laufende Playlist in Spotify/YouTube Titel für Titel einlesen"),
            self._button("Zufallsmix …", self._random_mix, icon="media-playlist-shuffle-symbolic",
                         tooltip="Zufällige Mischung aus Chart-Hits (1990 bis heute, Listen wählbar) "
                                 "und Weihnachtsliedern"),
            catalog_button,
            self._button("Als Playlist exportieren …", self._export_playlist, icon="document-save-as-symbolic",
                         tooltip="Text/CSV für Spotify-/YouTube-Import oder M3U"),
            self._button("Mit Playlist abgleichen …", self._compare_playlist, icon="emblem-ok-symbolic",
                         tooltip="Prüfen, ob Playlist und Bingo-Songs identisch sind"),
            self._button("Leeren", self._clear_songs, "danger", icon="edit-clear-all-symbolic"),
        ):
            toolbar.add(widget)
        body.pack_start(toolbar, False, False, 0)

        columns = Gtk.Box(spacing=16)
        body.pack_start(columns, True, True, 0)
        song_frame, song_box = self._panel(
            "Songliste", "Pro Zeile: Titel – Interpret. Optional mit „ | “ und Spotify-/YouTube-Link. "
                         "Zeilen mit # ohne „ – Interpret“ sind Kommentare. Doppelte Songs werden automatisch ignoriert.")
        columns.pack_start(song_frame, True, True, 0)
        self.song_view = Gtk.TextView()
        self.song_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        for setter in (self.song_view.set_left_margin, self.song_view.set_right_margin,
                       self.song_view.set_top_margin, self.song_view.set_bottom_margin):
            setter(10)
        self.song_buffer = self.song_view.get_buffer()
        self.song_buffer.set_text(DEFAULT_SONGS)
        self.song_buffer.connect("changed", self._song_changed)
        song_scroll = add_class(Gtk.ScrolledWindow(), "editor")
        song_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        song_scroll.set_min_content_height(300)
        song_scroll.add(self.song_view)
        song_box.pack_start(song_scroll, True, True, 0)
        self.pool_count_label = label("", "small")
        song_box.pack_start(self.pool_count_label, False, False, 0)
        self.link_chip = self._button("", self._edit_links, "link-chip",
                                      tooltip="Spotify-Links ansehen und fehlende nachtragen")
        self.link_chip.set_halign(Gtk.Align.START)
        self.link_chip.set_no_show_all(True)
        song_box.pack_start(self.link_chip, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right.set_size_request(340, -1)
        columns.pack_start(right, False, False, 0)
        settings_frame, settings = self._panel("Karten vorbereiten", "Jede Karte bekommt eine andere Songkombination.")
        right.pack_start(settings_frame, False, False, 0)
        self.title_entry = Gtk.Entry()
        self.title_entry.set_max_length(60)
        self.title_entry.set_placeholder_text("z. B. Weihnachtsfeier 2026")
        self.title_entry.set_text("Musik Bingo")
        self.title_entry.connect("changed", self._title_changed)
        settings.pack_start(field("Titel der Feier", self.title_entry, "Steht auf jeder Karte und auf dem Beamer."),
                            False, False, 0)
        self.size_combo = Gtk.ComboBoxText()
        for value in (3, 4, 5):
            self.size_combo.append_text(f"{value} × {value}")
        self.size_combo.set_active(2)
        self.size_combo.connect("changed", self._update_field_count)
        self.count_spin = Gtk.SpinButton.new_with_range(1, 500, 1)
        self.count_spin.set_value(160)
        self.count_spin.set_tooltip_text("Faustregel: Gästezahl + 10–15 % Puffer (z. B. 140 Gäste → 160 Karten). "
                                         "Mehr Karten verändern den Spielverlauf kaum.")
        self.count_spin.connect("value-changed", self._count_changed)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10, column_homogeneous=True)
        grid.attach(field("Kartengröße", self.size_combo), 0, 0, 1, 1)
        grid.attach(field("Anzahl Karten", self.count_spin), 1, 0, 1, 1)
        settings.pack_start(grid, False, False, 0)
        self.free_check = Gtk.CheckButton(label="Freies Mittelfeld (bei 3×3 und 5×5)")
        self.free_check.set_active(True)
        self.free_check.connect("toggled", self._update_field_count)
        settings.pack_start(self.free_check, False, False, 0)
        self.diagonal_check = Gtk.CheckButton(label="Diagonalen zählen als Bingo")
        self.diagonal_check.set_tooltip_text("Gilt ab der nächsten Kartenerzeugung.")
        self.diagonal_check.connect("toggled", self._save_settings)
        settings.pack_start(self.diagonal_check, False, False, 0)
        self.page_combo = Gtk.ComboBoxText()
        self.page_combo.append_text("2 Karten pro A4-Seite")
        self.page_combo.append_text("1 Karte pro A4-Seite")
        self.page_combo.set_active(0)
        self.page_combo.connect("changed", self._set_page_count)
        settings.pack_start(field("Drucklayout", self.page_combo), False, False, 0)
        self.field_count = label("24 Songs je Karte", "muted", "small")
        settings.pack_start(self.field_count, False, False, 0)
        generate = self._button("Karten erzeugen", self._generate, "primary", "big", icon="view-grid-symbolic")
        settings.pack_start(generate, False, False, 4)
        settings.pack_start(label("Neue Karten starten eine neue Runde. Die Liste links kann vorher frei "
                                  "bearbeitet werden – laufende Runden bleiben unberührt.",
                                  "muted", "small", wrap=True), False, False, 0)

        audio_frame, audio_box = self._panel("Eigene Musikdateien",
                                             "Optional: MP3/FLAC/OGG aus einem Ordner zuordnen, "
                                             "Dateiname „Titel – Interpret.mp3“.")
        audio_box.pack_start(self._button("Ordner zuordnen …", self._match_audio_folder,
                                          icon="folder-music-symbolic"), False, False, 0)
        right.pack_start(audio_frame, False, False, 0)
        self._update_song_stats()
        return page

    # ---------------------------------------------------------------- Seite 2

    def _build_cards_page(self) -> Gtk.Widget:
        page, head, body = self._page("Bingokarten", "Vorschau der ersten Karten. Gedruckt werden alle.")
        self.cards_meta = label("", "pill", "small")
        self.cards_meta.set_valign(Gtk.Align.CENTER)
        head.pack_start(self.cards_meta, False, False, 0)
        self.cards_forecast = label("", "muted", "small", wrap=True)
        body.pack_start(self.cards_forecast, False, False, 0)
        self.print_button = self._button("Drucken / PDF …", self._print, "primary", "big", icon="printer-symbolic")
        self.print_button.set_valign(Gtk.Align.CENTER)
        head.pack_end(self.print_button, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.cards_flow = Gtk.FlowBox()
        self.cards_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.cards_flow.set_column_spacing(16)
        self.cards_flow.set_row_spacing(16)
        self.cards_flow.set_max_children_per_line(4)
        self.cards_flow.set_valign(Gtk.Align.START)
        scroll.add(self.cards_flow)
        body.pack_start(scroll, True, True, 0)
        self._render_cards()
        return page

    # ---------------------------------------------------------------- Seite 3

    def _build_game_page(self) -> Gtk.Widget:
        page, head, body = self._page("Spielleitung", "Songs ziehen, abspielen und Gewinner prüfen.")
        self.rule_pill = label("", "pill", "small")
        self.rule_pill.set_valign(Gtk.Align.CENTER)
        head.pack_end(self.rule_pill, False, False, 0)
        win_box = add_class(Gtk.Box(spacing=0), "linked")
        win_box.set_valign(Gtk.Align.CENTER)
        self.win_buttons: dict[str, Gtk.RadioButton] = {}
        group = None
        for key in WIN_TARGETS:
            button = Gtk.RadioButton.new_with_label_from_widget(group, WIN_TARGET_LABELS[key])
            button.set_mode(False)
            button.set_tooltip_text("Gewinnziel dieser Runde – „Bingo prüfen“ prüft genau dieses Ziel. "
                                    "Vor dem ersten Song gewählt, beginnen auch die nächsten Runden damit.")
            group = group or button
            button.connect("toggled", self._win_target_changed, key)
            win_box.pack_start(button, False, False, 0)
            self.win_buttons[key] = button
        head.pack_end(win_box, False, False, 8)
        head.pack_end(label("Gewinnziel", "tiny", "muted"), False, False, 0)
        columns = Gtk.Box(spacing=18)
        body.pack_start(columns, True, True, 0)
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        left.set_margin_end(6)
        left_scroll.add(left)
        columns.pack_start(left_scroll, True, True, 0)

        # Wiedergabequelle
        # Zwei Zeilen: Ziele oben, „Player folgen“ darunter – so bleibt das Fenster schmal genug
        # für 1366er-Bildschirme, auch mit vier Wiedergabezielen.
        source = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "panel-flat")
        source_row = Gtk.Box(spacing=12)
        source_row.pack_start(label("Wiedergabe über", "tiny", "muted"), False, False, 0)
        targets = add_class(Gtk.Box(spacing=0), "linked")
        self.target_buttons: dict[str, Gtk.RadioButton] = {}
        group = None
        for key in ("lokal", "spotify", "youtube"):
            button = Gtk.RadioButton.new_with_label_from_widget(group, TARGET_LABELS[key])
            button.set_mode(False)
            group = group or button
            button.connect("toggled", self._target_changed, key)
            targets.pack_start(button, False, False, 0)
            self.target_buttons[key] = button
        source_row.pack_start(targets, False, False, 0)
        source.pack_start(source_row, False, False, 0)
        follow_box = Gtk.Box(spacing=8)
        self.follow_switch = Gtk.Switch()
        self.follow_switch.set_valign(Gtk.Align.CENTER)
        self.follow_switch.connect("notify::active", self._follow_toggled)
        follow_box.pack_start(self.follow_switch, False, False, 0)
        follow_label = label("Player folgen")
        follow_label.set_tooltip_text(
            "Die Playlist läuft in Spotify oder YouTube (gerne im Zufallsmodus). Die App zieht automatisch "
            "den Song, der gerade läuft, und warnt, wenn er nicht auf den Karten steht."
        )
        follow_box.pack_start(follow_label, False, False, 0)
        source.pack_start(follow_box, False, False, 0)
        left.pack_start(source, False, False, 0)

        # Bedienknöpfe zuerst: Ihre Lage hängt so nicht von Titellänge, Hinweisen und Warnungen darunter ab
        controls = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        self.draw_button = self._button("Nächsten Song ziehen", self._draw_next, "primary", "big",
                                        icon="media-playlist-shuffle-symbolic")
        self.undo_button = self._button("Zurück", self._undo, "big", icon="edit-undo-symbolic")
        self.verify_button = self._button("Bingo prüfen", self._verify_bingo, "big", icon="emblem-ok-symbolic")
        self.shuffle_button = self._button("Neu mischen", self._reshuffle, icon="view-refresh-symbolic")
        controls.attach(self.draw_button, 0, 0, 2, 1)
        controls.attach(self.undo_button, 2, 0, 1, 1)
        controls.attach(self.verify_button, 3, 0, 1, 1)
        self.stage_button = self._button("Weiter: 2 Reihen", self._advance_stage, icon="go-next-symbolic",
                                         tooltip="Nächstes Gewinnziel – die Ziehung läuft weiter. "
                                                 "Nach „Volle Karte“ beginnt eine neue Runde (neu gemischt) "
                                                 "mit dem Gewinnziel vom Rundenbeginn.")
        controls.attach(self.stage_button, 0, 1, 4, 1)
        # Knöpfe und (darunter) die Warnung in einem Kasten: Die Warnung braucht ausgeblendet keinen Platz
        controls_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        controls_area.pack_start(controls, False, False, 0)
        left.pack_start(controls_area, False, False, 0)


        # Jetzt-Anzeige
        self.hero = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "hero")
        self.now_label = label("", "hero-kicker", xalign=0.5)
        self.song_label = label("Musik Bingo", "song-title", wrap=True, xalign=0.5)
        self.song_label.set_justify(Gtk.Justification.CENTER)
        self.artist_label = label("", "song-artist", "hero-muted", wrap=True, xalign=0.5)
        self.artist_label.set_justify(Gtk.Justification.CENTER)
        self.source_chip = label("", "chip", "small", xalign=0.5)
        self.source_chip.set_halign(Gtk.Align.CENTER)
        self.hero.pack_start(self.now_label, False, False, 0)
        self.hero.pack_start(self.song_label, False, False, 6)
        self.hero.pack_start(self.artist_label, False, False, 0)
        self.hero.pack_start(self.source_chip, False, False, 6)
        progress_row = Gtk.Box(spacing=12)
        self.progress = Gtk.ProgressBar()
        self.progress.set_valign(Gtk.Align.CENTER)
        progress_row.pack_start(self.progress, True, True, 0)
        self.progress_label = label("", "hero-muted", "small")
        progress_row.pack_start(self.progress_label, False, False, 0)
        self.hero.pack_end(progress_row, False, False, 0)
        left.pack_start(self.hero, False, False, 0)
        self.forecast_label = label("", "muted", "small", wrap=True)
        left.pack_start(self.forecast_label, False, False, 0)
        self.game_link_hint = self._button("", self._edit_links, "link-chip", "link-missing",
                                           icon="dialog-warning-symbolic",
                                           tooltip="Songs ohne Spotify-Link werden über die Suche geöffnet. "
                                                   "Klicken, um Links nachzutragen.")
        self.game_link_hint.set_halign(Gtk.Align.START)
        self.game_link_hint.set_no_show_all(True)
        left.pack_start(self.game_link_hint, False, False, 0)

        # Warnung: läuft, steht aber nicht auf den Karten
        self.warning_revealer = Gtk.Revealer()
        warning = add_class(Gtk.Box(spacing=12), "warning-box")
        self.warning_label = label("", wrap=True)
        warning.pack_start(self.warning_label, True, True, 0)
        self.warning_skip_button = self._button("Überspringen", self._skip_unmatched,
                                                icon="media-skip-forward-symbolic")
        warning.pack_end(self.warning_skip_button, False, False, 0)
        self.warning_autoplay_button = self._button(
            "Automatisch abspielen", self._enable_autoplay, icon="media-playback-start-symbolic",
            tooltip="Hakt „Beim Ziehen automatisch abspielen“ an und startet den aktuellen Song")
        self.warning_autoplay_button.set_no_show_all(True)
        warning.pack_end(self.warning_autoplay_button, False, False, 0)
        warning.pack_end(self._button("Ausblenden", self._dismiss_warning, "flat"), False, False, 0)
        self.warning_revealer.add(warning)
        # Direkt unter die Knöpfe: Weiter unten (nach Anzeige und Prognose) lag die Warnung auf einem
        # 1366×768-Laptop unter dem sichtbaren Bereich – „Überspringen“ war nur nach Scrollen zu erreichen.
        # Die Knöpfe darüber bleiben an ihrer Stelle.
        warning.set_margin_top(14)
        controls_area.pack_start(self.warning_revealer, False, False, 0)

        show_frame, show = self._panel("Beamer & Timer",
                                       "Beamer: zweites Fenster für die Gäste (Doppelklick/F11 = Vollbild). "
                                       "Der Songtitel bleibt verborgen, bis du ihn aufdeckst (Taste T) – "
                                       "oder ganz, wenn „Titel auf dem Beamer aufdecken“ aus ist.")
        show_row = Gtk.Box(spacing=8)
        self.beamer_button = Gtk.ToggleButton(label="Beamer öffnen")
        self.beamer_button.set_image(Gtk.Image.new_from_icon_name("video-display-symbolic", Gtk.IconSize.BUTTON))
        self.beamer_button.set_always_show_image(True)
        self.beamer_button.connect("toggled", self._beamer_toggled)
        self.reveal_button = Gtk.ToggleButton(label="Titel aufdecken (T)")
        self.reveal_button.connect("toggled", self._reveal_toggled)
        show_row.pack_start(self.beamer_button, False, False, 0)
        show_row.pack_start(self.reveal_button, False, False, 0)
        self.beamer_reveal_check = Gtk.CheckButton(label="Titel auf dem Beamer aufdecken")
        self.beamer_reveal_check.set_active(True)
        self.beamer_reveal_check.set_tooltip_text(
            "Aus: Die Gäste sehen auf dem Beamer nie einen Songtitel – weder beim Aufdecken (T) noch in der "
            "Auflösung des Timers oder unter „Zuletzt“. Du siehst ihn weiter hier im Hauptfenster.")
        self.beamer_reveal_check.connect("toggled", self._beamer_reveal_changed)
        show_row.pack_start(self.beamer_reveal_check, False, False, 0)
        show.pack_start(show_row, False, False, 0)
        timer_row = Gtk.Box(spacing=10)
        self.timer_spin = Gtk.SpinButton.new_with_range(0, 600, 5)
        self.timer_spin.set_tooltip_text("Sekunden pro Song, danach automatisch weiter. 0 = Timer aus.")
        self.timer_spin.connect("value-changed", self._timer_settings_changed)
        self.reveal_spin = Gtk.SpinButton.new_with_range(0, 30, 1)
        self.reveal_spin.set_value(5)
        self.reveal_spin.set_tooltip_text("Sekunden, in denen der Titel vor dem nächsten Song aufgelöst wird. 0 = keine Auflösung.")
        self.reveal_spin.connect("value-changed", self._timer_settings_changed)
        self.timer_pause_button = self._button("Pause (P)", self._toggle_timer_pause, icon="media-playback-pause-symbolic")
        timer_row.pack_start(label("Song-Timer (s)", "small"), False, False, 0)
        timer_row.pack_start(self.timer_spin, False, False, 0)
        timer_row.pack_start(label("Auflösung (s)", "small"), False, False, 0)
        timer_row.pack_start(self.reveal_spin, False, False, 0)
        timer_row.pack_start(self.timer_pause_button, False, False, 0)
        show.pack_start(timer_row, False, False, 0)
        self.timer_label = label("Timer aus", "panel-title")
        show.pack_start(self.timer_label, False, False, 0)
        left.pack_start(show_frame, False, False, 0)

        play_panel = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "panel-flat")
        play_row = Gtk.Box(spacing=8)
        self.audio_play_button = self._button("Abspielen", self._play_audio, icon="media-playback-start-symbolic")
        self.audio_pause_button = self._button("Pause", self._pause_audio, icon="media-playback-pause-symbolic")
        self.audio_stop_button = self._button("Stopp", self._stop_audio, icon="media-playback-stop-symbolic")
        self.audio_assign_button = self._button("Datei zuordnen …", self._assign_audio_file, "flat")
        for button in (self.audio_play_button, self.audio_pause_button, self.audio_stop_button):
            play_row.pack_start(button, False, False, 0)
        play_row.pack_end(self.audio_assign_button, False, False, 0)
        play_row.pack_end(self.shuffle_button, False, False, 0)
        play_panel.pack_start(play_row, False, False, 0)
        options_row = Gtk.Box(spacing=16)
        self.auto_play_check = Gtk.CheckButton(label="Beim Ziehen automatisch abspielen")
        self.auto_play_check.connect("toggled", self._autoplay_changed)
        options_row.pack_start(self.auto_play_check, False, False, 0)
        self.pause_after_check = Gtk.CheckButton(label="Nach Ablauf pausieren")
        self.pause_after_check.set_active(True)
        self.pause_after_check.set_tooltip_text(
            "Läuft die Spielzeit des Song-Timers ab, wird die Musik angehalten (Spotify oder lokale Datei) – "
            "sonst spielt Spotify während der Auflösung weiter.")
        self.pause_after_check.connect("toggled", self._pause_after_changed)
        options_row.pack_start(self.pause_after_check, False, False, 0)
        self.spotify_test_button = self._button(
            "Spotify testen", self._spotify_test, "flat", icon="emblem-system-symbolic",
            tooltip="Startet Spotify bei Bedarf, spielt einen Song der Runde kurz an, pausiert ihn wieder "
                    "und zeigt eine Prüfliste. Zieht keinen Song.")
        options_row.pack_end(self.spotify_test_button, False, False, 0)
        play_panel.pack_start(options_row, False, False, 0)
        self.audio_status = label("", "muted", "small", wrap=True)
        play_panel.pack_start(self.audio_status, False, False, 0)
        left.pack_start(play_panel, False, False, 0)

        history_frame, history = self._panel("Zuletzt gezogen")
        self.history = Gtk.FlowBox()
        self.history.set_selection_mode(Gtk.SelectionMode.NONE)
        self.history.set_max_children_per_line(3)
        self.history.set_column_spacing(8)
        self.history.set_row_spacing(8)
        history.pack_start(self.history, False, False, 0)
        left.pack_start(history_frame, False, False, 0)

        control_frame, control_box = self._panel(
            "Gewinnkontrolle", "Nur hier sichtbar, nicht auf dem Beamer. Die App prüft nach jedem Song alle Karten "
            "gegen das aktuelle Gewinnziel.")
        self.target_status_label = label("", "small", wrap=True)
        control_box.pack_start(self.target_status_label, False, False, 0)
        self.target_cards = Gtk.FlowBox()
        self.target_cards.set_selection_mode(Gtk.SelectionMode.NONE)
        self.target_cards.set_max_children_per_line(4)
        self.target_cards.set_column_spacing(8)
        self.target_cards.set_row_spacing(8)
        control_box.pack_start(self.target_cards, False, False, 0)
        left.pack_start(control_frame, False, False, 0)

        winners_frame, winners_box = self._panel("Gewinnerliste",
                                                 "Wird über „Bingo prüfen“ gefüllt. Dieselbe Karte kann nicht doppelt gewinnen.")
        self.winners_list = Gtk.ListBox()
        self.winners_list.set_selection_mode(Gtk.SelectionMode.NONE)
        winners_box.pack_start(self.winners_list, False, False, 0)
        winners_box.pack_start(self._button("Als CSV exportieren …", self._export_winners,
                                            icon="document-save-as-symbolic"), False, False, 0)
        left.pack_start(winners_frame, False, False, 0)

        pool_frame, pool_content = self._panel("Songpool", "Doppelklick markiert einen Song von Hand als gezogen.")
        pool_frame.set_size_request(330, -1)
        columns.pack_start(pool_frame, False, False, 0)
        self.pool_meta = label("", "muted", "small")
        pool_content.pack_start(self.pool_meta, False, False, 0)
        self.pool_search = Gtk.SearchEntry()
        self.pool_search.set_placeholder_text("Song suchen …")
        self.pool_search.connect("search-changed", lambda *_: self.pool_list.invalidate_filter())
        pool_content.pack_start(self.pool_search, False, False, 0)
        pool_scroll = Gtk.ScrolledWindow()
        pool_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pool_list = Gtk.ListBox()
        self.pool_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.pool_list.set_activate_on_single_click(False)
        self.pool_list.set_filter_func(self._pool_filter)
        self.pool_list.connect("row-activated", self._pool_row_activated)
        pool_scroll.add(self.pool_list)
        pool_content.pack_start(pool_scroll, True, True, 0)
        self._render_caller()
        self._no_focus_on_click(page)
        return page

    @classmethod
    def _no_focus_on_click(cls, widget: Gtk.Widget) -> None:
        """Nach einem Mausklick behält kein Knopf den Fokus – sonst würde die Leertaste ihn erneut auslösen
        (z. B. „Titel aufdecken“ statt „Nächster Song“)."""
        if isinstance(widget, (Gtk.Button, Gtk.Switch, Gtk.ComboBox)):
            widget.set_focus_on_click(False)
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                cls._no_focus_on_click(child)

    # ================================================================ Zustand

    def _apply_service_to_widgets(self, service: GameService) -> None:
        self._loading_state = True
        try:
            self.service = service
            self.song_buffer.set_text(service.song_text)
            self.size_combo.set_active(service.card_size - 3)
            self.free_check.set_active(service.free_space)
            self.diagonal_check.set_active(service.diagonal_wins)
            self.count_spin.set_value(service.card_count)
            self.page_combo.set_active(1 if service.per_page == 1 else 0)
            self.auto_play_check.set_active(service.auto_play)
            self.pause_after_check.set_active(service.pause_after_timer)
            self.beamer_reveal_check.set_active(service.beamer_reveal)
            self._sync_reveal_button()
            self.target_buttons[service.playback_target].set_active(True)
            self.win_buttons[service.win_target].set_active(True)
            self.title_entry.set_text(service.event_title)
            self.timer_spin.set_value(service.timer_seconds)
            self.reveal_spin.set_value(service.reveal_seconds)
            self.timer.configure(service.timer_seconds, service.reveal_seconds)
            self.timer.stop()
            self.timer_hold = False
            self.autoplay_hint_dismissed = False
            if self.warning_kind == "autoplay":
                self._hide_warning()
            self.banner = ""
            self.print_per_page = service.per_page
            self.follow_switch.set_active(False)
        finally:
            self._loading_state = False
        self._update_field_count()
        self._render_cards()
        self._render_caller()
        self._update_forecast()
        self._render_winners()
        self._set_revealed(False)
        self.header.set_subtitle(f"{self.service.event_title} · offline")

    def _restore(self) -> None:
        try:
            saved = self.store.load()
            if saved is not None:
                # Auch das Anwenden kann scheitern (z. B. Zeichen, die GTK nicht darstellen kann) –
                # dann ebenfalls mit leerer Runde starten statt ohne Fenster hängen zu bleiben.
                self._apply_service_to_widgets(saved)
        except Exception as error:  # noqa: BLE001 – kaputte Datei darf den Start nie verhindern
            # Erst sichern: Schon das Schließen der App würde die Datei sonst überschreiben.
            try:
                kept = self.store.backup("unlesbar", keep=True)
                where = (f"Eine unveränderte Kopie liegt in:\n{kept}" if kept
                         else "Es gab keine Datei zum Sichern.")
            except OSError as backup_error:
                where = f"Kopie konnte nicht angelegt werden: {backup_error}"
            # Zurück auf den Auslieferungszustand – das Anwenden kann mittendrin abgebrochen sein
            fresh = GameService()
            fresh.song_text = DEFAULT_SONGS
            fresh.card_count = 160
            self._apply_service_to_widgets(fresh)
            dialogs.message(self, Gtk.MessageType.WARNING, "Spielstand konnte nicht geladen werden",
                            f"{error}\n\nDie App startet mit einer neuen Runde. {where}")
            self.nav.select_row(self.nav.get_row_at_index(0))
            return
        if saved is None:
            self.nav.select_row(self.nav.get_row_at_index(0))
            self._update_summary()
            return
        follow = saved.follow_player
        self.nav.select_row(self.nav.get_row_at_index(2 if saved.game.cards else 0))
        self._set_status("Gespeicherter Spielstand geladen")
        if follow and saved.playback_target in EXTERNAL_TARGETS:
            # Folgen-Modus erst nach dem Aufbau des Fensters versuchen (ohne Fehlermeldung).
            GLib.idle_add(self._resume_follow)

    def _resume_follow(self) -> bool:
        if self._connect_player(quiet=True):
            self.follow_switch.set_active(True)
        else:
            self.service.follow_player = False
            self._set_status("Player folgen ist aus: Der gewählte Player läuft gerade nicht.")
        return False

    def _song_text(self) -> str:
        start, end = self.song_buffer.get_bounds()
        return self.song_buffer.get_text(start, end, True)

    def _set_song_list(self, songs: list[Song], mode: str) -> tuple[int, int]:
        """Ersetzt/ergänzt die Songliste im Editor. Gibt (neu, doppelt) zurück."""
        if mode == MODE_APPEND:
            existing = parse_songs(self._song_text())
            keys = {song.key for song in existing}
            new = [song for song in songs if song.key not in keys]
            text = self._song_text().rstrip("\n")
            addition = format_songs(new)
            self.song_buffer.set_text(f"{text}\n{addition}" if text and addition else (text or addition))
            result = (len(new), len(songs) - len(new))
        else:
            self.song_buffer.set_text(format_songs(songs))
            result = (len(songs), 0)
        self._save_settings()
        return result

    def _active_or_draft_songs(self) -> tuple[list[Song], str]:
        if self.service.game.songs:
            return list(self.service.game.songs), "aktuelle Runde"
        return parse_songs(self._song_text()), "Songliste (noch keine Karten erzeugt)"

    # ================================================================ Seite 1: Aktionen

    def _import_playlist(self, _button) -> None:
        outcome = dialogs.import_playlist_dialog(self)
        if outcome is None:
            return
        result, mode = outcome
        added, duplicate = self._set_song_list(result.songs, mode)
        details = [f"{count_text(added, 'Song', 'Songs')} übernommen"]
        if duplicate:
            details.append(f"{duplicate} schon vorhanden")
        if result.skipped:
            details.append(f"{count_text(len(result.skipped), 'Zeile', 'Zeilen')} übersprungen")
        self._set_status("Playlist importiert: " + " · ".join(details))

    def _random_mix(self, _button) -> None:
        if not self.catalogs:
            dialogs.message(self, Gtk.MessageType.ERROR, "Keine Songlisten gefunden",
                            f"Im Ordner {CATALOG_DIR} liegen keine lesbaren Kataloge.")
            return
        outcome = dialogs.mix_dialog(self, self.catalogs)
        if outcome is None:
            return
        result, mode = outcome
        added, _duplicate = self._set_song_list(result.songs, mode)
        text = f"Zufallsmix: {result.christmas} Weihnachtslieder + {result.charts} Chart-Hits"
        if result.shortfall:
            text += f" · {result.shortfall} weniger als gewünscht (Listen erschöpft)"
        if mode == MODE_APPEND:
            text += f" · {added} neu angehängt"
        self._set_status(text)

    def _insert_catalog(self, _button, catalog: Catalog) -> None:
        added, duplicate = self._set_song_list(catalog.songs, MODE_APPEND)
        self._set_status(f"„{catalog.name}“: {count_text(added, 'Song', 'Songs')} angehängt" + (f", {duplicate} schon vorhanden" if duplicate else ""))

    def _clear_songs(self, _button) -> None:
        if dialogs.confirm(self, "Songliste leeren?",
                           "Die Liste im Editor wird geleert. Erzeugte Karten und die laufende Runde bleiben erhalten.",
                           "Leeren"):
            self.song_buffer.set_text("")
            self._save_settings()

    def _export_playlist(self, _button) -> None:
        songs, source = self._active_or_draft_songs()
        if not songs:
            dialogs.message(self, Gtk.MessageType.INFO, "Nichts zu exportieren", "Die Songliste ist leer.")
            return
        dialog = Gtk.FileChooserDialog(title=f"Als Playlist exportieren ({source})", transient_for=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Exportieren", Gtk.ResponseType.ACCEPT)
        dialog.set_do_overwrite_confirmation(True)
        filters = {}
        for key, name, pattern in (
            ("txt", "Text „Interpret - Titel“ – für TuneMyMusic/Soundiiz → Spotify/YouTube", "*.txt"),
            ("csv", "CSV (Titel, Interpret, Link)", "*.csv"),
            ("m3u", "M3U-Playlist (lokale Dateien/YouTube-Links, z. B. für VLC)", "*.m3u"),
        ):
            file_filter = Gtk.FileFilter()
            file_filter.set_name(name)
            file_filter.add_pattern(pattern)
            dialog.add_filter(file_filter)
            filters[key] = file_filter
        dialog.set_current_name("musik-bingo-playlist.txt")

        def filter_changed(*_args):
            current = dialog.get_current_name() or "musik-bingo-playlist"
            stem = current.rsplit(".", 1)[0]
            for key, file_filter in filters.items():
                if dialog.get_filter() == file_filter:
                    dialog.set_current_name(f"{stem}.{key}")
        dialog.connect("notify::filter", filter_changed)
        response = dialog.run()
        filename = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if not filename:
            return
        path = Path(filename)
        suffix = path.suffix.casefold()
        try:
            if suffix == ".csv":
                content, note = to_csv(songs), ""
            elif suffix in (".m3u", ".m3u8"):
                content, skipped = to_m3u(songs, self.service.audio_files)
                note = f" · {skipped} Songs ohne Datei/Link ausgelassen" if skipped else ""
            else:
                content, note = to_text(songs), ""
            path.write_text(content, encoding="utf-8")
        except OSError as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Export fehlgeschlagen", str(error))
            return
        self._set_status(f"{len(songs)} Songs ({source}) als Playlist exportiert: {path.name}{note}")

    def _compare_playlist(self, _button) -> None:
        songs, source = self._active_or_draft_songs()
        if not songs:
            dialogs.message(self, Gtk.MessageType.INFO, "Kein Abgleich möglich", "Die Songliste ist leer.")
            return
        outcome = dialogs.import_playlist_dialog(self)
        if outcome is None:
            return
        result, _mode = outcome
        missing, extra = compare_with_playlist(songs, result.songs)
        # Links der Playlist (z. B. Spotify-Track-Links) auf vorhandene Songs ohne Link übertragen –
        # Karten und Ziehung bleiben unverändert.
        taken = self._apply_links(links_from_playlist(songs, result.songs))
        link_note = f" {count_text(taken, 'Link', 'Links')} aus der Playlist übernommen." if taken else ""
        if taken:
            self._set_status(f"Mit Playlist abgeglichen: {count_text(taken, 'Link', 'Links')} übernommen")
        if not missing and not extra:
            dialogs.message(self, Gtk.MessageType.INFO, "Playlist passt genau",
                            f"Alle {len(songs)} Songs der {source} sind in der Playlist – und umgekehrt.{link_note}")
            return
        dialogs.list_dialog(
            self, "Abgleich mit Playlist",
            f"Verglichen: {source} ({len(songs)} Songs) mit der Playlist ({len(result.songs)} Songs).{link_note}",
            [("Auf den Karten, aber nicht in der Playlist – wird nie gespielt", [s.display_name for s in missing]),
             ("In der Playlist, aber nicht auf den Karten – vorher entfernen", [s.display_name for s in extra])],
        )

    def _read_from_player(self, _button) -> None:
        if self.follow_switch.get_active():
            dialogs.message(self, Gtk.MessageType.INFO, "Erst „Player folgen“ ausschalten",
                            "Beim Einlesen springt der Player von Titel zu Titel. Im Folgen-Modus würden "
                            "dabei alle Songs der laufenden Runde gezogen.")
            return
        players = mpris.list_players()
        if not players:
            dialogs.message(
                self, Gtk.MessageType.INFO, "Kein Player gefunden",
                "Starte zuerst Spotify (Desktop-App) oder spiele die YouTube-Playlist im Browser ab. "
                "Dann erneut versuchen.")
            return
        dialog, content, _ok = dialogs.base_dialog(self, "Playlist vom Player einlesen", "Einlesen starten", 560)
        content.pack_start(label(
            "So geht's:\n1. Playlist im Player öffnen, Zufallswiedergabe aus, Wiederholen an.\n"
            "2. Den ersten Titel der Playlist starten (Lautstärke ruhig leise stellen).\n"
            "3. Hier „Einlesen starten“ – die App springt Titel für Titel weiter und notiert sie.\n\n"
            "Das geschieht lokal über die Player-Schnittstelle des Rechners, ohne Internetzugriff der App.",
            wrap=True), False, False, 0)
        combo = Gtk.ComboBoxText()
        for info in players:
            combo.append(info.bus_name, info.identity)
        chosen = mpris.choose_player(players, self.service.player_name, self.service.playback_target)
        combo.set_active_id((chosen or players[0]).bus_name)
        content.pack_start(field("Player", combo), False, False, 0)
        mode_box, append = dialogs.mode_selector()
        content.pack_start(mode_box, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        bus_name = combo.get_active_id()
        mode = MODE_APPEND if append.get_active() else "replace"
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not bus_name:
            return
        info = next(p for p in players if p.bus_name == bus_name)
        try:
            player = mpris.MprisPlayer(info)
        except RuntimeError as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Player nicht erreichbar", str(error))
            return

        progress = Gtk.Dialog(title="Playlist wird eingelesen", transient_for=self, modal=True, use_header_bar=True)
        progress.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        box = progress.get_content_area()
        box.set_border_width(20)
        box.set_spacing(10)
        count_label = label("Starte …", "panel-title")
        box.pack_start(count_label, False, False, 0)
        spinner = Gtk.Spinner()
        spinner.start()
        box.pack_start(spinner, False, False, 0)
        progress.set_default_size(380, -1)

        def on_progress(count: int) -> None:
            count_label.set_text(f"{count} Titel gelesen …")

        def on_done(tracks: list[PlayingTrack], reason: str, complete: bool) -> None:
            progress.destroy()
            player.close()
            self.reader = None
            if self.closing:
                return
            if not complete:
                # Abbruch/Fehler: bestehende Songliste nicht durch ein Teilergebnis ersetzen.
                dialogs.message(self, Gtk.MessageType.INFO, "Nichts übernommen",
                                f"{reason}\n\nBis dahin gelesen: {len(tracks)} Titel." if tracks else reason)
                return
            # Spotify liefert Titel und Interpret getrennt – nur YouTube-Videos im Browser brauchen das
            # Zerlegen „Interpret - Titel“.
            clean = info.is_spotify
            cleaned = from_player_tracks(tracks, clean_metadata=clean).songs
            if not cleaned:
                dialogs.message(self, Gtk.MessageType.WARNING, "Keine Titel eingelesen", reason)
                return
            added, duplicate = self._set_song_list(cleaned, mode)
            self._set_status(f"{reason} {count_text(added, 'Song', 'Songs')} übernommen" + (f", {duplicate} doppelt" if duplicate else ""))

        def on_response(_dialog, _response):
            if self.reader:
                self.reader.cancel()
        progress.connect("response", on_response)
        progress.show_all()
        self.reader = mpris.PlaylistReader(player, on_progress, on_done)
        self.reader.start()

    def _update_link_overview(self) -> None:
        """Chip „Spotify: x von y Songs direkt abspielbar“ (Songliste) und Hinweis in der Spielleitung."""
        if not hasattr(self, "link_chip") or not hasattr(self, "song_buffer"):
            return
        songs, source = self._active_or_draft_songs()
        coverage = link_coverage(songs)
        self.link_chip.set_label(dialogs.coverage_text(coverage) + " …")
        self.link_chip.set_tooltip_text(f"Bezieht sich auf die {source}. Klicken, um Spotify-Links "
                                        "anzusehen und fehlende nachzutragen.")
        context = self.link_chip.get_style_context()
        context.remove_class("link-ok")
        context.remove_class("link-missing")
        context.add_class("link-ok" if coverage.complete else "link-missing")
        self.link_chip.set_visible(coverage.total > 0)
        self.link_chip.show_all()
        if hasattr(self, "game_link_hint"):
            game_coverage = link_coverage(self.service.game.songs)
            show = (self.service.playback_target == "spotify" and game_coverage.total > 0
                    and not game_coverage.complete)
            self.game_link_hint.set_label(dialogs.coverage_text(game_coverage) + " – Links ergänzen …")
            self.game_link_hint.set_visible(show)
            if show:
                self.game_link_hint.show_all()

    def _apply_links(self, links: dict[str, str]) -> int:
        """Links über den GameService setzen (Songliste, Runde, Karten, Ziehung) und speichern."""
        if not links:
            return 0
        if not self._loading_state:
            self.service.song_text = self._song_text()  # noch nicht gespeicherte Editor-Änderungen
        try:
            changed = self.service.set_song_links(links)
        except ValueError as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Link nicht übernommen", str(error))
            return 0
        if not changed:
            return 0
        if self._song_text() != self.service.song_text:
            self._loading_state = True
            try:
                self.song_buffer.set_text(self.service.song_text)
            finally:
                self._loading_state = False
        self._pool_keys = None  # Songpool neu aufbauen (♫-Markierung)
        self._save()
        self._update_song_stats()
        self._render_caller()
        return changed

    def _edit_links(self, _button=None) -> None:
        songs, source = self._active_or_draft_songs()
        if not songs:
            dialogs.message(self, Gtk.MessageType.INFO, "Keine Songs", "Die Songliste ist leer.")
            return
        links = dialogs.spotify_links_dialog(self, songs, source)
        if not links:
            return
        changed = self._apply_links(links)
        if changed:
            coverage = link_coverage(self._active_or_draft_songs()[0])
            self._set_status(f"{count_text(changed, 'Link', 'Links')} gespeichert · {dialogs.coverage_text(coverage)}")

    def _match_audio_folder(self, _button) -> None:
        dialog = Gtk.FileChooserDialog(title="Ordner mit Audiodateien auswählen", transient_for=self,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Ordner auswählen", Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        folder = Path(dialog.get_filename()) if response == Gtk.ResponseType.ACCEPT and dialog.get_filename() else None
        dialog.destroy()
        if folder is None:
            return
        try:
            songs = self.service.game.songs or parse_songs(self._song_text())
            matched, unmatched = match_audio_files(songs, folder)
            dropped = self.service.merge_audio_files(matched)
            self._save()
            result = f"{len(matched)} Audiodateien zugeordnet · {len(unmatched)} Songs ohne eindeutigen Treffer"
            if dropped:
                result += f" · {dropped} alte Zuordnungen nicht mehr benötigter Songs entfernt"
            if self.audio_player is None:
                result += " · Audioplayer auf diesem System nicht verfügbar"
            self._set_status(result)
            self._update_audio_controls()
        except (OSError, ValueError) as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Audioordner konnte nicht gelesen werden", str(error))

    # ================================================================ Karten

    def _generate(self, _button) -> None:
        self._cancel_playback()  # neue Karten: keine Meldungen mehr zu Songs der alten Runde
        try:
            song_text = self._song_text()
            songs = parse_songs(song_text)
            size = self.size_combo.get_active() + 3
            free_space = self.free_check.get_active()
            self.count_spin.update()
            count = self.count_spin.get_value_as_int()
            needed = required_songs(size, free_space)
            capacity = unique_card_capacity(songs, size, free_space)
            if len(songs) < needed:
                raise NotEnoughSongs(f"Mindestens {needed} eindeutige Songs werden benötigt; aktuell sind es {len(songs)}.")
            if capacity < count:
                raise ValueError(f"Mit dieser Songliste sind höchstens {capacity} unterschiedliche Karten möglich.")
            if self.service.game.cards and not dialogs.confirm(
                self, "Neue Runde vorbereiten?",
                "Die vorhandenen Karten werden ersetzt und der Ziehfortschritt wird zurückgesetzt.",
                "Neue Karten erzeugen",
            ):
                return
            if self.service.game.cards:
                self._backup("vor-neuen-karten")
            self.service.set_song_text(song_text)
            cards = self.service.create_cards(size, free_space, count, self.diagonal_check.get_active())
            self._stop_all_playback()
            self._hide_warning()
            self.autoplay_hint_dismissed = False
            self.last_track_identity = ""
            self.timer.stop()
            self.timer_hold = False
            self.banner = ""
            self._set_revealed(False)
            self._sync_win_buttons()
            self._render_winners()
            self._render_cards()
            self._render_caller()
            self._save()
            self._select_page("cards")
            check = self.service.guarantee()
            if not check.ok:
                dialogs.message(self, Gtk.MessageType.ERROR, "Gewinn nicht garantiert", "\n".join(check.problems))
            self._update_forecast()
            self._set_status(f"{count_text(len(cards), 'Karte', 'Karten')} aus {count_text(len(songs), 'Song', 'Songs')} erzeugt · {self.forecast_text}")
        except (ValueError, NotEnoughSongs) as error:
            dialogs.message(self, Gtk.MessageType.WARNING, "Karten konnten nicht erzeugt werden", str(error))

    def _update_forecast(self) -> None:
        """Spielprognose für die aktuelle Runde (wann gibt es die ersten Gewinner?)."""
        self.forecast_text = ""
        for widget in (getattr(self, "forecast_label", None), getattr(self, "cards_forecast", None)):
            if widget is not None:
                widget.set_text("")
                widget.set_tooltip_text(None)
        if not self.service.game.cards:
            return
        try:
            result = self.service.forecast(runs=200)
        except ValueError:
            return
        parts = [f"{WIN_TARGET_LABELS[key]} ≈ Song {result.stages[key].median}" for key in WIN_TARGETS]
        self.forecast_text = "Prognose: " + " · ".join(parts) + f" (von {result.pool_size})"
        tooltip = "\n".join(
            f"{WIN_TARGET_LABELS[key]}: meist bei Song {stage.early}–{stage.late}, spätestens {stage.worst}, "
            f"Ø {stage.winners:.1f} Gewinner gleichzeitig" for key, stage in result.stages.items())
        tooltip += (f"\n\nGarantie: Spätestens nach allen {result.pool_size} Songs hat jede Karte "
                    "„Volle Karte“. Voraussetzung: Die Playlist enthält wirklich alle Songs der Karten – "
                    "vorher „Mit Playlist abgleichen“ nutzen.")
        for widget in (getattr(self, "forecast_label", None), getattr(self, "cards_forecast", None)):
            if widget is not None:
                widget.set_text(self.forecast_text)
                widget.set_tooltip_text(tooltip)

    def _render_cards(self) -> None:
        for child in self.cards_flow.get_children():
            self.cards_flow.remove(child)
        game = self.service.game
        cards = game.cards[: self.preview_count]
        size = game.size
        free = game.free_space and size % 2 == 1
        if not cards:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            empty.set_margin_top(60)
            empty.pack_start(label("Noch keine Karten", "page-title", xalign=0.5), False, False, 0)
            empty.pack_start(label("Lege unter „Songs & Playlist“ die Liste und Kartengröße fest und klicke "
                                   "„Karten erzeugen“.", "muted", xalign=0.5, wrap=True), False, False, 0)
            self.cards_flow.add(empty)
        cell_width = {3: 104, 4: 80, 5: 64}.get(size, 64)
        # Mindestens zwei pro Zeile – drei kleine 3×3-Karten nebeneinander machten das Fenster breiter
        # als einen 1366-px-Bildschirm (die Vorschau zeigt trotzdem so viele, wie Platz haben).
        self.cards_flow.set_min_children_per_line(2)
        for number, card in enumerate(cards, start=1):
            frame = add_class(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "bingo-card")
            head = add_class(Gtk.Box(), "card-head")
            title_label = label("♪ " + self.service.event_title.upper())
            title_label.set_ellipsize(Pango.EllipsizeMode.END)
            head.pack_start(title_label, True, True, 0)
            head.pack_end(label(f"#{number}"), False, False, 0)
            frame.pack_start(head, False, False, 0)
            grid = Gtk.Grid(column_spacing=3, row_spacing=3, column_homogeneous=True, row_homogeneous=True)
            songs = iter(card.songs)
            for index in range(size * size):
                is_free = free and index == size * size // 2
                cell = label("★ FREI" if is_free else next(songs).display_name, "bingo-cell", wrap=True, xalign=0.5)
                cell.set_justify(Gtk.Justification.CENTER)
                cell.set_lines(4)
                cell.set_ellipsize(Pango.EllipsizeMode.END)
                cell.set_max_width_chars(10)
                cell.set_size_request(cell_width, 54)
                if is_free:
                    add_class(cell, "bingo-cell-free")
                grid.attach(cell, index % size, index // size, 1, 1)
            frame.pack_start(grid, True, True, 0)
            self.cards_flow.add(frame)
        self.cards_flow.show_all()
        total = len(game.cards)
        self.cards_meta.set_text(
            f"{total} Karten · {size} × {size}" + (f" · Vorschau {min(total, self.preview_count)}" if total > self.preview_count else "")
            if total else "keine Karten")
        self.print_button.set_sensitive(total > 0)
        self._update_summary()

    def _print(self, _button) -> None:
        if not self.service.game.cards:
            return
        if not cairo_available():
            dialogs.message(self, Gtk.MessageType.ERROR, "Drucken nicht möglich",
                            "Für den Druck fehlt das Paket python3-gi-cairo. Bitte im Terminal installieren:\n\n"
                            "sudo apt install python3-gi-cairo")
            return
        operation = Gtk.PrintOperation()
        operation.set_job_name("Musik Bingo Karten")
        operation.set_n_pages(math.ceil(len(self.service.game.cards) / self.print_per_page))
        operation.set_unit(Gtk.Unit.POINTS)
        operation.connect("draw-page", self._draw_print_page)
        try:
            operation.run(Gtk.PrintOperationAction.PRINT_DIALOG, self)
        except GLib.Error as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Druckdialog fehlgeschlagen", str(error))

    def _draw_print_page(self, operation, context, page_number: int) -> None:
        cr = context.get_cairo_context()
        width, height = context.get_width(), context.get_height()
        margin = 18
        gap = 22
        count = self.print_per_page
        card_h = (height - 2 * margin - gap * (count - 1)) / count
        first = page_number * count
        for offset in range(count):
            card_index = first + offset
            if card_index >= len(self.service.game.cards):
                break
            y = margin + offset * (card_h + gap)
            self._draw_card(cr, self.service.game.cards[card_index], card_index + 1, margin, y, width - 2 * margin, card_h)

    def _draw_card(self, cr, card, number: int, x: float, y: float, width: float, height: float) -> None:
        game = self.service.game
        printing.draw_card(cr, card, number, x, y, width, height, game.size, game.free_space,
                           bool(getattr(game, "diagonal_wins", False)),
                           getattr(self.service, "event_title", "Musik Bingo").upper())

    @staticmethod
    def _draw_centered_text(cr, text: str, x: float, y: float, width: float, height: float) -> None:
        printing.draw_centered_text(cr, text, x, y, width, height)

    # ================================================================ Spielleitung

    def _render_caller(self) -> None:
        if not hasattr(self, "pool_list"):
            return
        caller = self.service.game.caller
        positions = {song.key: index + 1 for index, song in enumerate(caller.drawn)}
        pool_keys = tuple(song.key for song in caller.pool)
        if pool_keys != getattr(self, "_pool_keys", None):
            # Pool hat sich geändert → Liste neu aufbauen (sonst nur Markierungen aktualisieren).
            self._pool_keys = pool_keys
            self._pool_rows = {}
            for child in self.pool_list.get_children():
                self.pool_list.remove(child)
            for song in caller.pool:
                row = Gtk.ListBoxRow()
                row.song = song
                add_class(row, "pool-row")
                box = Gtk.Box(spacing=8)
                box.set_margin_top(5)
                box.set_margin_bottom(5)
                badge = label("", xalign=1)
                box.pack_start(badge, False, False, 0)
                box.pack_start(label(song.display_name, "name", wrap=True), True, True, 0)
                if song.link:
                    box.pack_end(label("♫", "muted", "small"), False, False, 0)
                row.add(box)
                self.pool_list.add(row)
                self._pool_rows[song.key] = (row, badge)
            self.pool_list.show_all()
        for key, (row, badge) in self._pool_rows.items():
            number = positions.get(key)
            badge.set_text(f"{number}." if number else "○")
            badge_context = badge.get_style_context()
            row_context = row.get_style_context()
            if number:
                badge_context.remove_class("pool-open")
                badge_context.add_class("pool-badge")
                row_context.add_class("pool-drawn")
            else:
                badge_context.remove_class("pool-badge")
                badge_context.add_class("pool-open")
                row_context.remove_class("pool-drawn")

        total = len(caller.pool)
        count = len(caller.drawn)
        song = caller.current
        follow = self.follow_switch.get_active()
        if song:
            self.now_label.set_text("LETZTER SONG · ALLE GESPIELT" if count == total else f"SONG {count} VON {total}")
            self.song_label.set_text(song.title)
            self.artist_label.set_text(song.artist or " ")
        else:
            self.now_label.set_text("BEREIT FÜR DIE ERSTE RUNDE" if total else "NOCH KEIN SPIEL")
            self.song_label.set_text("Musik Bingo")
            if not total:
                self.artist_label.set_text("Erzeuge zuerst Karten, um den Songpool zu laden.")
            elif follow:
                self.artist_label.set_text("Starte die Playlist im Player – der laufende Song wird automatisch gezogen.")
            else:
                self.artist_label.set_text("Leertaste oder „Nächsten Song ziehen“ drücken.")
        self._update_source_chip()
        self._update_link_overview()
        self._render_target_status()
        self.progress_label.set_text(f"{count}/{total}")
        self.progress.set_fraction(count / total if total else 0)
        if self.service.game.cards:
            rule = "Reihen & Spalten" + (" & Diagonalen" if self.service.game.diagonal_wins else "")
            self.rule_pill.set_text(f"Runde {self.service.round_number} · Ziel: "
                                    f"{WIN_TARGET_LABELS[self.service.win_target]} · {rule}")
        else:
            self.rule_pill.set_text("Noch keine Runde")
        self.pool_meta.set_text(f"{total} Songs · {count} gezogen · {total - count} offen")
        if follow:
            self.draw_button.set_label("Nächster Titel im Player")
            self.draw_button.set_sensitive(self.player is not None)
        else:
            self.draw_button.set_label("Nächsten Song ziehen")
            self.draw_button.set_sensitive(total > 0 and count < total)
        self.undo_button.set_sensitive(caller.index >= 0)
        self.shuffle_button.set_sensitive(total > 0 and not follow)
        self.verify_button.set_sensitive(bool(self.service.game.cards))
        for child in self.history.get_children():
            self.history.remove(child)
        recent = list(reversed(caller.drawn[-6:]))
        for position, recent_song in enumerate(recent):
            chip = label(f"{count - position}. {recent_song.display_name}", "history-chip", "small", wrap=True)
            self.history.add(chip)
        if not recent:
            self.history.add(label("Hier erscheinen die zuletzt gezogenen Songs.", "muted", "small"))
        self.history.show_all()
        self._update_audio_controls()
        self._update_summary()
        if hasattr(self, "stage_button"):
            self.stage_button.set_label(next_stage_label(self.service.win_target))
            self.stage_button.set_sensitive(bool(self.service.game.cards))
        self._update_beamer()

    def _update_source_chip(self) -> None:
        song = self.service.game.caller.current
        target = self.service.playback_target
        text = ""
        if song is not None:
            if target == "lokal":
                path = self.service.audio_file_for(song)
                text = f"Datei: {Path(path).name}" if path else "keine Audiodatei zugeordnet"
            elif target == "spotify":
                text = "Spotify-Titel verknüpft" if song.link.startswith("spotify:") else "Spotify: über Suche"
            else:
                name = TARGET_LABELS[target]
                text = f"{name}: Titel verknüpft" if song.link.startswith("https://www.youtube") else f"{name}: über Suche"
        if self.follow_switch.get_active() and self.now_playing:
            text = f"Im Player: {self.now_playing.label}"
        self.source_chip.set_text(text)
        self.source_chip.set_visible(bool(text))

    def _pool_filter(self, row, *_args) -> bool:
        query = self.pool_search.get_text().strip().casefold() if hasattr(self, "pool_search") else ""
        return not query or query in getattr(row, "song", Song("")).display_name.casefold()

    def _pool_row_activated(self, _listbox, row) -> None:
        song = getattr(row, "song", None)
        if song is None or self.service.game.caller.is_drawn(song):
            return
        if dialogs.confirm(self, "Song als gezogen markieren?",
                           f"„{song.display_name}“ wird als nächster gezogener Song eingetragen "
                           "(z. B. wenn er gerade von Hand gespielt wurde).", "Markieren"):
            self._take_song(song, f"Von Hand markiert: {song.display_name}")

    def _take_song(self, song: Song, status: str, automatic: bool = False) -> None:
        if self.service.draw_song(song):
            self._save()
            # Von Hand markiert: Die Warnung „nicht auf den Karten“ ist erledigt – sonst würde
            # „Überspringen“ den gerade markierten Song im Player weiterschalten.
            self._hide_warning()
            self._new_song_started(automatic, unattended=automatic)
            self._render_caller()
            self._set_status(status)

    def _new_song_started(self, automatic: bool = False, unattended: bool = False) -> None:
        """Nach jedem gezogenen Song: Titel verbergen, Banner weg, Timer neu starten.

        ``automatic``: Der Player hat im Folgen-Modus von selbst weitergeschaltet. Ist gerade ein Gewinner
        eingetragen worden, zählt der Song zwar, der Timer bleibt aber aus – sonst liefe die Ziehung während
        der Ehrung alle paar Sekunden von selbst weiter.
        ``unattended``: Niemand hat gerade gedrückt (Player oder Song-Timer haben weitergeschaltet).
        """
        self._cancel_playback()
        self.banner = ""
        self._set_revealed(False)
        if automatic and self.timer_hold:
            return
        self.timer_hold = False
        self._commit_timer_fields(unattended)
        if self.service.game.caller.current is not None:
            self.timer.start()

    def _commit_timer_fields(self, unattended: bool = False) -> None:
        """Eingetippte, aber noch nicht bestätigte Zahlen in „Song-Timer“ und „Auflösung“ übernehmen.

        Ein Zahlenfeld übernimmt Getipptes erst mit Enter, Tab oder wenn es den Fokus verliert. Die Knöpfe der
        Spielleitung nehmen beim Klick aber keinen Fokus, und die Leertaste zieht auch mit Fokus im Feld: Wer
        „15“ tippte und dann zog, hatte „15“ im Feld stehen – der Timer blieb trotzdem aus.
        ``unattended``: Schaltet der Timer oder der Player gerade von selbst weiter, wird ein leeres oder
        unvollständiges Feld (mitten im Tippen) nicht übernommen – das hieße sonst 0 = „Timer aus“.
        """
        if not hasattr(self, "timer_spin"):
            return
        for spin in (self.timer_spin, self.reveal_spin):
            if unattended and not spin.get_text().strip().isdigit():
                continue
            spin.update()

    def _draw_next(self, _button=None, by_timer: bool = False) -> None:
        if _button is not None:
            # Doppelklick auf den Knopf zöge zwei Songs – der erste wäre nie zu hören gewesen
            now = GLib.get_monotonic_time() / 1e6
            if now - self._last_click_draw < 0.6:
                return
            self._last_click_draw = now
        self.timer_hold = False  # die Spielleitung macht weiter
        if self.follow_switch.get_active():
            if self.player:
                self.player.next(on_error=lambda m: self._set_status(f"Player reagiert nicht: {m}"))
            return
        if self.audio_player:
            self.audio_player.stop()
        if self.service.game.caller.draw_next():
            self._save()  # zuerst sichern: ein Fehler beim Zeichnen darf die Ziehung nicht kosten
            self._new_song_started(unattended=by_timer)
            self._render_caller()
            if self.service.auto_play:
                self._play_audio(None, automatic=True)
            else:
                self._warn_timer_without_autoplay()

    def _autoplay_would_start(self, song: Song | None) -> bool:
        """Könnte „Beim Ziehen automatisch abspielen“ diesen Song starten (Spotify oder vorhandene Audiodatei)?"""
        if song is None:
            return False
        target = self.service.playback_target
        if target == "spotify":
            return True
        if target == "lokal":
            return self.audio_player is not None and is_readable_file(self.service.audio_file_for(song))
        return False  # YouTube: jeder Song öffnete ein Browserfenster – das bleibt eine bewusste Entscheidung

    def _warn_timer_without_autoplay(self) -> None:
        """Song-Timer an, „Beim Ziehen automatisch abspielen“ aus: Die Ziehung liefe stumm weiter.

        Mit den Vorgaben der App zählte der Timer herunter, löste auf und zog den nächsten Song, ohne dass je
        Musik lief – und die Statuszeile meldete „Spotify ist nicht verbunden“. Der Hinweis nennt die Ursache
        und bietet den Haken direkt an. „Ausblenden“ merkt sich, dass von Hand abgespielt werden soll.
        Die Statuszeile bleibt unberührt: Dort steht ggf. noch „bitte von Hand pausieren“ zum vorigen Titel.
        """
        if (self.autoplay_hint_dismissed or self.service.auto_play or not self.timer.enabled
                or self.follow_switch.get_active() or self.warning_kind in ("follow", "spotify")
                or not self._autoplay_would_start(self.service.game.caller.current)):
            return
        self.unmatched_track = None
        self.warning_kind = "autoplay"
        self.warning_label.set_markup(
            "<b>Der Song-Timer läuft – die Musik startet aber nicht von selbst</b>\n"
            "„Beim Ziehen automatisch abspielen“ ist aus. Einschalten oder jeden Song mit „Abspielen“ starten.")
        self.warning_skip_button.set_visible(False)
        self.warning_autoplay_button.set_visible(True)
        self.warning_revealer.set_reveal_child(True)

    def _enable_autoplay(self, _button=None) -> None:
        """Aus dem Hinweis heraus: Haken setzen und den aktuellen Song jetzt richtig beginnen."""
        self._hide_warning()
        self.auto_play_check.set_active(True)  # speichert über _autoplay_changed
        if self.service.game.caller.current is not None and self.timer.phase != "aus":
            # Titel wieder verbergen, volle Spielzeit, Musik an
            self._new_song_started()
            self._render_caller()
            self._play_audio(None, automatic=True)

    def _dismiss_warning(self, _button=None) -> None:
        if self.warning_kind == "autoplay":
            self.autoplay_hint_dismissed = True
        self._hide_warning()

    def _undo(self, _button=None) -> None:
        if self.audio_player:
            self.audio_player.stop()
        self._cancel_playback()
        if self.service.game.caller.undo():
            self.timer.stop()
            self.timer_hold = False
            self.banner = ""
            self._set_revealed(False)
            # Im Folgen-Modus den aktuellen Player-Titel NICHT neu bewerten – sonst
            # würde der zurückgenommene Song sofort wieder gezogen.
            if not self.follow_switch.get_active():
                self.last_track_identity = ""
            self._render_caller()
            self._save()

    def _reshuffle(self, _button) -> None:
        if self.service.game.caller.index >= 0 and not dialogs.confirm(
            self, "Ziehung neu mischen?",
            f"Der bisherige Ziehfortschritt wird zurückgesetzt. Es beginnt Runde {self.service.round_number + 1} "
            f"mit „{WIN_TARGET_LABELS[self.service.round_start_target]}“; die Gewinnerliste bleibt erhalten.",
            "Neu mischen"
        ):
            return
        self._stop_all_playback()
        if self.service.game.caller.index >= 0:
            self.service.restart_round()
            self._sync_win_buttons()
        else:
            self.service.game.caller.reshuffle()
        self.timer.stop()
        self.timer_hold = False
        self.banner = ""
        self._set_revealed(False)
        self.last_track_identity = ""
        self._render_caller()
        self._save()
        self._set_status("Songreihenfolge neu gemischt")

    def _verify_bingo(self, _button) -> None:
        game = self.service.game
        if not game.cards:
            return
        rule = (f"{WIN_TARGET_LABELS[self.service.win_target]} – Reihen und Spalten"
                + (" sowie Diagonalen" if game.diagonal_wins else ""))
        was_paused = self.timer.paused
        self.timer.pause()  # während der Prüfung zählt der Timer nicht weiter
        try:
            self._check_card(rule)
        finally:
            if not was_paused:
                self.timer.resume()
            self._update_beamer()

    def _check_card(self, rule: str) -> None:
        game = self.service.game
        answer = dialogs.bingo_check_dialog(self, len(game.cards), rule)
        if answer is None:
            return
        number, name = answer
        if number == dialogs.WITHOUT_NUMBER:
            # Nummer unleserlich/fehlt: Karte über die vorgelesenen Songs der Gewinnreihe finden
            def find(songs: list[Song]) -> list[tuple[int, bool]]:
                return [(found, self.service.check_win(found)[0])
                        for found in cards_containing(game.cards, songs)]
            number = dialogs.find_card_dialog(self, game.songs, {song.key for song in game.caller.drawn}, find)
            if number is None:
                return
        self._show_card_result(number, name)

    def _show_card_result(self, number: int, name: str = "") -> None:
        """Karte mit gezogenen Feldern zeigen; bei erreichtem Ziel als Gewinner eintragbar."""
        game = self.service.game
        try:
            reached, wins, full = self.service.check_win(number)
        except ValueError as error:
            dialogs.message(self, Gtk.MessageType.WARNING, "Ungültige Kartennummer", str(error))
            return
        card = game.cards[number - 1]
        cells = winning_cells(card, game.size, game.free_space, game.caller.drawn, game.diagonal_wins)
        register = dialogs.bingo_result_dialog(self, card, number, name, game.size, game.free_space,
                                               {song.key for song in game.caller.drawn}, wins, cells,
                                               WIN_TARGET_LABELS[self.service.win_target], reached, full)
        if register:
            self._register_winner(number, name)

    def _register_winner(self, number: int, name: str) -> None:
        try:
            winner = self.service.add_winner(number, name)
        except DuplicateWinner as duplicate:
            same_stage = (duplicate.previous.round == self.service.round_number
                          and duplicate.previous.target == self.service.win_target)
            if same_stage:
                dialogs.message(self, Gtk.MessageType.INFO, "Schon eingetragen", str(duplicate))
                return
            if not dialogs.confirm(
                self, "Karte hat schon gewonnen",
                f"{duplicate}\n\nTrotzdem auch für „{WIN_TARGET_LABELS[self.service.win_target]}“ eintragen?",
                "Trotzdem eintragen",
            ):
                return
            try:
                winner = self.service.add_winner(number, name, allow_repeat=True)
            except ValueError as error:  # z. B. Liste voll
                dialogs.message(self, Gtk.MessageType.WARNING, "Nicht eingetragen", str(error))
                return
        except ValueError as error:
            dialogs.message(self, Gtk.MessageType.WARNING, "Nicht eingetragen", str(error))
            return
        self.timer.stop()  # Stufe entschieden – weiter mit dem Stufen-Button oder dem nächsten Song
        self.timer_hold = True
        self.banner = f"BINGO! Karte #{winner.card}" + (f" · {winner.name}" if winner.name else "")
        self._save()
        self._render_winners()
        self._render_caller()
        self._set_status(f"Gewinner eingetragen: {self.banner} – weiter mit „{next_stage_label(self.service.win_target)}“")

    # ================================================================ Abend: Stufen, Beamer, Timer, Gewinner

    def _advance_stage(self, _button=None) -> None:
        if not self.service.game.cards:
            return
        _following, new_round = next_stage(self.service.win_target)
        if new_round:
            detail = ("Die Ziehung wird neu gemischt und beginnt wieder mit "
                      f"„{WIN_TARGET_LABELS[self.service.round_start_target]}“. "
                      "Die gedruckten Karten bleiben gültig, die Gewinnerliste bleibt erhalten.")
            if self.follow_switch.get_active() and self.player is not None and self.player.is_playing():
                # Im Folgen-Modus zählt alles, was läuft – auch der Titel, der gerade noch aus der alten Runde spielt
                detail += ("\n\nPlayer folgen ist an: Der gerade laufende Titel zählt sofort als erster Song der "
                           "neuen Runde. Soll sie später beginnen, vorher im Player pausieren.")
            if not dialogs.confirm(self, f"Runde {self.service.round_number + 1} starten?", detail, "Neue Runde"):
                return
        self.service.advance_stage()
        self._sync_win_buttons()
        self.timer.stop()
        self.timer_hold = False
        self.banner = ""
        self._set_revealed(False)
        if new_round:
            self._stop_all_playback()
            self.last_track_identity = ""
        self._save()
        self._render_caller()
        self._set_status(f"Runde {self.service.round_number} · Ziel: {WIN_TARGET_LABELS[self.service.win_target]}")

    def _sync_win_buttons(self) -> None:
        self._loading_state = True
        try:
            self.win_buttons[self.service.win_target].set_active(True)
        finally:
            self._loading_state = False

    def _set_revealed(self, value: bool) -> None:
        self.revealed = bool(value)
        if hasattr(self, "reveal_button") and self.reveal_button.get_active() != self.revealed:
            self.reveal_button.handler_block_by_func(self._reveal_toggled)
            self.reveal_button.set_active(self.revealed)
            self.reveal_button.handler_unblock_by_func(self._reveal_toggled)
        self._update_beamer()

    def _beamer_reveal_changed(self, _button) -> None:
        if self._loading_state:
            return
        self.service.beamer_reveal = self.beamer_reveal_check.get_active()
        self._sync_reveal_button()
        self._save()
        self._update_beamer()
        self._set_status("Titel werden auf dem Beamer aufgedeckt" if self.service.beamer_reveal
                         else "Titel bleiben auf dem Beamer verborgen")

    def _sync_reveal_button(self) -> None:
        """„Titel aufdecken (T)“ ist nur bedienbar, wenn der Beamer Titel überhaupt zeigen darf."""
        allowed = self.beamer_reveal_check.get_active()
        self.reveal_button.set_sensitive(allowed)
        self.reveal_button.set_tooltip_text(
            "" if allowed else "Aufdecken ist aus („Titel auf dem Beamer aufdecken“).")

    def _reveal_toggled(self, button: Gtk.ToggleButton) -> None:
        self.revealed = button.get_active()
        self._update_beamer()

    def _beamer_toggled(self, button: Gtk.ToggleButton) -> None:
        if button.get_active() and self.beamer is None:
            self.beamer = BeamerWindow(self)
            self.beamer.connect("delete-event", self._beamer_closed)
            self.beamer.show_all()
            if not self.beamer.place_on_second_monitor(self):
                self._set_status("Beamer-Fenster geöffnet – auf den Beamer ziehen und doppelklicken (Vollbild).")
            self._update_beamer()
            button.set_label("Beamer schließen")
        elif not button.get_active() and self.beamer is not None:
            beamer, self.beamer = self.beamer, None
            beamer.destroy()
            button.set_label("Beamer öffnen")

    def _beamer_closed(self, *_args) -> bool:
        self.beamer = None
        self.beamer_button.set_active(False)
        self.beamer_button.set_label("Beamer öffnen")
        return False

    def _update_beamer(self) -> None:
        if hasattr(self, "timer_label"):
            self.timer_label.set_text(self.timer.label())
            self.timer_pause_button.set_label("Weiter (P)" if self.timer.paused else "Pause (P)")
            self.timer_pause_button.set_sensitive(self.timer.phase != "aus")
        if self.beamer is not None:
            timer_text = self.timer.label() if self.timer.phase != "aus" else ""
            self.beamer.update(build_beamer_state(self.service, self.revealed, timer_text, self.banner))

    def _restart_timer_in_follow(self) -> None:
        """Folgen-Modus: Auch bei bereits gezogenem/fremdem Titel weiterzählen, sonst bleibt der Timer stehen."""
        if (self.follow_switch.get_active() and self.timer.enabled and self.timer.phase == "aus"
                and not self.timer_hold):
            self.timer.start()

    def _modal_dialog_open(self) -> bool:
        return any(top is not self and top is not self.beamer and top.get_visible() and top.get_modal()
                   for top in Gtk.Window.list_toplevels())

    def _timer_tick(self) -> bool:
        if self.closing:
            self.timer_source = 0
            return False
        try:
            self._timer_step()
        except Exception as error:  # noqa: BLE001 – eine Ausnahme würde den Sekundentakt für immer beenden
            self._set_status(f"Song-Timer: Fehler beim Weiterschalten ({error})")
        return True

    def _timer_step(self) -> bool:
        if self._modal_dialog_open():
            return True  # Rückfrage/Dialog offen: Timer steht, nichts passiert im Hintergrund
        phase_before = self.timer.phase
        event = self.timer.tick()
        if event == "reveal":
            self._set_revealed(True)
            self._pause_after_timer()
        elif event == "next":
            caller = self.service.game.caller
            more = len(caller.drawn) < len(caller.pool)
            upcoming = caller.order[caller.index + 1] if more else None
            # Auflösung 0 s: Die Spielzeit endet direkt mit dem nächsten Ziehen. Pausieren, außer der
            # nächste Song startet sicher automatisch (dann übernimmt Spotify bzw. GStreamer den Wechsel).
            if phase_before == "läuft" and not self._starts_automatically(upcoming):
                self._pause_after_timer()
            if self.follow_switch.get_active() or more:
                self._draw_next(by_timer=True)
            else:
                self._set_status("Alle Songs gespielt – Timer angehalten.")
        if event or self.timer.phase != "aus":
            self._update_beamer()
        return True

    def _starts_automatically(self, song: Song | None) -> bool:
        """Spielt das Ziehen dieses Songs ihn sofort ab? Nur dann ersetzt er den laufenden Titel.

        Ohne Spotify-Link öffnet Spotify nur die Suche – der alte Titel liefe sonst weiter.
        """
        if song is None or not self.service.auto_play:
            return False
        target = self.service.playback_target
        if target == "spotify":
            return is_spotify(song.link)
        if target == "lokal":
            return bool(self.audio_player and self.service.audio_file_for(song))
        return False

    def _toggle_timer_pause(self, _button=None) -> None:
        if self.timer.paused:
            self.timer.resume()
        else:
            self.timer.pause()
        self._update_beamer()

    def _timer_settings_changed(self, *_args) -> None:
        if self._loading_state:
            return
        seconds, reveal = self.timer_spin.get_value_as_int(), self.reveal_spin.get_value_as_int()
        was_enabled = self.timer.enabled
        self.service.set_timer(seconds, reveal)
        self.timer.configure(seconds, reveal)
        if not self.timer.enabled and self.warning_kind == "autoplay":
            self._hide_warning()  # Timer aus: nichts zieht mehr von selbst weiter
        if self.timer.enabled and not was_enabled:
            self.autoplay_hint_dismissed = False  # Timer neu eingeschaltet: der Hinweis darf wieder kommen
        self._save()
        self._update_beamer()

    def _title_changed(self, entry: Gtk.Entry) -> None:
        if self._loading_state:
            return
        self.service.set_event_title(entry.get_text())
        self.header.set_subtitle(f"{self.service.event_title} · offline")
        self._update_beamer()
        self._render_cards()
        if self.song_save_source:
            GLib.source_remove(self.song_save_source)
        self.song_save_source = GLib.timeout_add(650, self._save_song_edits)

    def _render_winners(self) -> None:
        if not hasattr(self, "winners_list"):
            return
        for child in self.winners_list.get_children():
            self.winners_list.remove(child)
        if not self.service.winners:
            self.winners_list.add(label("Noch keine Gewinner.", "muted", "small"))
        for index, winner in enumerate(self.service.winners):
            row = Gtk.Box(spacing=8)
            text = (f"Runde {winner.round} · {winner.target_label} · Karte #{winner.card}"
                    + (f" · {winner.name}" if winner.name else "") + f" · nach {winner.song_count} Songs")
            row.pack_start(label(text, wrap=True), True, True, 0)
            remove = Gtk.Button.new_from_icon_name("edit-delete-symbolic", Gtk.IconSize.BUTTON)
            remove.set_tooltip_text("Eintrag löschen (z. B. bei Versehen)")
            add_class(remove, "flat")
            remove.connect("clicked", self._remove_winner, index)
            row.pack_end(remove, False, False, 0)
            self.winners_list.add(row)
        self.winners_list.show_all()

    def _render_target_status(self) -> None:
        """Gewinnkontrolle: Karten mit erreichtem Ziel als Knöpfe, die direkt die Bingo-Prüfung öffnen."""
        if not hasattr(self, "target_cards"):
            return
        for child in self.target_cards.get_children():
            self.target_cards.remove(child)
        game = self.service.game
        target = WIN_TARGET_LABELS[self.service.win_target]
        if not game.cards or not game.caller.drawn:
            self.target_status_label.set_text(f"Ziel: {target} · Noch kein Song gezogen.")
            self.target_cards.show_all()
            return
        status = self.service.target_status()
        parts = [f"Ziel: {target}"]
        if status.reached:
            count = len(status.reached)
            parts.append(f"{count} Karte hat das Ziel erreicht" if count == 1
                         else f"{count} Karten haben das Ziel erreicht – Gleichstand")
        else:
            parts.append("noch keine Karte am Ziel")
        if status.entered:
            parts.append("eingetragen: " + ", ".join(f"#{number}" for number in status.entered))
        if status.one_missing:
            parts.append(f"{status.one_missing} Karte{'' if status.one_missing == 1 else 'n'} "
                         "fehlt nur noch ein Song")
        self.target_status_label.set_text(" · ".join(parts))
        for number in status.reached[:40]:
            button = self._button(f"Karte #{number} prüfen", self._check_reached_card, "primary",
                                  tooltip="Öffnet die Bingo-Prüfung für diese Karte")
            button.card_number = number
            self.target_cards.add(button)
        if len(status.reached) > 40:
            self.target_cards.add(label(f"… und {len(status.reached) - 40} weitere", "muted", "small"))
        self._no_focus_on_click(self.target_cards)
        self.target_cards.show_all()

    def _check_reached_card(self, button: Gtk.Button) -> None:
        was_paused = self.timer.paused
        self.timer.pause()  # während der Prüfung zählt der Timer nicht weiter
        try:
            self._show_card_result(button.card_number)
        finally:
            if not was_paused and not self.timer_hold:
                self.timer.resume()
            self._update_beamer()

    def _remove_winner(self, _button, index: int) -> None:
        if not 0 <= index < len(self.service.winners):
            return
        winner = self.service.winners[index]
        if dialogs.confirm(self, "Gewinner löschen?",
                           f"Karte #{winner.card} ({winner.target_label}, Runde {winner.round})", "Löschen"):
            self.service.remove_winner(index)
            self._save()
            self._render_winners()
            self._render_target_status()

    def _export_winners(self, _button) -> None:
        if not self.service.winners:
            dialogs.message(self, Gtk.MessageType.INFO, "Keine Gewinner", "Die Gewinnerliste ist noch leer.")
            return
        dialog = Gtk.FileChooserDialog(title="Gewinnerliste exportieren", transient_for=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Exportieren", Gtk.ResponseType.ACCEPT)
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name("gewinner.csv")
        filename = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if not filename:
            return
        try:
            Path(filename).write_text(winners_csv(self.service.winners, self.service.event_title), encoding="utf-8")
        except OSError as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Export fehlgeschlagen", str(error))
            return
        self._set_status(f"Gewinnerliste exportiert: {Path(filename).name}")

    # ================================================================ Wiedergabe

    def _win_target_changed(self, button: Gtk.RadioButton, key: str) -> None:
        if not button.get_active() or self._loading_state:
            return
        self.service.set_win_target(key)
        self._save()
        self._render_caller()
        self._set_status(f"Gewinnziel: {WIN_TARGET_LABELS[key]}")

    def _target_changed(self, button: Gtk.RadioButton, key: str) -> None:
        if not button.get_active():
            return
        if self._loading_state:
            return
        if self.audio_player:
            self.audio_player.stop()
        self._cancel_playback()
        if self.warning_kind == "autoplay":
            self._hide_warning()  # gehörte zum alten Wiedergabeziel
        self.autoplay_hint_dismissed = False
        self.service.set_playback_target(key)
        if self.player and not self.follow_switch.get_active() and not self._player_fits_target(self.player.info):
            self._disconnect_player()
        if key == "lokal" and self.follow_switch.get_active():
            self.follow_switch.set_active(False)
        elif self.player and self.follow_switch.get_active():
            # Anderes Ziel → passenden Player neu wählen.
            self._disconnect_player()
            if not self._connect_player(quiet=False):
                self.follow_switch.set_active(False)
        self._save()
        self._render_caller()

    def _update_audio_controls(self, status_text: str | None = None) -> None:
        if not hasattr(self, "audio_status"):
            return
        caller = self.service.game.caller
        song = caller.current
        target = self.service.playback_target
        follow = self.follow_switch.get_active()
        if target == "lokal":
            path_text = self.service.audio_file_for(song)
            path = Path(os.path.expanduser(path_text)) if path_text else None
            file_exists = is_readable_file(path_text)
            available = self.audio_player is not None
            if not available:
                detail = self.audio_error or "Lokaler Audioplayer nicht verfügbar."
            elif song is None:
                detail = "Ziehe einen Song, um die passende Audiodatei abzuspielen."
            elif not path:
                detail = "Für diesen Song ist noch keine Audiodatei zugeordnet."
            elif not file_exists:
                detail = f"Audiodatei nicht gefunden: {path.name}"
            else:
                detail = f"Audiodatei bereit: {path.name}"
            playing = available and self.audio_player.is_playing
            self.audio_play_button.set_sensitive(available and song is not None and file_exists)
            self.audio_pause_button.set_sensitive(playing)
            self.audio_pause_button.set_label("Fortsetzen" if playing and self.audio_player.is_paused else "Pause")
            self.audio_stop_button.set_sensitive(playing)
            self.audio_assign_button.set_visible(True)
            self.audio_assign_button.set_sensitive(song is not None)
            self.audio_assign_button.set_label("Datei ersetzen …" if path_text else "Datei zuordnen …")
            self.auto_play_check.set_sensitive(available and bool(caller.pool))
            self.pause_after_check.set_sensitive(True)
            self.spotify_test_button.set_visible(False)
        else:
            name = TARGET_LABELS[target]
            if self.player:
                detail = f"Verbunden mit {self.player.info.identity}"
                if self.now_playing:
                    detail += f" · läuft: {self.now_playing.label}"
            elif target == "spotify":
                detail = ("Spotify-Desktop-App nicht gestartet – Titel werden über "
                          + ("die Spotify-App geöffnet." if self.spotify_scheme else "den Spotify-Webplayer im Browser geöffnet."))
            else:
                detail = ("„Abspielen“ öffnet das Video im Standardbrowser. Für automatisches Mitziehen "
                          "„Player folgen“ einschalten.")
            if follow:
                detail = (f"Folgen aktiv: Die Playlist läuft in {self.player.info.identity if self.player else name}; "
                          "die App zieht den laufenden Song automatisch.")
            self.audio_play_button.set_sensitive(song is not None and not follow)
            self.audio_pause_button.set_label("Pause/Weiter")
            self.audio_pause_button.set_sensitive(self.player is not None)
            self.audio_stop_button.set_sensitive(self.player is not None)
            self.audio_assign_button.set_visible(False)
            self.auto_play_check.set_sensitive(not follow and bool(caller.pool))
            self.pause_after_check.set_sensitive(target == "spotify" and not follow)
            self.spotify_test_button.set_visible(target == "spotify")
            self.spotify_test_button.set_sensitive(not follow and not self.spotify_test_running)
        self.audio_status.set_text(status_text or detail)
        self._update_summary()

    def _autoplay_changed(self, _button) -> None:
        if self._loading_state:
            return
        self.service.auto_play = self.auto_play_check.get_active()
        if self.service.auto_play and self.warning_kind == "autoplay":
            self._hide_warning()  # Haken von Hand gesetzt: der Hinweis ist erledigt
        self._save()

    def _pause_after_changed(self, _button) -> None:
        if self._loading_state:
            return
        self.service.pause_after_timer = self.pause_after_check.get_active()
        self._save()

    def _pause_after_timer(self) -> None:
        """Spielzeit abgelaufen (Übergang zur Auflösung): Musik anhalten – nicht im Folgen-Modus, nicht bei YouTube."""
        if not self.service.pause_after_timer or self.follow_switch.get_active():
            return
        target = self.service.playback_target
        if target == "spotify":
            self._cancel_playback()  # sonst könnte die Kontrolle danach noch „Play“ senden
            if self.player and self.player.info.is_spotify:
                self.player.pause(on_error=lambda m: self._set_status(f"Spotify reagiert nicht: {m}"))
                self._set_status("Spielzeit abgelaufen – Spotify pausiert.")
            elif self.warning_kind != "autoplay":
                # Titel lief über Webplayer/spotify:-Link – ohne Verbindung kann die App nicht pausieren.
                # (Mit dem Hinweis „Musik startet nicht von selbst“ hat die App gar nichts gestartet.)
                self._set_status("Spielzeit abgelaufen – Spotify ist nicht verbunden, bitte von Hand pausieren.")
        elif target == "lokal" and self.audio_player and self.audio_player.is_playing \
                and not self.audio_player.is_paused:
            try:
                self.audio_player.pause()
            except RuntimeError as error:
                self._audio_failed(str(error))
                return
            self._update_audio_controls("Spielzeit abgelaufen – Wiedergabe pausiert.")

    def _play_audio(self, _button, automatic: bool = False) -> None:
        song = self.service.game.caller.current
        if song is None:
            return
        target = self.service.playback_target
        if target == "lokal":
            path_text = self.service.audio_file_for(song)
            if not path_text or not self.audio_player:
                return
            try:
                self.audio_player.play(Path(path_text))
                self._set_status(f"Spiele: {song.display_name}")
            except (OSError, RuntimeError, ValueError) as error:
                self._audio_failed(str(error))
                return
            self._update_audio_controls(f"Wiedergabe: {Path(path_text).name}")
            return
        self._cancel_playback_check()
        if target == "spotify":
            self._keep_in_front()
        if target == "spotify" and self.player is None:
            self._connect_player(quiet=True)
        spotify_mpris = bool(self.player and self.player.info.is_spotify)
        if target == "spotify" and not spotify_mpris and is_spotify(song.link):
            # Spotify läuft nicht: Desktop-App starten und auf sie warten, statt nur den Link abzugeben.
            generation = self.play_generation
            if self._ensure_spotify(lambda found: self._spotify_ready_for(found, song, generation)):
                self._keep_in_front(grace=REFOCUS_AUTOSTART_S)
                text = f"Spotify wird gestartet … ({song.display_name})"
                self._set_status(text)
                self._update_audio_controls(text)
                return
        plan = plan_launch(song, target, spotify_mpris, self.spotify_scheme)

        def fallback(message: str, no_reply: bool = False) -> None:
            # Spotify-App lehnte OpenUri ab oder antwortet nicht: Titel über das System öffnen –
            # ohne spotify:-Handler im Webplayer.
            try:
                open_uri(plan_launch(song, "spotify", False, self.spotify_scheme).uri)
            except RuntimeError as error:
                self._set_status(str(error))
                return
            if no_reply:
                text = f"Spotify reagiert nicht – Titel stattdessen geöffnet: {song.display_name}"
                self._set_status(text)
                self._update_audio_controls(text)
                return
            self._set_status(f"Spotify-Steuerung meldete „{message}“ – Titel stattdessen geöffnet.")

        try:
            if plan.method == "mpris" and self.player:
                self._start_playback_check(song, plan.uri, fallback)
            else:
                open_uri(plan.uri)
        except RuntimeError as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Konnte nicht geöffnet werden", str(error))
            return
        if plan.method != "mpris":
            self._set_status(f"{plan.description}: {song.display_name}")

    # ---------------------------------------------------------------- Spotify: Kontrolle & Autostart

    def _start_playback_check(self, song: Song, uri: str, fallback) -> None:
        """OpenUri senden und asynchron prüfen, ob Spotify genau diesen Titel spielt."""
        generation = self.play_generation

        def done(result: str, detail: str) -> None:
            if generation != self.play_generation:
                return
            if result == spotify.PlaybackCheck.FAILED:
                # Kontrolle beobachtet weiter (playback_check bleibt, damit ein neuer Song sie abbricht).
                self._show_spotify_warning(song)
                return
            self.playback_check = None
            if result == spotify.PlaybackCheck.PLAYING:
                # z. B. nach einem erneuten „Abspielen“: die alte Warnung ist damit erledigt
                if self.warning_kind == "spotify":
                    self._hide_warning()
                text = f"Läuft in Spotify: {song.display_name}"
                self._set_status(text)
                self._update_audio_controls(text)
            elif result == spotify.PlaybackCheck.LATE_PLAYING:
                # Spotify war nur langsam: Warnung zurücknehmen.
                if self.warning_kind == "spotify":
                    self._hide_warning()
                text = f"Läuft jetzt in Spotify: {song.display_name}"
                self._set_status(text)
                self._update_audio_controls(text)
            elif result == spotify.PlaybackCheck.NO_REPLY:
                fallback(detail, no_reply=True)
            else:
                fallback(detail)
        self._set_status(f"Spotify startet den Titel …: {song.display_name}")
        self.playback_check = spotify.PlaybackCheck(self.player, uri, done, timeout_ms=self.playback_check_ms,
                                                    song=song)
        self.playback_check.start()

    # ---------------------------------------------------------------- Steuerung vorn behalten

    def _own_window_active(self) -> bool:
        """Hat ein Fenster der App den Fokus (Hauptfenster, Dialog, Beamer)?"""
        return any(window.is_active() for window in Gtk.Window.list_toplevels()
                   if window is self or window is self.beamer or window.get_transient_for() is self)

    def _keep_in_front(self, grace: float = 0.0) -> None:
        """Nach dem Start eines Titels in Spotify die Steuerung zurück nach vorn holen.

        Nur wenn die Spielleitung gerade in der App arbeitet (sie hat den Fokus, oder ein Spotify-Autostart
        läuft noch) – wer bewusst in ein anderes Fenster gewechselt ist, wird nicht gestört.
        """
        now = time.monotonic()
        if not self.get_visible() or not (self._own_window_active() or now < self.refocus_until):
            return
        self.refocus_until = max(self.refocus_until, now + grace)
        self.refocus_generation += 1
        generation = self.refocus_generation
        for delay in REFOCUS_DELAYS_MS:
            GLib.timeout_add(delay, self._refocus, generation)

    def _refocus(self, generation: int) -> bool:
        if generation == self.refocus_generation and self.get_visible() and not self._own_window_active():
            self.present_with_time(self._server_time())
        return False

    def _server_time(self) -> int:
        """Aktuelle X-Serverzeit: Damit akzeptiert der Fenstermanager das Nach-vorn-Holen als neueste Aktion."""
        try:
            gi.require_version("GdkX11", "3.0")
            from gi.repository import GdkX11
            window = self.get_window()
            if isinstance(window, GdkX11.X11Window):
                return GdkX11.x11_get_server_time(window)
        except (ImportError, ValueError, AttributeError):
            pass
        return Gtk.get_current_event_time()

    def _cancel_playback_check(self) -> None:
        if self.playback_check is not None:
            check, self.playback_check = self.playback_check, None
            check.cancel()

    def _cancel_playback(self) -> None:
        """Neuer Song (oder Ziel gewechselt): laufende Kontrolle, Start-Aufträge und alte Spotify-Warnung verwerfen."""
        self.play_generation += 1
        self._cancel_playback_check()
        if self.spotify_test_running:
            self._finish_spotify_test(cancelled=True)
        if self.warning_kind == "spotify":
            self._hide_warning()

    def _show_spotify_warning(self, song: Song) -> None:
        self.unmatched_track = None
        self.warning_kind = "spotify"
        self.warning_label.set_markup(
            "<b>Spotify hat den Titel nicht gestartet – bitte in Spotify prüfen</b>\n"
            f"{escape(song.display_name)}")
        self.warning_skip_button.set_visible(False)
        self.warning_autoplay_button.set_visible(False)
        self.warning_revealer.set_reveal_child(True)
        self._set_status(f"Spotify hat den Titel nicht gestartet: {song.display_name}")

    def _ensure_spotify(self, callback) -> bool:
        """Spotify-Desktop-App starten und asynchron auf sie warten.

        ``callback(gefunden)`` kommt, sobald sich Spotify am Bus meldet oder die Wartezeit abläuft.
        Rückgabe False: keine Spotify-App installiert (oder Start gescheitert) – der Aufrufer fällt zurück.
        """
        if self.spotify_waiter is not None and self.spotify_waiter.active:
            self.spotify_waiter_callbacks.append(callback)
            return True
        if not spotify.launch_desktop_app():
            return False
        self.spotify_waiter_callbacks = [callback]
        self.spotify_waiter = spotify.NameWaiter(spotify.BUS_NAME, self.spotify_start_timeout_ms,
                                                 self._spotify_wait_done)
        self.spotify_waiter.start()
        return True

    def _spotify_wait_done(self, appeared: bool) -> None:
        self.spotify_waiter = None
        callbacks, self.spotify_waiter_callbacks = self.spotify_waiter_callbacks, []
        if self.closing:
            return
        for callback in callbacks:
            callback(appeared)

    def _spotify_ready_for(self, appeared: bool, song: Song, generation: int) -> None:
        if generation != self.play_generation or self.service.game.caller.current != song:
            return  # inzwischen wurde ein anderer Song gezogen
        if appeared and self.player is None:
            self._connect_player(quiet=True)
        if appeared and self.player and self.player.info.is_spotify:
            self._play_audio(None, automatic=True)
            return
        plan = plan_launch(song, "spotify", False, self.spotify_scheme)
        try:
            open_uri(plan.uri)
        except RuntimeError as error:
            self._set_status(str(error))
            return
        self._set_status(f"Spotify hat sich nicht gemeldet – {plan.description}: {song.display_name}")
        self._update_audio_controls()

    # ---------------------------------------------------------------- Spotify testen

    def _spotify_test(self, _button=None) -> None:
        if self.spotify_test_running:
            return
        self.spotify_test_running = True
        self._update_audio_controls("Spotify-Test läuft …")
        self._set_status("Spotify-Test läuft …")
        players = mpris.list_players()  # nur einmal abfragen: ein hängender Player kostet jedes Mal Zeit
        if any(p.is_spotify for p in players):
            self._spotify_test_found(True, players)
        elif not self._ensure_spotify(self._spotify_test_found):
            self._spotify_test_found(False)
        else:
            self._update_audio_controls("Spotify-Test: Spotify wird gestartet …")

    def _spotify_test_found(self, found: bool, players: list[mpris.PlayerInfo] | None = None) -> None:
        if not self.spotify_test_running or self.spotify_self_test is not None:
            return
        if found and players is None:
            players = mpris.list_players()
        info = mpris.choose_player(players, target="spotify") if found else None
        if info is None:
            self._spotify_test_result(found=False)
            return
        try:
            self.spotify_test_player = mpris.MprisPlayer(info)
        except RuntimeError:
            self._spotify_test_result(found=False)
            return
        songs, _mode = self._active_or_draft_songs()
        caller = self.service.game.caller
        song = pick_test_song(caller.current, songs, caller.drawn)
        self.spotify_test_notes = [NO_TEST_SONG_NOTE] if song is None and caller.drawn else []
        self.spotify_self_test = spotify.SelfTest(self.spotify_test_player, song.link if song else "",
                                                  self._spotify_test_done, check_timeout_ms=self.playback_check_ms,
                                                  song=song)
        self.spotify_self_test.start()

    def _spotify_test_done(self, outcome: spotify.SelfTestOutcome) -> None:
        self.spotify_self_test = None
        if not outcome.responding:
            self.spotify_test_notes.append(NO_REPLY_NOTE)
        self._spotify_test_result(True, outcome.can_control, outcome.started, outcome.paused)

    def _finish_spotify_test(self, cancelled: bool = False) -> None:
        # Wartet der Test noch auf den Spotify-Start, darf er danach nicht mehr loslaufen
        # (sonst liefe nach einem Neustart des Tests ein zweiter, verwaister Test mit).
        if self._spotify_test_found in self.spotify_waiter_callbacks:
            self.spotify_waiter_callbacks.remove(self._spotify_test_found)
        if self.spotify_self_test is not None:
            test, self.spotify_self_test = self.spotify_self_test, None
            test.cancel()
        if self.spotify_test_player is not None:
            self.spotify_test_player.close()
            self.spotify_test_player = None
        self.spotify_test_running = False
        if cancelled:
            self._set_status("Spotify-Test abgebrochen.")
        self._update_audio_controls()

    def _spotify_test_result(self, found: bool, can_control: bool = False, started: bool = False,
                             paused: bool = False) -> None:
        if not self.spotify_test_running:
            return
        self._finish_spotify_test()
        songs, _mode = self._active_or_draft_songs()
        items = checklist(found, can_control, started, paused, count_spotify_links(songs), len(songs))
        notes, self.spotify_test_notes = self.spotify_test_notes, []
        self._set_status("Spotify-Test beendet.")
        dialogs.message(self, Gtk.MessageType.INFO if all(ok for ok, _ in items) else Gtk.MessageType.WARNING,
                        "Spotify-Test", report(items, notes))

    def _pause_audio(self, _button) -> None:
        if self.service.playback_target != "lokal":
            self._cancel_playback_check()
            if self.player:
                self.player.play_pause()
            return
        if not self.audio_player or not self.audio_player.is_playing:
            return
        try:
            if self.audio_player.is_paused:
                self.audio_player.resume()
            else:
                self.audio_player.pause()
        except RuntimeError as error:
            self._audio_failed(str(error))
            return
        self._update_audio_controls("Wiedergabe pausiert." if self.audio_player.is_paused else "Wiedergabe läuft.")

    def _stop_audio(self, _button=None) -> None:
        if self.service.playback_target != "lokal":
            self._cancel_playback_check()
            if self.player:
                self.player.pause()
            return
        if self.audio_player:
            self.audio_player.stop()
        self._update_audio_controls("Wiedergabe gestoppt.")

    def _stop_all_playback(self) -> None:
        if self.audio_player:
            self.audio_player.stop()

    def _assign_audio_file(self, _button) -> None:
        song = self.service.game.caller.current
        if song is None:
            return
        dialog = Gtk.FileChooserDialog(title=f"Audiodatei für {song.title} auswählen", transient_for=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Auswählen", Gtk.ResponseType.ACCEPT)
        audio_filter = Gtk.FileFilter()
        audio_filter.set_name("Audiodateien")
        for suffix in ("*.aac", "*.flac", "*.m4a", "*.mp3", "*.oga", "*.ogg", "*.opus", "*.wav"):
            audio_filter.add_pattern(suffix)
            audio_filter.add_pattern(suffix.upper())
        dialog.add_filter(audio_filter)
        response = dialog.run()
        filename = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if not filename:
            return
        try:
            self.service.assign_audio_file(song, str(Path(filename).resolve()))
            self._save()
            self._render_caller()
            self._set_status(f"Audiodatei für {song.display_name} zugeordnet")
        except (OSError, ValueError) as error:
            dialogs.message(self, Gtk.MessageType.ERROR, "Audiodatei konnte nicht zugeordnet werden", str(error))

    def _audio_finished(self) -> None:
        self._update_audio_controls("Wiedergabe beendet.")

    def _audio_failed(self, detail: str) -> None:
        if hasattr(self, "audio_status"):
            self._update_audio_controls(f"Wiedergabe fehlgeschlagen: {detail}")
            self._set_status("Audiodatei konnte nicht abgespielt werden")

    # ================================================================ Externer Player / Folgen

    def _player_fits_target(self, info: mpris.PlayerInfo) -> bool:
        target = self.service.playback_target
        if target == "spotify":
            return info.is_spotify
        if target == "youtube":
            return info.is_browser
        return True

    def _connect_player(self, quiet: bool) -> bool:
        if self.player is not None:
            if self._player_fits_target(self.player.info):
                return True
            self._disconnect_player()
        players = mpris.list_players()
        target = self.service.playback_target
        info = mpris.choose_player(players, self.service.player_name, target)
        if info is None:
            if not quiet:
                what = {"spotify": "Spotify (Desktop-App)", "youtube": "YouTube im Browser"}.get(target, "den Player")
                dialogs.message(self, Gtk.MessageType.INFO, "Kein passender Player gefunden",
                                f"Starte {what} und die Playlist, dann erneut einschalten."
                                + (f"\n\nGefunden wurden: {', '.join(p.identity for p in players)}" if players else ""))
            return False
        try:
            self.player = mpris.MprisPlayer(info, on_change=self._player_changed)
        except RuntimeError as error:
            if not quiet:
                dialogs.message(self, Gtk.MessageType.ERROR, "Player nicht erreichbar", str(error))
            return False
        self.service.player_name = info.bus_name
        self.player_watch = Gio.bus_watch_name(Gio.BusType.SESSION, info.bus_name, Gio.BusNameWatcherFlags.NONE,
                                               lambda *_args: None, self._player_vanished)
        self.player_poll = GLib.timeout_add_seconds(2, self._poll_player)
        self.last_track_identity = ""
        self._player_changed()
        return True

    def _disconnect_player(self) -> None:
        self._cancel_playback_check()
        if self.player_poll:
            GLib.source_remove(self.player_poll)
            self.player_poll = 0
        if self.player_watch:
            Gio.bus_unwatch_name(self.player_watch)
            self.player_watch = 0
        if self.player:
            self.player.close()
            self.player = None
        self.now_playing = None

    def _player_vanished(self, *_args) -> None:
        name = self.player.info.identity if self.player else "Player"
        self._disconnect_player()
        was_following = self.follow_switch.get_active()
        if was_following:
            self.follow_switch.set_active(False)
        self._set_status(f"{name} wurde beendet – Player folgen ausgeschaltet.")
        self._render_caller()
        if was_following:
            dialogs.message(self, Gtk.MessageType.WARNING, f"{name} wurde beendet",
                            "Player folgen und Song-Timer sind angehalten, es wird nichts mehr automatisch gezogen.\n"
                            "Player neu starten, Playlist abspielen und „Player folgen“ wieder einschalten.")

    def _poll_player(self) -> bool:
        # Manche Player (v. a. Browser) melden Titelwechsel nicht zuverlässig.
        if self.player is None:
            self.player_poll = 0
            return False
        player = self.player

        def received(state: dict) -> None:
            if self.player is not player:
                return
            status = state.get("PlaybackStatus")
            if isinstance(status, str):
                player.proxy.set_cached_property("PlaybackStatus", GLib.Variant("s", status))
            metadata = state.get("Metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            if mpris.track_identity(metadata) != self.last_track_identity:
                self._handle_metadata(metadata)
        player.fetch_state(received)
        return True

    def _player_changed(self) -> None:
        if self.player is not None:
            self._handle_metadata(self.player.metadata())

    def _handle_metadata(self, metadata: dict) -> None:
        identity = mpris.track_identity(metadata)
        if (self.follow_switch.get_active() and self.player is not None and not self.player.is_playing()
                and identity != self.last_track_identity):
            # Nur laufende Titel ziehen. Ein pausiert geladener Titel (vom Vortag, nach „Spotify testen“) wurde sonst
            # sofort als gespielt gezählt. last_track_identity bleibt stehen: Startet der Titel, kommt die
            # Statusänderung hier erneut an und er wird gezogen.
            self.now_playing = mpris.track_from_metadata(metadata)
            self._update_audio_controls()
            self._update_source_chip()
            return
        if identity == self.last_track_identity:
            return
        self.last_track_identity = identity
        track = mpris.track_from_metadata(metadata)
        self.now_playing = track
        if track is None:
            self._update_audio_controls()
            self._update_source_chip()
            return
        if self.follow_switch.get_active():
            self._follow_track(track)
        else:
            self._update_audio_controls()

    def _follow_track(self, track: PlayingTrack) -> None:
        caller = self.service.game.caller
        song = SongMatcher(caller.pool).find(track)
        if song is None:
            self.unmatched_track = track
            self.warning_kind = "follow"
            self.warning_skip_button.set_visible(True)
            self.warning_autoplay_button.set_visible(False)
            self.warning_label.set_markup(
                f"<b>Läuft im Player, steht aber nicht auf den Karten:</b>\n{escape(track.label)}\n"
                "<small>Überspringen oder rechts per Doppelklick den passenden Song markieren.</small>")
            self.warning_revealer.set_reveal_child(True)
            self._restart_timer_in_follow()
            self._set_status(f"Nicht auf den Karten: {track.label}")
            self._update_source_chip()
            return
        self._hide_warning()
        if caller.is_drawn(song):
            self._set_status(f"Läuft erneut (bereits gezogen): {song.display_name}")
            self._restart_timer_in_follow()
            self._render_caller()
            return
        self._take_song(song, f"Aus {self.player.info.identity if self.player else 'Player'} übernommen: {song.display_name}",
                        automatic=True)

    def _skip_unmatched(self, _button) -> None:
        self._hide_warning()
        if self.player:
            self.player.next()

    def _hide_warning(self) -> None:
        self.unmatched_track = None
        self.warning_kind = ""
        if hasattr(self, "warning_revealer"):
            self.warning_revealer.set_reveal_child(False)
            self.warning_autoplay_button.set_visible(False)

    def _follow_toggled(self, switch: Gtk.Switch, _param) -> None:
        if self._loading_state:
            return
        self.timer_hold = False
        if switch.get_active():
            if not self.service.game.cards:
                dialogs.message(self, Gtk.MessageType.INFO, "Erst Karten erzeugen",
                                "Player folgen braucht eine laufende Runde mit Karten.")
                switch.set_active(False)
                return
            if self.service.playback_target == "lokal":
                self.target_buttons["spotify"].set_active(True)
            if not self._connect_player(quiet=False):
                switch.set_active(False)
                return
            self.service.follow_player = True
            if self.warning_kind == "autoplay":
                self._hide_warning()  # im Folgen-Modus spielt der Player selbst
            if self.audio_player:
                self.audio_player.stop()
            self.last_track_identity = ""
            self._player_changed()
            self._set_status(f"Folge {self.player.info.identity}: laufende Songs werden automatisch gezogen.")
        else:
            was_following = self.service.follow_player
            self.service.follow_player = False
            self._hide_warning()
            self._disconnect_player()
            # Ohne Player würde der Timer sonst Songs ziehen, die niemand hört. Ein gescheiterter
            # Einschaltversuch (kein Player) lässt einen normal laufenden Timer dagegen in Ruhe.
            if was_following and self.timer.phase != "aus":
                self.timer.stop()
                self._set_status("Player folgen aus – Song-Timer angehalten.")
        self._save()
        self._render_caller()

    # ================================================================ Einstellungen & Speichern

    def _update_field_count(self, *_args) -> None:
        if not hasattr(self, "field_count"):
            return
        size = max(3, self.size_combo.get_active() + 3)
        if size % 2 == 0 and self.free_check.get_active():
            self.free_check.set_active(False)
        self.free_check.set_sensitive(size % 2 == 1)
        free = self.free_check.get_active() and size % 2 == 1
        self.field_count.set_text(f"{size * size - int(free)} Songs je Karte")
        self._update_song_stats()
        self._save_settings()

    def _count_changed(self, *_args) -> None:
        self._update_song_stats()
        self._save_settings()

    def _update_song_stats(self) -> None:
        if not hasattr(self, "pool_count_label"):
            return
        songs = parse_songs(self._song_text())
        size = max(3, self.size_combo.get_active() + 3)
        free_space = self.free_check.get_active()
        needed = required_songs(size, free_space)
        requested = self.count_spin.get_value_as_int()
        linked = sum(1 for song in songs if song.link)
        from musik_bingo.domain.text import normalize
        seen_titles: dict[str, int] = {}
        for song in songs:
            seen_titles[normalize(song.title)] = seen_titles.get(normalize(song.title), 0) + 1
        same_titles = [song.title for song in songs if seen_titles[normalize(song.title)] > 1]
        link_text = f" · {linked} mit Link" if linked else ""
        if len(songs) < needed:
            message = f"{len(songs)} Songs · {needed} nötig · {needed - len(songs)} fehlen"
            style = "pool-warning"
        else:
            possible = unique_card_capacity(songs, size, free_space)
            if possible < requested:
                message = f"{len(songs)} Songs · nur {possible} verschiedene Karten möglich · {requested} gewünscht"
                style = "pool-warning"
            else:
                combinations = "sehr viele" if possible >= 10**6 else f"{possible}"
                message = f"✓ {len(songs)} Songs{link_text} · {needed} je Karte · {combinations} Kombinationen"
                style = "pool-ready"
        if same_titles and style == "pool-ready":
            unique = sorted(set(same_titles), key=str.casefold)
            message += f" · ⚠ gleicher Titel mehrfach: {', '.join(unique[:3])} – für Gäste kaum unterscheidbar"
            style = "pool-warning"
        context = self.pool_count_label.get_style_context()
        context.remove_class("pool-ready")
        context.remove_class("pool-warning")
        context.add_class(style)
        self.pool_count_label.set_text(message)
        self._update_link_overview()
        self._update_summary()

    def _update_summary(self) -> None:
        if not hasattr(self, "summary_values"):
            return
        caller = self.service.game.caller
        values = self.summary_values
        values["list"].set_text(f"{len(parse_songs(self._song_text()))} Songs" if hasattr(self, "song_buffer") else "–")
        values["cards"].set_text(f"{len(self.service.game.cards)}" if self.service.game.cards else "–")
        values["drawn"].set_text(f"{len(caller.drawn)} / {len(caller.pool)}" if caller.pool else "–")
        player = TARGET_LABELS[self.service.playback_target]
        if self.player:
            player = self.player.info.identity + (" · folgt" if self.follow_switch.get_active() else "")
        values["player"].set_text(player)

    def _set_page_count(self, combo: Gtk.ComboBoxText) -> None:
        self.print_per_page = 1 if combo.get_active() == 1 else 2
        if not self._loading_state:
            self.service.per_page = self.print_per_page
            self._save()

    def _song_changed(self, _buffer) -> None:
        self._update_song_stats()
        if self._loading_state:
            return
        if self.song_save_source:
            GLib.source_remove(self.song_save_source)
        self.song_save_source = GLib.timeout_add(650, self._save_song_edits)

    def _save_song_edits(self) -> bool:
        self.song_save_source = 0
        self._save_settings()
        return False

    def _save_settings(self, *_args) -> None:
        if self._loading_state or not hasattr(self, "auto_play_check"):
            return
        self.service.song_text = self._song_text()
        self.service.card_size = max(3, self.size_combo.get_active() + 3)
        self.service.free_space = self.free_check.get_active()
        self.service.card_count = self.count_spin.get_value_as_int()
        self.service.per_page = self.print_per_page
        self.service.diagonal_wins = self.diagonal_check.get_active()
        self.service.auto_play = self.auto_play_check.get_active()
        self.service.pause_after_timer = self.pause_after_check.get_active()
        self.service.beamer_reveal = self.beamer_reveal_check.get_active()
        if hasattr(self, "title_entry"):
            self.service.set_event_title(self.title_entry.get_text())
        self._save()

    def _backup(self, reason: str) -> None:
        try:
            self._save()
            target = self.store.backup(reason)
            if target:
                self._set_status(f"Sicherung angelegt: {target.name}")
        except OSError as error:
            self._set_status(f"Sicherung fehlgeschlagen: {error}")

    def _save(self) -> None:
        try:
            self.store.save(self.service)
        except (OSError, ValueError) as error:
            self._set_status(f"Lokal speichern fehlgeschlagen: {error}")
            self._show_save_problem(error)
            return
        if getattr(self, "save_failed", False):
            self.save_failed = False
            self.privacy_pill.set_text("● offline")
            self.privacy_pill.get_style_context().remove_class("pill-warn")
            self.privacy_pill.get_style_context().add_class("pill-ok")

    def _show_save_problem(self, error: Exception) -> None:
        """Bleibt sichtbar, bis wieder gespeichert werden konnte – die Statuszeile wird sofort überschrieben."""
        first = not getattr(self, "save_failed", False)
        self.save_failed = True
        if hasattr(self, "privacy_pill"):
            self.privacy_pill.set_text("⚠ NICHT GESPEICHERT")
            self.privacy_pill.get_style_context().remove_class("pill-ok")
            self.privacy_pill.get_style_context().add_class("pill-warn")
            self.privacy_pill.set_tooltip_text(f"Der Spielstand konnte nicht gespeichert werden: {error}")
        if first and not self.closing:
            # nicht aus dem laufenden Ereignis heraus (z. B. mitten im Ziehen) einen Dialog öffnen
            GLib.idle_add(lambda: dialogs.message(
                self, Gtk.MessageType.ERROR, "Spielstand wird nicht gespeichert",
                f"Der Spielstand konnte nicht in {self.store.path} geschrieben werden:\n{error}\n\n"
                "Die Runde läuft weiter, geht aber beim Schließen verloren. Bitte Speicherplatz und Rechte prüfen "
                "oder über das Menü „Spielstand exportieren“ an einen anderen Ort sichern.") or False)

    def _before_close(self, _window, _event) -> bool:
        self.closing = True
        if self.timer_source:
            GLib.source_remove(self.timer_source)
            self.timer_source = 0
        if self.beamer is not None:
            beamer, self.beamer = self.beamer, None
            beamer.destroy()
        if self.song_save_source:
            GLib.source_remove(self.song_save_source)
            self.song_save_source = 0
        if self.reader:
            self.reader.cancel()
        if self.spotify_waiter is not None:
            self.spotify_waiter.cancel()
        if self.spotify_test_running:
            self._finish_spotify_test()
        self._save_settings()
        self._disconnect_player()
        if self.audio_player:
            self.audio_player.close()
        return False

    def _set_status(self, text: str) -> None:
        self.status.set_text(text)

    def _export(self, _button) -> None:
        self._save_settings()
        dialog = Gtk.FileChooserDialog(title="Spielstand exportieren", transient_for=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Exportieren", Gtk.ResponseType.ACCEPT)
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name("musik-bingo-spielstand.json")
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            try:
                self.store.export_to(Path(dialog.get_filename()), self.service)
                self._set_status("Spielstand exportiert")
            except OSError as error:
                dialogs.message(self, Gtk.MessageType.ERROR, "Export fehlgeschlagen", str(error))
        dialog.destroy()

    def _import(self, _button) -> None:
        dialog = Gtk.FileChooserDialog(title="Spielstand importieren", transient_for=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Importieren", Gtk.ResponseType.ACCEPT)
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Musik Bingo Spielstand (*.json)")
        file_filter.add_pattern("*.json")
        dialog.add_filter(file_filter)
        response = dialog.run()
        filename = Path(dialog.get_filename()) if response == Gtk.ResponseType.ACCEPT and dialog.get_filename() else None
        dialog.destroy()
        if filename is None or not dialogs.confirm(
            self, "Spielstand ersetzen?",
            "Der ausgewählte Spielstand ersetzt Karten, Songliste, Einstellungen und Ziehfortschritt auf diesem Rechner.",
            "Ersetzen",
        ):
            return
        try:
            imported = self.store.import_from(filename)
            self._backup("vor-import")
        except Exception as error:  # noqa: BLE001 – z. B. RecursionError bei manipulierter JSON
            dialogs.message(self, Gtk.MessageType.ERROR, "Import fehlgeschlagen", str(error))
            return
        self._stop_all_playback()
        self._disconnect_player()
        self._hide_warning()
        imported.follow_player = False
        self._apply_service_to_widgets(imported)
        self._save()
        self._set_status("Spielstand importiert")

    # ================================================================ Sonstiges

    def _nav_selected(self, _listbox, row) -> None:
        if row is not None:
            self.stack.set_visible_child_name(row.page_name)

    def _select_page(self, name: str) -> None:
        self.nav.select_row(self.nav.get_row_at_index(PAGES.index(name)))

    def _toggle_theme(self, _button) -> None:
        self.theme = "light" if self.theme == "dark" else "dark"
        try:
            self.theme_path.parent.mkdir(parents=True, exist_ok=True)
            self.theme_path.write_text(self.theme, encoding="utf-8")
        except OSError as error:
            self._set_status(f"Design konnte nicht gespeichert werden: {error}")
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.css_provider.load_from_data(css_for(self.theme).encode("utf-8"))
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", self.theme == "dark")
        self.theme_item.set_property("text", "Helles Design" if self.theme == "dark" else "Dunkles Design")

    def _toggle_fullscreen(self) -> None:
        if self.is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()
        self.is_fullscreen = not self.is_fullscreen

    def _show_help(self, _button) -> None:
        dialogs.list_dialog(self, "Hilfe & Datenschutz", "Musik Bingo läuft komplett lokal auf diesem Rechner.", [
            ("Datenschutz", [
                "Die App stellt selbst keine Internetverbindung her und überträgt keine Daten.",
                "Spielstand: ~/.local/share/musik-bingo/spielstand.json (nur lokal).",
                "Vor neuen Karten oder einem Import wird automatisch gesichert: "
                "~/.local/share/musik-bingo/sicherungen/ (die letzten 10). Wiederherstellen über "
                "Menü → Spielstand importieren.",
                "Spotify/YouTube werden nur über die lokale Player-Schnittstelle (MPRIS) gesteuert oder per "
                "Klick im Browser geöffnet – wie ein selbst angeklickter Link.",
                "Chart- und Weihnachtslisten sind fest in der App gespeichert (Stand KW 47/2026).",
            ]),
            ("Bingo = Playlist", [
                "Weg A: Playlist in Spotify bauen → als CSV exportieren (z. B. Exportify) → „Playlist importieren“.",
                "Weg B: Playlist in Spotify/YouTube starten → „Vom Player einlesen“.",
                "Weg C: Zufallsmix/Liste hier bauen → „Als Playlist exportieren“ (Text) → per TuneMyMusic o. Ä. "
                "in Spotify anlegen.",
                "Vor dem Spiel: „Mit Playlist abgleichen“ zeigt fehlende oder überzählige Titel.",
                "Im Spiel: „Player folgen“ – die Playlist läuft im Player, die App zieht automatisch mit und "
                "warnt bei Titeln, die nicht auf den Karten stehen.",
            ]),
            ("Tastatur", ["Leertaste: nächster Song", "Rücktaste: Ziehung zurücknehmen",
                          "T: Titel zeigen/verbergen (auch auf dem Beamer)", "P: Song-Timer pausieren/fortsetzen",
                          "F11: Vollbild",
                          "Die Kürzel wirken auf der Spielleitung immer – außer beim Tippen im Suchfeld "
                          "oder nach Tab/Pfeiltasten (dann bedient die Leertaste das markierte Element; "
                          "ein Mausklick schaltet zurück)."]),
            ("Bingo prüfen", [
                "Mit Kartennummer: Nummer eingeben → Karte mit Gewinnlinie wird angezeigt.",
                "Ohne Kartennummer (unleserlich, fehlt): „Ohne Kartennummer …“ → die vorgelesenen Songs "
                "der Gewinnreihe anhaken → die App zeigt, ob alle gespielt sind, und findet die Karte.",
            ]),
            ("Runden & Gewinnziel", [
                "Gewinnziel oben rechts wählen. Vor dem ersten Song gewählt, beginnen auch die nächsten Runden "
                "damit – z. B. den ganzen Abend nur „Volle Karte“.",
                "„Neue Runde“ mischt neu; die gedruckten Karten und die Gewinnerliste bleiben.",
                "Nach „Als Gewinner eintragen“ bleibt der Song-Timer aus, bis du weitermachst "
                "(Leertaste oder Stufen-Knopf).",
            ]),
            ("Song-Timer & Musik", [
                "Song-Timer (s) größer 0: Nach der Spielzeit wird der Titel aufgelöst, danach zieht die App "
                "den nächsten Song.",
                "Soll die App die Songs dabei selbst starten (Spotify-Link oder lokale Datei): unter den Knöpfen "
                "„Abspielen/Pause“ den Haken „Beim Ziehen automatisch abspielen“ setzen. Ohne den Haken zieht "
                "der Timer weiter, ohne dass Musik läuft – die App weist dann darauf hin.",
                "Mit „Player folgen“ spielt der Player selbst; der Timer schaltet ihn weiter.",
            ]),
        ])

    def _on_pointer(self, _window, _event) -> bool:
        self.keyboard_navigating = False
        return False

    SHORTCUT_KEYS = (Gdk.KEY_space, Gdk.KEY_BackSpace, Gdk.KEY_t, Gdk.KEY_T, Gdk.KEY_p, Gdk.KEY_P)

    def _on_key_release(self, _window, event) -> bool:
        self._held_keys.pop(Gdk.keyval_to_lower(event.keyval), None)
        return False

    def _is_key_repeat(self, event) -> bool:
        """Tastenwiederholung des X-Servers (Taste wird gehalten): weitere Drücke ohne Loslassen.

        Nur echte Ereignisse (mit Zeitstempel). Geht das Loslassen verloren (Fokuswechsel), gilt die Taste
        nach 2 s ohne weiteren Druck wieder als frei.
        """
        if not event.time:
            return False
        key = Gdk.keyval_to_lower(event.keyval)
        last = self._held_keys.get(key)
        self._held_keys[key] = event.time
        return last is not None and 0 <= event.time - last < 2000

    def _on_key(self, _window, event) -> bool:
        if event.keyval in self.SHORTCUT_KEYS and self._is_key_repeat(event):
            focus = self.get_focus()
            if self.stack.get_visible_child_name() == "game" and not isinstance(focus, (Gtk.TextView, Gtk.Entry)):
                return True  # gehaltene Taste: nicht noch einmal ziehen/zurücknehmen/aufdecken
        if event.keyval == Gdk.KEY_F11:
            self._toggle_fullscreen()
            return True
        if event.keyval in NAVIGATION_KEYS:
            self.keyboard_navigating = True
            return False
        focus = self.get_focus()
        if self.stack.get_visible_child_name() != "game":
            return False
        if isinstance(focus, Gtk.SpinButton):
            # Zahlenfelder (Timer): Ziffern und Rücktaste gehören dem Feld, Kürzel nicht
            if event.keyval not in (Gdk.KEY_space, Gdk.KEY_t, Gdk.KEY_T, Gdk.KEY_p, Gdk.KEY_P):
                return False
        elif isinstance(focus, (Gtk.TextView, Gtk.Entry)):
            return False  # Texteingaben (Suche, Titel) bekommen jede Taste
        # Buchstaben-Kürzel gelten immer – kein Bedienelement nutzt T oder P selbst.
        if (event.keyval in (Gdk.KEY_t, Gdk.KEY_T) and self.service.game.caller.current is not None
                and self.reveal_button.get_sensitive()):
            self.reveal_button.set_active(not self.reveal_button.get_active())
            return True
        if event.keyval in (Gdk.KEY_p, Gdk.KEY_P) and self.timer.phase != "aus":
            self._toggle_timer_pause()
            return True
        # Leertaste/Rücktaste gehören einem Bedienelement nur, wenn es per Tab/Pfeiltasten gezielt
        # angesteuert wurde. Nicht has_visible_focus() nehmen: GTK schaltet die Fokus-Anzeige bei
        # JEDEM echten Tastendruck ein – dann bekam z. B. der Seitenleisten-Eintrag die Leertaste.
        if self.keyboard_navigating and isinstance(
                focus, (Gtk.Button, Gtk.Switch, Gtk.Range, Gtk.ComboBox, Gtk.ListBoxRow,
                        Gtk.FlowBoxChild, Gtk.ModelButton)):
            return False
        if event.keyval == Gdk.KEY_space and self.draw_button.get_sensitive():
            self._draw_next()
            return True
        if event.keyval == Gdk.KEY_BackSpace:
            self._undo()
            return True
        return False


class MusikBingoApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="de.weihnachtsfeier.musikbingo", flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self) -> None:
        GLib.set_application_name("Musik Bingo")
        window = self.props.active_window
        if window is None:
            window = MusikBingoWindow(self)
            window.show_all()
            window.warning_revealer.set_reveal_child(False)
            window._update_source_chip()
            window._update_audio_controls()
        window.present()


def main() -> int:
    return MusikBingoApplication().run(sys.argv)
