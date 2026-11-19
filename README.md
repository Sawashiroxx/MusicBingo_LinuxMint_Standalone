# 🎵 Musik Bingo · Linux Mint

Musik-Bingo für private Feiern als native Desktop-App (Python + GTK 3).
**Offline:** Die App selbst baut keine Internetverbindung auf.

![Spielleitung](docs/screenshots/spielleitung.png)

## Funktionen

- **Karten:** 3×3, 4×4 oder 5×5, Freifeld, Diagonalen, bis 500 verschiedene Karten, Druck/PDF
- **Songlisten:** Playlist-Import (Spotify-CSV, M3U, YouTube-Titel), Zufallsmix aus Charts & Weihnachtsliedern (offline, Stand KW 47/2026)
- **Bingo = Playlist:** Export als Playlist, Abgleich Karten ↔ Playlist
- **Wiedergabe:** lokale Dateien, Spotify-Desktop-App oder YouTube im Browser
- **Player folgen:** Playlist läuft in Spotify/YouTube, die App zieht den laufenden Song automatisch und warnt bei fremden Titeln
- **Bingo prüfen:** zeigt die Karte mit gezogenen Feldern und Gewinnlinie

## Installation

```bash
git clone https://github.com/Sawashiroxx/MusicBingo_LinuxMint_Standalone.git
cd MusicBingo_LinuxMint_Standalone
bash scripts/install-desktop.sh     # Menüeintrag „Musik Bingo“ unter Spiele
```

Oder ohne Menüeintrag: `bash scripts/starten.sh`

Benötigt (auf Mint vorinstalliert): `python3-gi`, `gir1.2-gtk-3.0`, `python3-gi-cairo` (Druck).
Optional für lokale Musikdateien: `python3-gst-1.0`.

## Ablauf

1. **Songs & Playlist:** Liste importieren oder Zufallsmix erstellen → *Karten erzeugen*
2. **Bingokarten:** *Drucken / PDF*
3. **Spielleitung:** Wiedergabe wählen → ziehen (Leertaste) oder *Player folgen* → *Bingo prüfen*

**Tipp für Spotify:** Playlist in Spotify anlegen, mit [Exportify](https://exportify.app) als CSV exportieren, dann *Playlist importieren*. So stehen genau die Playlist-Titel mit Spotify-Links auf den Karten.

## Datenschutz

- Kein Netzwerkzugriff durch die App, keine Telemetrie
- Spotify/YouTube nur lokal über MPRIS (D-Bus) oder per Klick im Browser
- Spielstand nur lokal: `~/.local/share/musik-bingo/spielstand.json`

## Projektstruktur

```text
musik_bingo/      App (domain · application · infrastructure · presentation)
  data/           Songlisten, Kataloge, Icon
scripts/          starten.sh, install-desktop.sh
tests/            unit · integration · security · gui (E2E unter Xvfb)
docs/             Architektur, Prüfprotokoll, Screenshots
```

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -v          # alles
PYTHONPATH=. python3 -m unittest discover -s tests/unit -t .   # nur Unit
```

Die GitHub-Pipeline führt Lint, Unit- (Mint 21 + 22), Integrations-, Sicherheits- und GUI/E2E-Tests aus.

| Dokument | Inhalt |
|---|---|
| [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md) | Aufbau, Regeln, Datenformat |
| [docs/TESTPROTOKOLL.md](docs/TESTPROTOKOLL.md) | Prüfstand und manuelle Checkliste |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Ablauf für Änderungen |
| [CHANGELOG.md](CHANGELOG.md) | Versionen |
