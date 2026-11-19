<p align="center"><img src="docs/logo.png" width="128" alt="Musik Bingo"></p>

# Musik Bingo · Linux Mint

Musik-Bingo für private Feiern als native Desktop-App (Python + GTK 3).
**Offline:** Die App selbst baut keine Internetverbindung auf.

![Spielleitung](docs/screenshots/spielleitung.png)

![Beamer-Ansicht für die Gäste](docs/screenshots/beamer.png)

## Funktionen

- **Karten:** 3×3, 4×4 oder 5×5, Freifeld, Diagonalen, bis 500 verschiedene Karten, Druck/PDF
- **Songlisten:** Playlist-Import (Spotify-CSV, M3U, YouTube-Titel), Zufallsmix aus Charts & Weihnachtsliedern (offline, Stand KW 47/2026)
- **Bingo = Playlist:** Export als Playlist, Abgleich Karten ↔ Playlist
- **Wiedergabe:** frei wählbar – lokale Dateien, Spotify (Desktop-App), YouTube (Browser) oder YouTube Music (Desktop-App oder Browser, z. B. mit Premium)
- **Player folgen:** Playlist läuft in Spotify, YouTube oder YouTube Music, die App zieht den laufenden Song automatisch und warnt bei fremden Titeln
- **Gewinnziel pro Runde:** 1 Reihe, 2 Reihen oder volle Karte – mit Spielprognose und Gewinngarantie
- **Bingo prüfen:** zeigt die Karte mit gezogenen Feldern und Gewinnlinie, trägt Gewinner ein
- **Beamer-Ansicht:** zweites Fenster für die Gäste, Titel erst nach Aufdecken (T), Countdown, BINGO-Banner
- **Song-Timer:** nach X Sekunden auflösen und automatisch weiter (P = Pause)
- **Gewinnerliste & Runden:** 1 Reihe → 2 Reihen → Volle Karte → neue Runde; keine Karte gewinnt doppelt
- **Titel der Feier** auf Karten und Beamer

## Installation

**Am einfachsten:** unter [Releases](https://github.com/Sawashiroxx/MusicBingo_LinuxMint_Standalone/releases) die neueste `musik-bingo-<version>.zip` herunterladen, entpacken, im Ordner `bash scripts/install-desktop.sh` ausführen.

Oder per Git:

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
3. **Spielleitung:** *Beamer öffnen*, Song-Timer einstellen, ziehen (Leertaste) oder *Player folgen* → *Bingo prüfen* → *Als Gewinner eintragen* → *Weiter: 2 Reihen* …

**Für ~140 Gäste** (Standardwerte): 75 Songs, 5×5 mit Freifeld, 160 Karten drucken. Ob 120 oder 170 kommen, ändert den Ablauf kaum.

| Gewinnziel | erster Gewinner typischerweise nach |
|---|---|
| 1 Reihe | ~16 Songs |
| 2 Reihen | ~30 Songs |
| Volle Karte | ~63 Songs (≈ 1 Stunde) |

Spätestens nach dem letzten Song hat jede Karte „Volle Karte“ – es gibt also immer einen Gewinner, solange alle Songs der Liste gespielt werden (*Mit Playlist abgleichen* prüft das).

**Tipp für Spotify:** Playlist in Spotify anlegen, mit [Exportify](https://exportify.app) als CSV exportieren, dann *Playlist importieren*. So stehen genau die Playlist-Titel mit Spotify-Links auf den Karten.

**Tipp für YouTube Music:** Oben *Wiedergabe über → YouTube Music* wählen. Playlist in YouTube Music abspielen – am besten in einer Desktop-App mit MPRIS (z. B. [th-ch „YouTube Music“](https://github.com/th-ch/youtube-music), mit Premium angemeldet), sonst auf music.youtube.com im Browser. Dann *Vom Player einlesen* → Karten → *Player folgen*. Ohne Folgen öffnet *Abspielen* den Titel (oder die Suche) auf music.youtube.com.

## Datenschutz

- Kein Netzwerkzugriff durch die App, keine Telemetrie
- Spotify/YouTube/YouTube Music nur lokal über MPRIS (D-Bus) oder per Klick im Browser
- Spielstand nur lokal: `~/.local/share/musik-bingo/spielstand.json`
- Vor neuen Karten oder einem Import wird automatisch gesichert (`…/musik-bingo/sicherungen/`, die letzten 10) – gedruckte Karten bleiben prüfbar

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

**Neue Version veröffentlichen:** Version in `musik_bingo/__init__.py` und `pyproject.toml` erhöhen, Abschnitt in `CHANGELOG.md` ergänzen, dann Tag pushen (`git tag v2.3.0 && git push origin v2.3.0`) oder auf GitHub *Releases → Draft a new release* mit neuem Tag. Die Pipeline testet und hängt ZIP, tar.gz und Prüfsummen an.
