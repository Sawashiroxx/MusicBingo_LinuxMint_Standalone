"""Beamer-Fenster für die Gäste: groß, ohne Bedienelemente, Titel erst nach Aufdecken."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from musik_bingo.application.beamer_state import BeamerState
from musik_bingo.presentation.dialogs import add_class, label

# Die Schriftgrößen (theme.py) sind feste Pixelwerte. Auf kleinen Beamern (1280×720, 1024×768) passten ein
# zweizeiliger Titel mit Countdown oder das BINGO-Banner nicht mehr in die Höhe – „Zuletzt“ lag dann über dem
# Banner. Passt der Inhalt nicht, wird er deshalb stufenweise verkleinert.
SCALES = (1.0, 0.92, 0.85, 0.78, 0.72, 0.66, 0.6, 0.55, 0.5)
BORDER, SPACING, MIDDLE_SPACING = 48, 18, 16


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
        # Rollbereich ohne Leisten: Die Mindesthöhe des Fensters hängt so nicht von der Textmenge ab. GTK rechnete
        # sie sonst für die Mindestbreite aus (bis 1500 px bei langen Titeln) – das Fenster ließ sich nicht kleiner
        # machen als der Bildschirm hoch ist.
        self.area = Gtk.ScrolledWindow()
        self.area.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.area.set_overlay_scrolling(False)
        self.area.set_kinetic_scrolling(False)
        root.add(self.area)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACING)
        box.set_border_width(BORDER)
        box.set_valign(Gtk.Align.FILL)
        self.area.add(box)  # legt einen Gtk.Viewport an
        self.area.get_child().set_shadow_type(Gtk.ShadowType.NONE)
        self.box = box
        self.event_label = label("", "beamer-event", xalign=0.5)
        self.event_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.round_label = label("", "beamer-round", xalign=0.5)
        self.song_label = label("", "beamer-song", xalign=0.5)
        self.title_label = label("", "beamer-title", wrap=True, xalign=0.5)
        self.title_label.set_justify(Gtk.Justification.CENTER)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_lines(2)
        self.artist_label = label("", "beamer-artist", wrap=True, xalign=0.5)
        self.artist_label.set_justify(Gtk.Justification.CENTER)
        self.timer_label = label("", "beamer-timer", xalign=0.5)
        self.timer_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.banner = add_class(Gtk.Box(), "beamer-banner")
        self.banner.set_halign(Gtk.Align.CENTER)
        self.banner_label = label("", wrap=True, xalign=0.5)
        self.banner_label.set_justify(Gtk.Justification.CENTER)
        self.banner_label.set_lines(2)
        self.banner_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.banner.pack_start(self.banner_label, True, True, 0)
        # „Zuletzt“: genau eine Zeile je Song. Ohne Umbruch – eine umbrochene Fortsetzung („& Anastacia“) sähe
        # zentriert wie ein eigener Song aus und kostete Höhe. Zu lange Zeilen enden mit „…“ (Titel steht vorn).
        self.recent_label = label("", "beamer-recent", xalign=0.5)
        self.recent_label.set_justify(Gtk.Justification.CENTER)
        self.recent_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.pack_start(self.event_label, False, False, 0)
        box.pack_start(self.round_label, False, False, 0)
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=MIDDLE_SPACING)
        middle.set_valign(Gtk.Align.CENTER)
        self.middle = middle
        for widget in (self.song_label, self.title_label, self.artist_label, self.timer_label, self.banner):
            middle.pack_start(widget, False, False, 0)
        box.pack_start(middle, True, True, 0)
        box.pack_end(self.recent_label, False, False, 0)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._on_click)
        self.connect("key-press-event", self._on_key)
        # Loslassen ebenfalls weiterreichen, sonst hält das Hauptfenster die Taste für „noch gedrückt“
        self.connect("key-release-event", lambda _w, event: bool(self.host is not None
                                                                 and self.host._on_key_release(self.host, event)))
        self.state: BeamerState | None = None
        self.scale = 1.0
        self.recent_scale = 1.0  # Größe von „Zuletzt“ (Einstellung), zusätzlich zur Einpass-Stufe
        self._scaled = (self.event_label, self.round_label, self.song_label, self.title_label, self.artist_label,
                        self.timer_label, self.banner_label, self.recent_label)
        self._fit_key: tuple | None = None
        self._fit_size = (0, 0)
        self._fit_source = 0
        self.area.connect("size-allocate", self._area_allocated)
        self.connect("destroy", self._cancel_fit)

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

    # ------------------------------------------------------------ Größe an den Beamer anpassen

    def _set_scale(self, scale: float) -> None:
        if scale == self.scale:
            return
        self.scale = scale
        attributes = None
        if scale != 1.0:
            attributes = Pango.AttrList()
            attributes.insert(Pango.attr_scale_new(scale))
        for widget in self._scaled:
            widget.set_attributes(attributes)
        self._apply_recent_scale()
        self.box.set_border_width(round(BORDER * scale))
        self.box.set_spacing(round(SPACING * scale))
        self.middle.set_spacing(round(MIDDLE_SPACING * scale))

    def _apply_recent_scale(self) -> None:
        factor = self.scale * self.recent_scale
        attributes = None
        if factor != 1.0:
            attributes = Pango.AttrList()
            attributes.insert(Pango.attr_scale_new(factor))
        self.recent_label.set_attributes(attributes)

    def needed_height(self, width: int) -> int:
        """Höhe, die der Inhalt bei dieser Breite in der aktuellen Schriftgröße braucht."""
        return self.box.get_preferred_height_for_width(width)[1]

    def fit(self) -> None:
        """Größte Schriftstufe wählen, bei der alles in die Höhe passt."""
        allocation = self.area.get_allocation()
        if allocation.width <= 1 or allocation.height <= 1:
            return  # noch nicht angezeigt
        for scale in SCALES:
            self._set_scale(scale)
            if self.needed_height(allocation.width) <= allocation.height:
                break

    def _fit_when_idle(self) -> bool:
        self._fit_source = 0
        self.fit()
        return False

    def _area_allocated(self, _widget, allocation) -> None:
        size = (allocation.width, allocation.height)
        if size != self._fit_size:
            self._fit_size = size
            if not self._fit_source:  # nicht mitten in der Größenzuteilung umbauen
                self._fit_source = GLib.idle_add(self._fit_when_idle)

    def _cancel_fit(self, *_args) -> None:
        if self._fit_source:
            GLib.source_remove(self._fit_source)
            self._fit_source = 0

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
        # Ein Song pro Zeile – aus der Ferne lesbarer als eine umbrechende Kette mit „·“
        self.recent_label.set_text("Zuletzt\n" + "\n".join(state.recent) if state.recent else "")
        if state.recent_scale != self.recent_scale:
            self.recent_scale = state.recent_scale
            self._apply_recent_scale()
        # Nur neu einpassen, wenn sich die Textmenge ändert – der Countdown läuft jede Sekunde durch update()
        key = (state.event_title, state.round_line, state.song_line, state.title, state.artist, bool(state.timer),
               state.banner, state.recent, state.recent_scale)
        if key != self._fit_key:
            self._fit_key = key
            self.fit()
