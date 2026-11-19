"""Misst den Kontrast von Tabellen-/Dateilisten-Text in beiden Designs (WCAG ≥ 4,5:1)."""
import sys

from common import Gdk, GLib, Gtk, check
from musik_bingo.presentation.theme import css_for

THEME = sys.argv[1]
provider = Gtk.CssProvider()
provider.load_from_data(css_for(THEME).encode())
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", THEME == "dark")

store = Gtk.ListStore(str)
for _ in range(6):
    store.append(["WWWWWWWWWWWWWWWWWWWW musik_bingo scripts tests"])
view = Gtk.TreeView(model=store)
view.append_column(Gtk.TreeViewColumn("Name", Gtk.CellRendererText(), text=0))
window = Gtk.Window()
window.add(view)
window.set_default_size(500, 220)


def luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def measure():
    gdk_window = view.get_bin_window()
    view.get_selection().unselect_all()
    pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, 480, 100)
    data, stride, channels = pixbuf.get_pixels(), pixbuf.get_rowstride(), pixbuf.get_n_channels()
    pixels = [tuple(data[y * stride + x * channels: y * stride + x * channels + 3])
              for y in range(pixbuf.get_height()) for x in range(pixbuf.get_width())]
    background = max(set(pixels), key=pixels.count)
    bg = luminance(background)
    text = max(pixels, key=lambda p: abs(luminance(p) - bg))
    light, dark = max(bg, luminance(text)), min(bg, luminance(text))
    ratio = (light + 0.05) / (dark + 0.05)
    check(f"{THEME}: Tabellentext-Kontrast {ratio:.1f}:1 (≥ 4,5)", ratio >= 4.5)
    from common import RESULTS
    sys.exit(0 if all(ok for _, ok in RESULTS) else 1)


window.show_all()
GLib.timeout_add(800, measure)
Gtk.main()
