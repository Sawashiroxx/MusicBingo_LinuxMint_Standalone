"""Das App-Design darf GTK-eigene Stilklassen nicht umdeuten (Fehler: Dateidialog unlesbar)."""
import re
import unittest

from musik_bingo.presentation.theme import PALETTES, css_for

# Stilklassen, die GTK 3 selbst vergibt (gtkstylecontext.h, GTK_STYLE_CLASS_*), plus häufige Theme-Klassen.
GTK_RESERVED = {
    "cell", "view", "button", "entry", "check", "radio", "menu", "menubar", "menuitem", "toolbar", "background",
    "frame", "list", "list-row", "sidebar", "header", "titlebar", "title", "subtitle", "linked", "flat",
    "suggested-action", "destructive-action", "dim-label", "error", "warning", "info", "question", "image",
    "trough", "slider", "scale", "scrollbar", "progressbar", "spinbutton", "tooltip", "dialog-action-area",
    "dialog-vbox", "dnd", "expander", "notebook", "pane-separator", "rubberband", "separator", "spinner",
    "top", "bottom", "left", "right", "horizontal", "vertical", "osd", "level-bar", "accelerator", "mark",
    "highlight", "inline-toolbar", "primary-toolbar", "message-dialog", "popover", "popup", "selection-mode",
    "circular", "text-button", "image-button", "default", "touch-selection", "context-menu", "monospace",
}
# Bewusst genutzte GTK-Klassen mit Absicht (nur mit Elementtyp/Eltern kombiniert):
ALLOWED = {"linked", "flat", "dialog-action-area", "dialog-vbox", "view", "title", "subtitle", "background"}


class ThemeTests(unittest.TestCase):
    def test_no_reserved_gtk_class_is_restyled(self):
        for theme in PALETTES:
            css = css_for(theme)
            classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", re.sub(r"\{[^}]*\}", "{}", css)))
            with self.subTest(theme=theme):
                self.assertEqual(sorted((classes & GTK_RESERVED) - ALLOWED), [])

    def test_both_palettes_have_same_keys(self):
        self.assertEqual(set(PALETTES["dark"]), set(PALETTES["light"]))


if __name__ == "__main__":
    unittest.main()
