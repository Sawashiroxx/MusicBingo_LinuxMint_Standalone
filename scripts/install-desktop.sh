#!/usr/bin/env bash
# Legt einen Menüeintrag „Musik Bingo“ samt Icon für den aktuellen Benutzer an.
# Keine Root-Rechte nötig. Erneut ausführen, wenn der Projektordner verschoben wurde.
set -euo pipefail

PROJEKT_ORDNER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DATEN_ORDNER="${XDG_DATA_HOME:-${HOME}/.local/share}"
APP_ORDNER="${DATEN_ORDNER}/applications"
ICON_ZIEL="${DATEN_ORDNER}/icons/hicolor"
DESKTOP_DATEI="${APP_ORDNER}/musik-bingo.desktop"

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
STARTER="$PROJEKT_ORDNER/scripts/starten.sh"
EXEC_PFAD="$(printf '%s' "$STARTER" | sed -e 's/\\/\\\\\\\\/g' -e 's/["`$]/\\\\&/g' -e 's/%/%%/g')"

# Exec über /bin/bash: funktioniert auch, wenn starten.sh beim Kopieren das
# Ausführungsrecht verloren hat (z. B. von USB-Stick oder Cloud-Ordner).
cat > "$DESKTOP_DATEI" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Musik Bingo
GenericName=Musik-Bingo-Spiel
Comment=Musik-Bingo für private Feiern – Karten, Ziehung, Spotify/YouTube
Icon=musik-bingo
Exec=/bin/bash "$EXEC_PFAD"
Path=$PROJEKT_ORDNER
Terminal=false
Categories=Game;
Keywords=Bingo;Musik;Weihnachten;Party;Spotify;
StartupNotify=true
StartupWMClass=de.weihnachtsfeier.musikbingo
DESKTOP
chmod 644 "$DESKTOP_DATEI"

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$DESKTOP_DATEI"
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t "${DATEN_ORDNER}/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q "$APP_ORDNER" 2>/dev/null || true
fi

printf 'Menüeintrag installiert: %s\n' "$DESKTOP_DATEI"
