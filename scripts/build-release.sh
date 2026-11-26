#!/usr/bin/env bash
# Baut die Release-Pakete für Musik Bingo:
#   musik-bingo-<version>.zip, musik-bingo-<version>.tar.gz, SHA256SUMS und RELEASE_NOTES.md
# Aufruf: bash scripts/build-release.sh [TAG] [AUSGABEORDNER]
#   TAG            optional, z. B. v2.3.0 – muss genau "v" + Version aus musik_bingo/__init__.py sein
#   AUSGABEORDNER  optional, Standard: dist/ im Projektordner
# Es werden nur von Git verfolgte Dateien aus dem Commit HEAD verpackt (git archive),
# also keine Spielstände, Caches oder lokalen Änderungen.
set -euo pipefail

PROJEKT_ORDNER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${1:-}"
AUSGABE="${2:-$PROJEKT_ORDNER/dist}"

fehler() {
  echo "Fehler: $*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fehler "git ist nicht installiert."
git -C "$PROJEKT_ORDNER" rev-parse --verify --quiet HEAD >/dev/null \
  || fehler "$PROJEKT_ORDNER ist kein Git-Repository mit Commit (git archive braucht HEAD)."

# Alle Angaben aus demselben Commit lesen, der verpackt wird (HEAD) – sonst könnte
# eine ZIP mit neuer Versionsnummer, aber altem Inhalt entstehen.
aus_head() {
  git -C "$PROJEKT_ORDNER" show "HEAD:$1" 2>/dev/null || fehler "$1 fehlt im Commit HEAD."
}

# --- Version lesen und prüfen -------------------------------------------------
VERSION="$(aus_head musik_bingo/__init__.py | sed -n -E 's/^__version__[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' \
  | head -n 1)"
[[ -n "$VERSION" ]] || fehler "Keine Version (__version__ = \"X.Y.Z\") in musik_bingo/__init__.py gefunden."
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || fehler "Version \"$VERSION\" in musik_bingo/__init__.py hat nicht das Format X.Y.Z."

PYPROJECT_VERSION="$(aus_head pyproject.toml | sed -n -E 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' \
  | head -n 1)"
[[ "$PYPROJECT_VERSION" == "$VERSION" ]] \
  || fehler "Version in pyproject.toml (\"$PYPROJECT_VERSION\") passt nicht zu musik_bingo/__init__.py (\"$VERSION\")."

if [[ -n "$TAG" && "$TAG" != "v$VERSION" ]]; then
  fehler "Tag \"$TAG\" passt nicht zur Version $VERSION in musik_bingo/__init__.py (erwartet: v$VERSION)."
fi

if [[ -n "$(git -C "$PROJEKT_ORDNER" status --porcelain --untracked-files=no)" ]]; then
  echo "Hinweis: Es gibt nicht committete Änderungen – verpackt und geprüft wird nur der Stand von HEAD." >&2
fi

# --- Release-Notizen aus CHANGELOG.md -----------------------------------------
KURZVERSION="${VERSION%.*}"
CHANGELOG_TEXT="$(aus_head CHANGELOG.md)"

# Abschnitt mit genau dieser Überschrift (danach Leerzeichen oder Zeilenende) bis zum nächsten "## ".
abschnitt() {
  awk -v kopf="## $1" '
    /^## / {
      if (drin) exit
      rest = substr($0, length(kopf) + 1)
      if (index($0, kopf) == 1 && (rest == "" || rest ~ /^[[:space:]]/)) drin = 1
    }
    drin { print }
  ' <<< "$CHANGELOG_TEXT"
}

# Zuerst die genaue Version ("## 2.6.1"), sonst die Kurzform ("## 2.6"). Ein Fehlerbehebungs-Release
# (2.6.1) mit eigenem Abschnitt bekäme sonst die Notizen von 2.6.0, weil nur "## 2.6" gesucht wurde.
NOTIZEN="$(abschnitt "$VERSION")"
[[ -n "$NOTIZEN" ]] || NOTIZEN="$(abschnitt "$KURZVERSION")"
[[ -n "$NOTIZEN" ]] \
  || fehler "Kein Abschnitt \"## $VERSION …\" oder \"## $KURZVERSION …\" in CHANGELOG.md gefunden – bitte Änderungen für Version $VERSION eintragen."

# --- Pakete bauen ---------------------------------------------------------------
mkdir -p "$AUSGABE"
AUSGABE="$(cd -- "$AUSGABE" && pwd)"
NAME="musik-bingo-$VERSION"
ZIP="$AUSGABE/$NAME.zip"
TARGZ="$AUSGABE/$NAME.tar.gz"
rm -f "$ZIP" "$TARGZ" "$AUSGABE/SHA256SUMS" "$AUSGABE/RELEASE_NOTES.md"

git -C "$PROJEKT_ORDNER" archive --format=zip --prefix="$NAME/" -o "$ZIP" HEAD
git -C "$PROJEKT_ORDNER" archive --format=tar.gz --prefix="$NAME/" -o "$TARGZ" HEAD

# Startskripte müssen im tar.gz ausführbar bleiben. git archive übernimmt das nur,
# wenn sie mit Modus 755 eingecheckt sind – sonst neu packen und Rechte setzen.
if tar -tvzf "$TARGZ" | awk -v p="$NAME/scripts/" '
    index($NF, p) == 1 && $NF ~ /\.sh$/ && substr($1, 4, 1) != "x" { gefunden = 1 }
    END { exit gefunden ? 0 : 1 }'; then
  echo "Hinweis: Skripte in scripts/ sind ohne Ausführrecht eingecheckt – setze es im tar.gz." >&2
  ARBEIT="$(mktemp -d)"
  trap 'rm -rf "$ARBEIT"' EXIT
  tar -xzf "$TARGZ" -C "$ARBEIT"
  chmod 755 "$ARBEIT/$NAME"/scripts/*.sh
  rm -f "$TARGZ"
  tar -C "$ARBEIT" --sort=name --owner=0 --group=0 --numeric-owner -czf "$TARGZ" "$NAME"
fi

(
  cd -- "$AUSGABE"
  sha256sum "$NAME.zip" "$NAME.tar.gz" >SHA256SUMS
)

{
  printf '%s\n\n' "$NOTIZEN"
  cat <<EOF
## Installation

1. \`$NAME.zip\` unten unter **Assets** herunterladen.
2. Entpacken, z. B. nach \`~/Programme/\`:
   \`unzip $NAME.zip -d ~/Programme/\`
3. Menüeintrag anlegen:
   \`cd ~/Programme/$NAME && bash scripts/install-desktop.sh\`

Danach steht **Musik Bingo** im Startmenü. Prüfsummen: \`sha256sum -c SHA256SUMS\`.
EOF
} >"$AUSGABE/RELEASE_NOTES.md"

echo "Release $VERSION gebaut in $AUSGABE:"
ls -l "$ZIP" "$TARGZ" "$AUSGABE/SHA256SUMS" "$AUSGABE/RELEASE_NOTES.md"
