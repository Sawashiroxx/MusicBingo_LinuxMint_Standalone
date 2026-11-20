#!/usr/bin/env bash
# Holt die neueste Version von GitHub (Zweig main) und aktualisiert den Menüeintrag.
# Wird über den Menüeintrag „Musik Bingo aktualisieren“ gestartet – ohne Terminal.
# Die App selbst baut nie Netzwerkverbindungen auf; nur dieses Skript, und nur auf Klick.
set -uo pipefail

PROJEKT_ORDNER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ZWEIG="main"
RELEASES="https://github.com/Sawashiroxx/MusicBingo_LinuxMint_Standalone/releases"
TITEL="Musik Bingo aktualisieren"

# Meldungen: Fenster (zenity, auf Linux Mint vorinstalliert), sonst Terminal-Ausgabe.
# MUSIK_BINGO_OHNE_DIALOG=1 schaltet Fenster ab (Tests, Terminal-Nutzung).
mit_fenster() {
  [ "${MUSIK_BINGO_OHNE_DIALOG:-0}" != "1" ] && command -v zenity >/dev/null 2>&1 \
    && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]
}
info() {
  # Schließen per X statt OK ist kein Fehler
  if mit_fenster; then zenity --info --title="$TITEL" --width=440 --text="$1" 2>/dev/null || true
  else printf '%s\n' "$1"; fi
}
fehler() {
  if mit_fenster; then zenity --error --title="$TITEL" --width=440 --text="$1" 2>/dev/null
  else printf 'FEHLER: %s\n' "$1" >&2; fi
  exit 1
}
version() {
  sed -n 's/^__version__ = "\(.*\)"/\1/p' "$PROJEKT_ORDNER/musik_bingo/__init__.py" 2>/dev/null
}

cd "$PROJEKT_ORDNER" || fehler "Projektordner nicht gefunden: $PROJEKT_ORDNER"

# Doppelklick-Schutz: nur ein Update gleichzeitig
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/musik-bingo-aktualisieren.lock"
flock -n 9 || fehler "Ein Update läuft bereits."

command -v git >/dev/null 2>&1 || fehler "git fehlt. Einmalig im Terminal installieren:

sudo apt install git"

if [ ! -d .git ]; then
  if mit_fenster && zenity --question --title="$TITEL" --width=440 \
      --ok-label="Download-Seite öffnen" --cancel-label="Abbrechen" \
      --text="Diese Kopie wurde als ZIP installiert und kann sich nicht selbst aktualisieren.

Lade die neue Version von der Release-Seite herunter und entpacke sie über den alten Ordner." 2>/dev/null; then
    xdg-open "$RELEASES" >/dev/null 2>&1 &
    exit 0
  fi
  fehler "Keine Git-Kopie – bitte die neue Version herunterladen: $RELEASES"
fi

# Die App darf nicht laufen: Sie speichert beim Schließen, und neue Dateien wirken erst nach Neustart.
if pgrep -u "$(id -u)" -f "[m]usik_bingo\.main" >/dev/null 2>&1; then
  fehler "Musik Bingo läuft noch. Bitte die App schließen und das Update dann erneut starten."
fi

# Eigene Änderungen niemals überschreiben
if ! git diff --quiet || ! git diff --cached --quiet; then
  fehler "Im Projektordner gibt es geänderte Dateien – das Update wurde nicht gestartet, damit nichts verloren geht.

Ordner: $PROJEKT_ORDNER"
fi

ALT="$(version)"
ALT_STAND="$(git rev-parse HEAD)"
PROTOKOLL="$(mktemp)"
trap 'rm -f "$PROTOKOLL"' EXIT

# 1. Nur herunterladen – das ändert am installierten Stand noch nichts
lade() {
  git fetch --quiet origin "$ZWEIG"
}
if mit_fenster; then
  ( lade >"$PROTOKOLL" 2>&1; echo $? >"$PROTOKOLL.rc" ) | zenity --progress --pulsate --auto-close \
    --no-cancel --title="$TITEL" --text="Neue Version wird geladen …" --width=380 2>/dev/null
  RC="$(cat "$PROTOKOLL.rc" 2>/dev/null || echo 1)"
  rm -f "$PROTOKOLL.rc"
else
  lade >"$PROTOKOLL" 2>&1
  RC=$?
fi
if [ "$RC" != "0" ]; then
  fehler "Update fehlgeschlagen (Internet? GitHub erreichbar?). Es wurde nichts verändert.

$(tail -n 5 "$PROTOKOLL")"
fi

# 2. Prüfen, ob der neue Stand den installierten nur ergänzt – sonst nichts anfassen
ist_enthalten() { git merge-base --is-ancestor "$1" "origin/$ZWEIG"; }
AKTUELLER_ZWEIG="$(git rev-parse --abbrev-ref HEAD)"
if ! ist_enthalten HEAD; then
  if [ "$AKTUELLER_ZWEIG" = "$ZWEIG" ]; then
    fehler "Diese Kopie enthält eigene Änderungen, die es auf GitHub nicht gibt. Update abgebrochen – es wurde nichts verändert."
  fi
  fehler "Diese Kopie steht auf dem Entwicklungsstand '$AKTUELLER_ZWEIG', der noch nicht in '$ZWEIG' übernommen ist (Pull Request noch nicht gemergt). Ein Update würde neue Funktionen entfernen – abgebrochen, es wurde nichts verändert."
fi
if git rev-parse --verify --quiet "refs/heads/$ZWEIG" >/dev/null && ! ist_enthalten "refs/heads/$ZWEIG"; then
  fehler "Der lokale Zweig '$ZWEIG' weicht von GitHub ab. Update abgebrochen – es wurde nichts verändert."
fi

# 3. Übernehmen (nur noch Vorspulen, kann nichts überschreiben)
if [ "$AKTUELLER_ZWEIG" = "$ZWEIG" ]; then
  git merge --quiet --ff-only "origin/$ZWEIG" >"$PROTOKOLL" 2>&1
else
  git checkout --quiet -B "$ZWEIG" "origin/$ZWEIG" >"$PROTOKOLL" 2>&1 \
    && git branch --quiet --set-upstream-to="origin/$ZWEIG" "$ZWEIG" >>"$PROTOKOLL" 2>&1
fi || fehler "Update konnte nicht übernommen werden:

$(tail -n 5 "$PROTOKOLL")"

NEU="$(version)"
if ! bash "$PROJEKT_ORDNER/scripts/install-desktop.sh" >"$PROTOKOLL" 2>&1; then
  fehler "Die neue Version ist geladen, der Menüeintrag konnte aber nicht erneuert werden:

$(tail -n 5 "$PROTOKOLL")"
fi

if [ "$ALT_STAND" = "$(git rev-parse HEAD)" ]; then
  info "Musik Bingo ist aktuell (Version $NEU)."
else
  [ "$ALT" = "$NEU" ] && NEU="$NEU (neuer Stand)"
  info "Musik Bingo wurde aktualisiert: Version $ALT → $NEU.

Dein Spielstand bleibt erhalten. Einfach die App wieder starten."
fi
exit 0
