<p align="center"><img src="docs/logo.png" width="128" alt="Musik Bingo"></p>

# Musik Bingo · Linux Mint

Musik-Bingo für private Feiern als native Desktop-App (Python + GTK 3).
**Offline:** Die App selbst baut keine Internetverbindung auf.

![Spielleitung](docs/screenshots/spielleitung.png)

![Beamer-Ansicht für die Gäste](docs/screenshots/beamer.png)

## Funktionen

- **Karten:** 3×3, 4×4 oder 5×5, Freifeld, Diagonalen, bis 500 verschiedene Karten, Druck/PDF
- **Songlisten:** Playlist-Import (Spotify-CSV, M3U, YouTube-Titel), Zufallsmix aus Charts & Weihnachtsliedern (offline): deutsche Jahrescharts 1990–2024 (Top 10 je Jahr, nach Jahrzehnten wählbar) und aktuelle Charts (Stand KW 47/2026)
- **Bingo = Playlist:** Export als Playlist, Abgleich Karten ↔ Playlist
- **Wiedergabe:** lokale Dateien, Spotify (Desktop-App, Titel startet automatisch) oder YouTube im Browser. Bei Spotify prüft die App, ob der Titel wirklich läuft, startet die Spotify-App bei Bedarf selbst und bietet *Spotify testen* (Prüfliste vor dem Abend)
- **Player folgen:** Playlist läuft in Spotify oder YouTube, die App zieht den laufenden Song automatisch und warnt bei fremden Titeln
- **Gewinnziel pro Runde:** 1 Reihe, 2 Reihen oder volle Karte – mit Spielprognose und Gewinngarantie
- **Bingo prüfen:** zeigt die Karte mit gezogenen Feldern und Gewinnlinie, trägt Gewinner ein – auch *ohne Kartennummer*: Songs der Gewinnreihe anhaken, die App findet die Karte
- **Gewinnkontrolle:** Die App prüft nach jedem Song alle Karten gegen das aktuelle Gewinnziel und zeigt der Spielleitung direkt unter den Knöpfen, welche Karte es seit welchem Song hat (Knopf öffnet *Bingo prüfen* mit vorbelegter Nummer), dazu einen echten Gleichstand (gleicher Song) und wie vielen Karten nur noch ein Song fehlt – nur im Hauptfenster, nicht auf dem Beamer
- **Beamer-Ansicht:** zweites Fenster für die Gäste, Titel erst nach Aufdecken (T), Countdown, BINGO-Banner. Mit *Titel auf dem Beamer aufdecken* (aus) sehen die Gäste nie einen Titel – auch nicht in der Auflösung oder unter „Zuletzt“. „Zuletzt“ zeigt einstellbar 0–5 frühere Songs (Standard 3) in wählbarer Größe, je Song genau eine Zeile (zu lange enden mit „…“). Mit *Runde auf dem Beamer zeigen* (aus) steht oben nur das Gewinnziel, ohne Rundennummer
- **Song-Timer:** nach X Sekunden auflösen und automatisch weiter (P = Pause); *Nach Ablauf pausieren* hält die Musik zur Auflösung an
- **Gewinnerliste & Runden:** 1 Reihe → 2 Reihen → Volle Karte → neue Runde; keine Karte gewinnt doppelt. Wer vor dem ersten Song z. B. *Volle Karte* wählt, spielt alle Runden nur damit
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

### Aktualisieren

Im Startmenü **Musik Bingo aktualisieren** anklicken – fertig, kein Terminal nötig. Es lädt die neueste Version von GitHub (nur bei einer Git-Installation) und erneuert die Menüeinträge. Vorher die App schließen; eigene Änderungen im Ordner werden nie überschrieben, der Spielstand bleibt erhalten.

Den Menüeintrag gibt es ab 2.4.2. Einmalig von einer älteren Version aus im Terminal:

```bash
cd ~/MusicBingo_LinuxMint_Standalone && git checkout main && git pull && bash scripts/install-desktop.sh
```

## Ablauf

Zum Ausdrucken für die Moderation: [Anleitung für die Spielleitung (PDF)](docs/ANLEITUNG-SPIELLEITUNG.pdf).

