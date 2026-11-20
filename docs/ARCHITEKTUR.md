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
├── data/             Startliste, Kataloge (catalogs/), Icons (icons/hicolor/)
└── paths.py          zentrale Pfade zu data/
```

## Module

| Modul | Aufgabe |
|---|---|
| `domain/models.py` | `Song` (Titel, Interpret, optionaler Link), `BingoCard` |
| `domain/song_list.py` | Zeilenformat `Titel – Interpret \| Link` lesen/schreiben |
| `domain/links.py` | Nur `spotify:track:…` und YouTube-Video-Links zulassen, vereinheitlichen; eingefügte Links mit deutscher Fehlermeldung prüfen (`parse_user_link`) |
| `domain/link_coverage.py` | Abdeckung einer Songliste: mit Spotify-/YouTube-Link, ohne Link, Songs ohne Spotify-Link |
| `domain/text.py` | Normalisieren, „(Official Video)“, „Remastered“, „feat.“ entfernen |
| `domain/catalog.py` | Kataloge lesen, Zufallsmix Charts/Weihnachten |
| `domain/playlist.py` | Import CSV/M3U/Text/Player, Export Text/CSV/M3U |
| `domain/matching.py` | Laufenden Titel einem Song zuordnen, Playlist-Abgleich, Links aus der Playlist übernehmen |
| `domain/card_generator.py` | Karten erzeugen, Gewinnlinien prüfen |
| `domain/evening.py` | Ablauf des Abends: Stufen/Runden, Gewinner mit Doppel-Schutz, Feiertitel, CSV-Export |
| `application/song_timer.py` | Song-Timer (Countdown → Auflösung → nächster Song), ohne GTK testbar |
| `application/beamer_state.py` | Was die Gäste sehen (Titel verborgen bis Aufdecken) |
| `presentation/beamer.py` | Beamer-Fenster (zweiter Bildschirm, Vollbild) |
| `domain/forecast.py` | Gewinnziele, Spielprognose (wann gibt es Gewinner?), Gewinngarantie |
| `domain/caller.py` | Ziehreihenfolge, ziehen, Song gezielt ziehen, zurück, mischen |
| `application/game_service.py` | Zustand, Einstellungen, JSON-Format mit Validierung |
| `infrastructure/file_store.py` | Atomisches Speichern unter `$XDG_DATA_HOME/musik-bingo/` |
| `infrastructure/audio_*.py` | Audiodateien zuordnen und mit GStreamer abspielen |
| `infrastructure/mpris.py` | Player auflisten, Metadaten, Steuerung, `OpenUri`, Playlist einlesen |
| `infrastructure/launcher.py` | Wie ein Song in Spotify oder YouTube geöffnet wird |
| `infrastructure/spotify.py` | Spotify-App starten (Paket/Snap/Flatpak), auf den Busnamen warten, Abspiel-Kontrolle nach `OpenUri`, Selbsttest |
| `application/spotify_check.py` | Prüfliste und Testsong für „Spotify testen“ |
| `presentation/gtk_app.py` | Hauptfenster mit drei Bereichen, Folgen-Modus |

## Wichtige Regeln

- **Karten:** Feldzahl = Größe² − Freifeld (nur bei ungerader Größe). Kombinationen werden vorab mit `math.comb` geprüft; keine doppelten Karten; max. 500.
- **Runde vs. Entwurf:** Die Songliste im Editor ändert eine laufende Runde nie. Erst *Karten erzeugen* startet eine neue Runde.
- **Gewinngarantie:** Steht jeder Kartensong im gespielten Pool, ist spätestens nach dem letzten Song jede Karte voll – es gibt immer einen Gewinner. `guarantee()` prüft das nach dem Erzeugen.
- **Prognose:** Pro simuliertem Spiel genügt die Ziehposition jedes Songs: Eine Linie ist voll beim Maximum ihrer Felder. 200 Spiele mit 160 Karten dauern < 0,5 s. Tests vergleichen das Ergebnis exakt mit Song-für-Song-Nachspielen.
- **Song-Identität:** Titel + Interpret (ohne Groß-/Kleinschreibung). Der Link gehört nicht dazu.
- **Links nachtragen:** `GameService.set_song_links` setzt/entfernt Links per Song-Identität gleichzeitig in Editorliste (`song_text`), Runde, allen Karten und der Ziehung (Pool/Reihenfolge). Karten, Ziehung und Gewinnprüfung bleiben unverändert; ungültige Links → `ValueError`, nichts wird geändert. *Mit Playlist abgleichen* überträgt so Links aus der Playlist auf Songs ohne Link.
- **Zuordnung (Folgen-Modus):** Spotify-ID → Titel + Interpret → eindeutiger Titel. Mehrdeutiges wird nicht geraten, unbekannte Titel werden nie gezogen, Werbung wird ignoriert.
- **Abspielen:** Spotify-Link + laufende App → MPRIS `OpenUri`; sonst `spotify:`-Schema → Webplayer/Suche. YouTube → Browser (`youtube.com`).
- **Abspiel-Kontrolle (Spotify):** Nach `OpenUri` wird bis ca. 2,5 s asynchron beobachtet (PropertiesChanged + `GetAll`): richtiger Titel (`mpris:trackid`) mit „Playing“ → „Läuft in Spotify“; richtiger Titel pausiert → einmal `Play()`; Titel fehlt → einmal `OpenUri` wiederholen, danach nicht-modale Warnung. Ein neuer Song bricht die Kontrolle ab.
- **Spotify-Autostart:** Song mit Spotify-Link, aber Spotify nicht am Bus → Desktop-App per `Gio.DesktopAppInfo` starten, bis 15 s auf `org.mpris.MediaPlayer2.spotify` warten, dann `OpenUri` + Kontrolle; sonst bisheriger Rückfall.
- **Nach Ablauf pausieren:** Beim Übergang Spielzeit → Auflösung pausiert die App Spotify (MPRIS) bzw. die lokale Datei; nicht im Folgen-Modus und nicht bei YouTube.
- **Player-Wahl (MPRIS):** Spotify → nur Spotify; YouTube → Browser. Ein gespeicherter Player hat Vorrang, wenn er zum Ziel passt.
- **Stufen:** 1 Reihe → 2 Reihen → Volle Karte bei weiterlaufender Ziehung (passt zur Prognose); danach neue Runde mit neu gemischter Ziehung. Neue Karten setzen Runde und Gewinnerliste zurück (alte Stände liegen in `sicherungen/`).
- **Gewinner:** nur eintragbar, wenn die Karte das aktuelle Ziel erreicht hat; gleiche Karte und Stufe nie doppelt, andere Stufe nur nach Rückfrage.
- **Beamer:** zeigt den aktuellen Titel erst nach Aufdecken; „Zuletzt“ enthält nur vorherige Songs.
- **Offline:** Die App öffnet keine Netzwerkverbindungen. MPRIS läuft über den lokalen Sitzungsbus.

## Spielstand

JSON mit `version: 1`, atomar geschrieben, Dateirechte 0600 (nur der Benutzer). Neue Felder (`link`, `playback_target`, `follow_player`, `player_name`, `pause_after_timer` – Standard an) sind optional, alte Stände laden weiter. Beim Import werden Typen, Kartenregeln, Ziehreihenfolge und Links geprüft; ungültige Dateien werden abgelehnt, statt still repariert zu werden.

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

Release: `scripts/build-release.sh <tag>` baut aus Git ZIP/tar.gz/Prüfsummen und Release-Notizen; `.github/workflows/release.yml` läuft bei Tags `v*`.
