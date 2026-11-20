#!/usr/bin/env bash
# Legt einen Menüeintrag „Musik Bingo“ samt Icon für den aktuellen Benutzer an.
# Keine Root-Rechte nötig. Erneut ausführen, wenn der Projektordner verschoben wurde.
set -euo pipefail

PROJEKT_ORDNER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DATEN_ORDNER="${XDG_DATA_HOME:-${HOME}/.local/share}"
APP_ORDNER="${DATEN_ORDNER}/applications"
ICON_ZIEL="${DATEN_ORDNER}/icons/hicolor"
DESKTOP_DATEI="${APP_ORDNER}/musik-bingo.desktop"
UPDATE_DATEI="${APP_ORDNER}/musik-bingo-aktualisieren.desktop"

mkdir -p "$APP_ORDNER"
# Icon in allen Größen (PNG + SVG) in das Benutzer-Icon-Thema kopieren
ICON_QUELLE="$PROJEKT_ORDNER/musik_bingo/data/icons/hicolor"
for ICON in "$ICON_QUELLE"/*/apps/musik-bingo.*; do
  GROESSE="$(basename "$(dirname "$(dirname "$ICON")")")"
  install -D -m 644 "$ICON" "$ICON_ZIEL/$GROESSE/apps/$(basename "$ICON")"
done

# Pfad für die Exec-Zeile nach Desktop-Entry-Spezifikation maskieren. Werte werden
# erst als String (\\ → \) und dann nach Anführungsregeln (\" \` \$ \\) gelesen,
# daher: Backslash → 4×\, Anführungszeichen/Backtick/Dollar → \\ davor, % → %%.
exec_pfad() {
  printf '%s' "$1" | sed -e 's/\\/\\\\\\\\/g' -e 's/["`$]/\\\\&/g' -e 's/%/%%/g'
}
EXEC_PFAD="$(exec_pfad "$PROJEKT_ORDNER/scripts/starten.sh")"
UPDATE_PFAD="$(exec_pfad "$PROJEKT_ORDNER/scripts/aktualisieren.sh")"

# Exec über /bin/bash: funktioniert auch, wenn starten.sh beim Kopieren das
# Ausführungsrecht verloren hat (z. B. von USB-Stick oder Cloud-Ordner).
cat > "$DESKTOP_DATEI" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Musik Bingo
GenericName=Musik-Bingo-Spiel
Comment=Musik-Bingo für private Feiern – Karten, Ziehung, Spotify/YouTube Music
Icon=musik-bingo
Exec=/bin/bash "$EXEC_PFAD"
Path=$PROJEKT_ORDNER
Terminal=false
Categories=Game;
Keywords=Bingo;Musik;Weihnachten;Party;Spotify;YouTube;
StartupNotify=true
StartupWMClass=de.weihnachtsfeier.musikbingo
DESKTOP
# Zweiter Eintrag: Update per Klick, ohne Terminal (holt die neue Version von GitHub)
cat > "$UPDATE_DATEI" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Musik Bingo aktualisieren
Comment=Neueste Version von Musik Bingo von GitHub laden
Icon=system-software-update
Exec=/bin/bash "$UPDATE_PFAD"
Path=$PROJEKT_ORDNER
Terminal=false
Categories=Game;
Keywords=Bingo;Update;Aktualisieren;
StartupNotify=false
DESKTOP
chmod 644 "$DESKTOP_DATEI" "$UPDATE_DATEI"

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$DESKTOP_DATEI"
  desktop-file-validate "$UPDATE_DATEI"
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t "${DATEN_ORDNER}/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q "$APP_ORDNER" 2>/dev/null || true
fi

printf 'Menüeinträge installiert: %s, %s\n' "$DESKTOP_DATEI" "$UPDATE_DATEI"
