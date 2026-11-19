"""Beamer-Fenster für die Gäste: groß, ohne Bedienelemente, Titel erst nach Aufdecken."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango

from musik_bingo.application.beamer_state import BeamerState
from musik_bingo.presentation.dialogs import add_class, label



class BeamerWindow(Gtk.Window):
    """Zweites Fenster für Beamer/TV. F11 oder Doppelklick: Vollbild, Esc: Vollbild aus."""

    def __init__(self, parent: Gtk.Window):
        super().__init__(title="Musik Bingo – Beamer")
        self.set_default_size(1280, 720)
        self.set_transient_for(None)  # eigenständig verschiebbar (auf den Beamer)
        self.is_fullscreen = False
        self.host = parent
        root = add_class(Gtk.EventBox(), "beamer")
        self.add(root)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_border_width(48)
        box.set_valign(Gtk.Align.FILL)
        root.add(box)
        self.event_label = label("", "beamer-event", xalign=0.5)
        self.round_label = label("", "beamer-round", xalign=0.5)
        self.song_label = label("", "beamer-song", xalign=0.5)
        self.title_label = label("", "beamer-title", wrap=True, xalign=0.5)
        self.title_label.set_justify(Gtk.Justification.CENTER)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_lines(2)
        self.artist_label = label("", "beamer-artist", wrap=True, xalign=0.5)
        self.artist_label.set_justify(Gtk.Justification.CENTER)
        self.timer_label = label("", "beamer-timer", xalign=0.5)
        self.banner = add_class(Gtk.Box(), "beamer-banner")
        self.banner.set_halign(Gtk.Align.CENTER)
        self.banner_label = label("", xalign=0.5)
        self.banner.pack_start(self.banner_label, True, True, 0)
        self.recent_label = label("", "beamer-recent", wrap=True, xalign=0.5)
        self.recent_label.set_justify(Gtk.Justification.CENTER)
        box.pack_start(self.event_label, False, False, 0)
        box.pack_start(self.round_label, False, False, 0)
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        middle.set_valign(Gtk.Align.CENTER)
        for widget in (self.song_label, self.title_label, self.artist_label, self.timer_label, self.banner):
            middle.pack_start(widget, False, False, 0)
        box.pack_start(middle, True, True, 0)
        box.pack_end(self.recent_label, False, False, 0)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._on_click)
        self.connect("key-press-event", self._on_key)
        self.state: BeamerState | None = None

    def place_on_second_monitor(self, host: Gtk.Window) -> bool:
        """Öffnet auf einem anderen Bildschirm als die Spielleitung (falls vorhanden) im Vollbild."""
        display = Gdk.Display.get_default()
        host_window = host.get_window()
        if display is None or host_window is None or display.get_n_monitors() < 2:
            return False
        host_monitor = display.get_monitor_at_window(host_window)
        for index in range(display.get_n_monitors()):
            monitor = display.get_monitor(index)
            if monitor != host_monitor:
                area = monitor.get_geometry()
                self.move(area.x, area.y)
                self.fullscreen_on_monitor(self.get_screen(), index)
                self.is_fullscreen = True
                return True
        return False

    def toggle_fullscreen(self) -> None:
        if self.is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()
        self.is_fullscreen = not self.is_fullscreen

    def _on_click(self, _widget, event) -> bool:
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_fullscreen()
            return True
        return False

    def _on_key(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        if event.keyval == Gdk.KEY_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
            return True
        # Leertaste, Rücktaste, T, P auch hier – z. B. wenn der Beamer gerade den Tastaturfokus hat.
        if self.host is not None and event.keyval in (Gdk.KEY_space, Gdk.KEY_BackSpace, Gdk.KEY_t, Gdk.KEY_T,
                                                      Gdk.KEY_p, Gdk.KEY_P):
            return self.host._on_key(self.host, event)
        return False

    def update(self, state: BeamerState) -> None:
        self.state = state
        self.event_label.set_text(state.event_title.upper())
        self.round_label.set_text(state.round_line)
        self.song_label.set_text(state.song_line)
        self.title_label.set_text(state.title)
        self.title_label.set_visible(bool(state.title))
        self.artist_label.set_text(state.artist)
        self.artist_label.set_visible(bool(state.artist))
        self.timer_label.set_text(state.timer)
        self.timer_label.set_visible(bool(state.timer))
        self.banner_label.set_text(state.banner)
        self.banner.set_visible(bool(state.banner))
        self.recent_label.set_text("Zuletzt: " + " · ".join(state.recent) if state.recent else "")