1. **Songs & Playlist:** Liste importieren oder Zufallsmix erstellen → *Karten erzeugen*
2. **Bingokarten:** *Drucken / PDF*
3. **Spielleitung:** *Beamer öffnen*, Song-Timer einstellen, ziehen (Leertaste, T = Titel aufdecken, P = Timer-Pause, Rücktaste = zurück) oder *Player folgen* → *Bingo prüfen* → *Als Gewinner eintragen* → *Weiter: 2 Reihen* …

   Damit die Leertaste (und der Song-Timer) den Song auch **abspielt**: bei *Wiedergabe über* das Ziel wählen (z. B. *Spotify*) und weiter unten *Beim Ziehen automatisch abspielen* anhaken. Ohne den Haken wird nur gezogen; läuft dabei der Song-Timer, weist die App darauf hin und bietet den Haken an.

**Für ~140 Gäste** (Standardwerte): 75 Songs, 5×5 mit Freifeld, 160 Karten drucken. Ob 120 oder 170 kommen, ändert den Ablauf kaum.

| Gewinnziel | erster Gewinner typischerweise nach |
|---|---|
| 1 Reihe | ~16 Songs |
| 2 Reihen | ~30 Songs |
| Volle Karte | ~63 Songs (≈ 1 Stunde) |

**Kurze Runden mit 3×3:** 50 Songs, 3×3 mit Freifeld, 160 Karten – die erste volle Karte fällt typischerweise nach ~27 Songs (≈ 9 Minuten bei 15 s Song-Timer + 5 s Auflösung), „1 Reihe“ dagegen schon nach ~3 Songs. Für einen Abend nur mit *Volle Karte*: das Gewinnziel **vor dem ersten Song** wählen – neue Runden (*Neue Runde*, dieselben gedruckten Karten) beginnen dann wieder damit.

Spätestens nach dem letzten Song hat jede Karte „Volle Karte“ – es gibt also immer einen Gewinner, solange alle Songs der Liste gespielt werden (*Mit Playlist abgleichen* prüft das).

**Tipp für Spotify:** In Spotify unter *Einstellungen → Autoplay* ausschalten, sonst laufen nach jedem Song ähnliche Titel weiter. Playlist in Spotify anlegen, mit [Exportify](https://exportify.app) als CSV exportieren, dann *Playlist importieren*. So stehen genau die Playlist-Titel mit Spotify-Links auf den Karten.

**Spotify-Links nachtragen:** Der Knopf „Spotify: 38 von 40 Songs direkt abspielbar …“ unter der Songliste (und als Hinweis in der Spielleitung, wenn Spotify gewählt ist und Links fehlen) öffnet den Dialog *Spotify-Links*: Songs ohne Link stehen oben, pro Song lässt sich ein Songlink einfügen (in Spotify: Rechtsklick auf den Titel → Teilen → Songlink kopieren). Schneller für viele Songs: Playlist in Spotify abspielen → *Vom Player einlesen* → *Mit Playlist abgleichen* – der Abgleich überträgt die Spotify-Links auf vorhandene Songs ohne Link, ohne Karten neu zu erzeugen. Vorhandene Links (z. B. YouTube) werden dabei nicht überschrieben.


## Datenschutz

- Kein Netzwerkzugriff durch die App, keine Telemetrie
- Spotify/YouTube nur lokal über MPRIS (D-Bus) oder per Klick im Browser
- Spielstand nur lokal: `~/.local/share/musik-bingo/spielstand.json`
- Vor neuen Karten oder einem Import wird automatisch gesichert (`…/musik-bingo/sicherungen/`: die letzten 50 Kartensätze vor „Karten erzeugen“, sonst die letzten 10; beim Importieren als Lesezeichen links) – gedruckte Karten bleiben prüfbar

## Projektstruktur

```text
musik_bingo/      App (domain · application · infrastructure · presentation)
  data/           Songlisten, Kataloge, Icon
scripts/          starten.sh, install-desktop.sh, aktualisieren.sh
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
| [docs/ANLEITUNG-SPIELLEITUNG.pdf](docs/ANLEITUNG-SPIELLEITUNG.pdf) | Anleitung für Moderation/Spielleitung: Spielzeit planen, Ablauf, Bingo prüfen, Notfälle (Quelle: `docs/anleitung/`) |
| [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md) | Aufbau, Regeln, Datenformat |
| [docs/TESTPROTOKOLL.md](docs/TESTPROTOKOLL.md) | Prüfstand und manuelle Checkliste |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Ablauf für Änderungen |
| [CHANGELOG.md](CHANGELOG.md) | Versionen |

