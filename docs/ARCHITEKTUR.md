# Architektur

Schichtenmodell, Abhängigkeiten zeigen nur nach innen:
`presentation → application → domain` und `infrastructure → domain`.
Die Domain kennt weder GTK noch Dateien noch D-Bus.

```text
musik_bingo/
├── domain/           reine Logik, vollständig unit-getestet
├── application/      Spielzustand (GameService), Speichern/Laden-Format
├── infrastructure/   Dateien, GStreamer, MPRIS/D-Bus, Links öffnen
├── presentation/     GTK-Fenster, Dialoge, Theme, Druck (Cairo)
├── data/             Startliste, Kataloge (catalogs/), Icon (icons/)
└── paths.py          zentrale Pfade zu data/
```

## Module

| Modul | Aufgabe |
|---|---|
| `domain/models.py` | `Song` (Titel, Interpret, optionaler Link), `BingoCard` |
| `domain/song_list.py` | Zeilenformat `Titel – Interpret \| Link` lesen/schreiben |
| `domain/links.py` | Nur `spotify:track:…` und YouTube-Video-Links zulassen, vereinheitlichen |
| `domain/text.py` | Normalisieren, „(Official Video)“, „Remastered“, „feat.“ entfernen |
| `domain/catalog.py` | Kataloge lesen, Zufallsmix Charts/Weihnachten |
| `domain/playlist.py` | Import CSV/M3U/Text/Player, Export Text/CSV/M3U |
| `domain/matching.py` | Laufenden Titel einem Song zuordnen, Playlist-Abgleich |
| `domain/card_generator.py` | Karten erzeugen, Gewinnlinien prüfen |
| `domain/caller.py` | Ziehreihenfolge, ziehen, Song gezielt ziehen, zurück, mischen |
| `application/game_service.py` | Zustand, Einstellungen, JSON-Format mit Validierung |
| `infrastructure/file_store.py` | Atomisches Speichern unter `$XDG_DATA_HOME/musik-bingo/` |
| `infrastructure/audio_*.py` | Audiodateien zuordnen und mit GStreamer abspielen |
| `infrastructure/mpris.py` | Player auflisten, Metadaten, Steuerung, `OpenUri`, Playlist einlesen |
| `infrastructure/launcher.py` | Wie ein Song in Spotify/YouTube geöffnet wird |
| `presentation/gtk_app.py` | Hauptfenster mit drei Bereichen, Folgen-Modus |

## Wichtige Regeln

- **Karten:** Feldzahl = Größe² − Freifeld (nur bei ungerader Größe). Kombinationen werden vorab mit `math.comb` geprüft; keine doppelten Karten; max. 500.
- **Runde vs. Entwurf:** Die Songliste im Editor ändert eine laufende Runde nie. Erst *Karten erzeugen* startet eine neue Runde.
- **Song-Identität:** Titel + Interpret (ohne Groß-/Kleinschreibung). Der Link gehört nicht dazu.
- **Zuordnung (Folgen-Modus):** Spotify-ID → Titel + Interpret → eindeutiger Titel. Mehrdeutiges wird nicht geraten, unbekannte Titel werden nie gezogen, Werbung wird ignoriert.
- **Abspielen:** Spotify-Link + laufende App → MPRIS `OpenUri`; sonst `spotify:`-Schema → Webplayer/Suche. YouTube → Browser.
- **Offline:** Die App öffnet keine Netzwerkverbindungen. MPRIS läuft über den lokalen Sitzungsbus.

## Spielstand

JSON mit `version: 1`, atomar geschrieben, Dateirechte 0600 (nur der Benutzer). Neue Felder (`link`, `playback_target`, `follow_player`, `player_name`) sind optional, alte Stände laden weiter. Beim Import werden Typen, Kartenregeln, Ziehreihenfolge und Links geprüft; ungültige Dateien werden abgelehnt, statt still repariert zu werden.

## Kataloge

`musik_bingo/data/catalogs/*.txt` mit Kopf:

```text
# name: Charts aktuell (Top 50, KW 47/2026)
# kategorie: charts            # oder: weihnachten
# quelle: Offizielle Deutsche Charts …
Housewife – Tate McRae
```

## Tests

| Ordner | Inhalt |
|---|---|
| `tests/unit` | Fachlogik, Import/Export, Matching, Regressionen |
| `tests/integration` | MPRIS gegen simuliertes Spotify (privater D-Bus), GStreamer, Druck, Installer |
| `tests/security` | kein Netzwerk, Link-Positivliste (Fuzzing), Dateirechte, manipulierte Dateien, Exec-Injection |
| `tests/gui` | echte GTK-Fenster unter Xvfb: Gesamtablauf inkl. PDF, Spotify-E2E, Grenzfälle, Screenshots |
| `tests/support` | simulierter MPRIS-Player |
