#!/usr/bin/env bash
set -euo pipefail

# Projektordner = Ordner oberhalb von scripts/
PROJEKT_ORDNER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="/usr/bin/python3"

fehler() {
  zenity --error --title="Musik Bingo" --width=420 --text="$1" 2>/dev/null || printf 'Musik Bingo: %s\n' "$1" >&2
  exit 1
}

[ -x "$PYTHON" ] || fehler "Python 3 wurde nicht gefunden. Auf Linux Mint ist Python normalerweise vorinstalliert."

if ! "$PYTHON" -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' >/dev/null 2>&1; then
  fehler "GTK 3 mit PyGObject fehlt. Bitte im Terminal installieren:

sudo apt install python3-gi gir1.2-gtk-3.0"
fi

if ! "$PYTHON" -c 'import gi; gi.require_foreign("cairo")' >/dev/null 2>&1; then
  # Kein Abbruch: Spielen geht auch ohne, nur Drucken nicht. Hinweis einmalig im Terminal.
  printf 'Hinweis: Für den Kartendruck bitte installieren: sudo apt install python3-gi-cairo\n' >&2
fi

cd "$PROJEKT_ORDNER"
exec "$PYTHON" -m musik_bingo.main "$@"
