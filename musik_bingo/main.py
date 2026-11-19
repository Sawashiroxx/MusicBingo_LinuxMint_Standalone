"""Programmeinstieg. Setzt Programmname/Fensterklasse, bevor GTK geladen wird."""
APP_ID = "de.weihnachtsfeier.musikbingo"


def main() -> int:
    import gi

    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib

    # Muss vor dem ersten Gtk-Import passieren: Sonst heißt die Fensterklasse
    # „Main.py“ und die Taskleiste ordnet das Fenster nicht dem Menüeintrag zu.
    GLib.set_prgname(APP_ID)
    Gdk.set_program_class(APP_ID)
    from musik_bingo.presentation.gtk_app import main as run

    # GTK setzt beim Start die großgeschriebene Variante – danach erneut festlegen.
    Gdk.set_program_class(APP_ID)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
