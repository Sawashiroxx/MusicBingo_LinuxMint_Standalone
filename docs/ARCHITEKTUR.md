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
| `domain/playlist.py` | Import CSV/M3U/Text/Player (Tab-getrennte Tabellen mit Kopfzeile auch ohne Endung .csv), Export Text/CSV/M3U |
| `domain/matching.py` | Laufenden Titel einem Song zuordnen, Playlist-Abgleich, Links aus der Playlist übernehmen |
| `domain/card_generator.py` | Karten erzeugen, Gewinnlinien prüfen |
| `domain/evening.py` | Ablauf des Abends: Stufen/Runden, Gewinner mit Doppel-Schutz, Feiertitel, CSV-Export |
| `application/song_timer.py` | Song-Timer (Countdown → Auflösung → nächster Song), ohne GTK testbar |
| `application/beamer_state.py` | Was die Gäste sehen (Titel verborgen bis Aufdecken; mit `beamer_reveal` aus nie) |
| `presentation/beamer.py` | Beamer-Fenster (zweiter Bildschirm, Vollbild) |
| `domain/forecast.py` | Gewinnziele, Spielprognose (wann gibt es Gewinner?), Gewinngarantie, fehlende Songs bis zum Ziel (`missing_to_target`) |
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
- **Zuordnung (Folgen-Modus):** Spotify-ID → Titel + Interpret → eindeutiger Titel. Der Titel wird ohne Zusätze („(Official Video)“, „(with …)“) und zusätzlich vollständig verglichen – so passt „Killing Me Softly (With His Song)“ auch zu „Killing Me Softly With His Song“. Mehrdeutiges wird nicht geraten, unbekannte Titel werden nie gezogen, Werbung wird ignoriert.
- **Abspielen:** Spotify-Link + laufende App → MPRIS `OpenUri`; sonst `spotify:`-Schema → Webplayer/Suche. YouTube → Browser (`youtube.com`).
- **Abspiel-Kontrolle (Spotify):** Nach `OpenUri` wird bis ca. 2,5 s asynchron beobachtet (PropertiesChanged + `GetAll`): richtiger Titel mit „Playing“ → „Läuft in Spotify“. Richtig ist er bei passendem Link (`mpris:trackid`/`xesam:url`) oder – Spotifys „Relinking“ – bei anderer Track-ID mit gleicher Song-Identität. Richtiger Titel pausiert → einmal `Play()`; hat sich gar nichts getan (noch derselbe Eintrag wie vor dem Öffnen) → einmal `OpenUri` wiederholen; hat Spotify schon gewechselt und lädt nur, wird nicht neu geöffnet, sondern noch einmal gewartet. Danach nicht-modale Warnung – die Kontrolle beobachtet aber still bis 30 s weiter und nimmt die Warnung zurück („Läuft jetzt in Spotify“), sobald der Titel doch läuft. Ein neuer Song und „Nach Ablauf pausieren“ brechen die Kontrolle ab.
- **Hängender Player:** Besitzt ein Prozess den MPRIS-Namen, antwortet aber nicht, blockiert die Oberfläche höchstens ca. 1 s (`list_players` fragt alle Namen parallel mit Zeitbudget ab; `MprisPlayer` lädt seine Eigenschaften asynchron statt per `DBusProxy`-Standard mit 25 s). `OpenUri` ohne Antwort → „Spotify reagiert nicht“ und Rückfall wie bei abgelehntem `OpenUri`.
- **Spotify testen – Testsong:** vor Spielbeginn der erste Song mit Link; in einer laufenden Runde nur der aktuelle oder ein bereits gezogener Song, nie ein noch nicht gezogener (sonst Test ohne Abspielen mit Hinweis).
- **Spotify-Autostart:** Song mit Spotify-Link, aber Spotify nicht am Bus → Desktop-App per `Gio.DesktopAppInfo` starten, bis 15 s auf `org.mpris.MediaPlayer2.spotify` warten, dann `OpenUri` + Kontrolle; sonst bisheriger Rückfall.
- **Nach Ablauf pausieren:** Beim Übergang Spielzeit → Auflösung pausiert die App Spotify (MPRIS) bzw. die lokale Datei; nicht im Folgen-Modus und nicht bei YouTube.
- **Warnkasten (Spielleitung):** direkt unter den Knöpfen, damit er auch auf 1366×768 ohne Scrollen zu sehen ist; die Knöpfe darüber bewegen sich nicht. Drei Arten: Titel läuft, steht aber nicht auf den Karten (Folgen-Modus, mit „Überspringen“); Spotify hat den Titel nicht gestartet; Song-Timer läuft, aber „Beim Ziehen automatisch abspielen“ ist aus (Spotify oder vorhandene lokale Datei – mit Knopf „Automatisch abspielen“; „Ausblenden“ unterdrückt den Hinweis, bis Timer oder Wiedergabeziel neu gewählt werden).
- **Player-Wahl (MPRIS):** Spotify → nur Spotify; YouTube → Browser. Ein gespeicherter Player hat Vorrang, wenn er zum Ziel passt.
- **Stufen:** 1 Reihe → 2 Reihen → Volle Karte bei weiterlaufender Ziehung (passt zur Prognose); danach neue Runde mit neu gemischter Ziehung. Neue Karten setzen Runde und Gewinnerliste zurück (alte Stände liegen in `sicherungen/`).
- **Startziel der Runde:** Das Gewinnziel, das vor dem ersten Song der Runde von Hand gewählt wird (`round_start_target`, sonst „1 Reihe“). Neue Runden – Stufen-Button nach „Volle Karte“ oder „Neu mischen“ mitten im Spiel – beginnen wieder damit. So bleibt ein Abend nur mit „Volle Karte“ über alle Runden bei diesem Ziel; ein Wechsel mitten in der Runde ändert das Startziel nicht.
- **Gewinner:** nur eintragbar, wenn die Karte das aktuelle Ziel erreicht hat; gleiche Karte und Stufe nie doppelt, andere Stufe nur nach Rückfrage. Nach dem Eintragen bleibt der Song-Timer aus, bis die Spielleitung weitermacht (Leertaste, Stufen-Button) – auch wenn der Player im Folgen-Modus von selbst zum nächsten Titel wechselt (der Titel zählt dann trotzdem).
- **Gewinnkontrolle:** `GameService.target_status()` prüft nach jedem gezogenen Song alle Karten gegen das aktuelle Gewinnziel (`missing_to_target`, 0 = erreicht – dieselbe Regel wie `check_win`). Ergebnis (`TargetStatus`): Karten mit erreichtem Ziel samt Song-Nr., ab der sie es haben (`reached_at`), früheste zuerst; in dieser Runde und Stufe eingetragene Karten (und welche davon nach „Zurück“ nicht mehr am Ziel sind); Karten, die schon eine andere Runde/Stufe gewonnen haben; Anzahl nicht eingetragener Karten mit genau einem fehlenden Song. **Gleichstand** nur, wenn mehrere Karten beim selben (frühesten) Song ans Ziel kamen – ein übersehener früherer Gewinn steht vorn. Anzeige: eine Hinweiszeile direkt unter den Knöpfen (unter dem Warnkasten, auf 1366×768 ohne Scrollen sichtbar) und das Panel „Gewinnkontrolle“ mit höchstens 12 Prüfknöpfen. Ein Knopf öffnet „Bingo prüfen“ mit vorbelegter Kartennummer (Name kann dazu, Timer steht wie bei der normalen Prüfung). Der Beamer zeigt davon nichts, damit niemand vorher weiß, wer gewinnt.
- **Beamer:** zeigt den aktuellen Titel erst nach Aufdecken; „Zuletzt“ enthält nur vorherige Songs. Ist „Titel auf dem Beamer aufdecken“ aus (`beamer_reveal`), bleibt jeder Titel verborgen – beim Aufdecken (T, dann gesperrt), in der Auflösung des Timers und unter „Zuletzt“; das Hauptfenster zeigt ihn weiter. Passt der Inhalt nicht in die Höhe (z. B. 1280×720 mit zweizeiligem Titel und BINGO-Banner), wird die Schrift stufenweise verkleinert (bis 50 %); die Mindestgröße des Fensters hängt nicht von der Textmenge ab.
- **Offline:** Die App öffnet keine Netzwerkverbindungen. MPRIS läuft über den lokalen Sitzungsbus.

## Spielstand

JSON mit `version: 1`, atomar geschrieben, Dateirechte 0600 (nur der Benutzer). Neue Felder (`link`, `playback_target`, `follow_player`, `player_name`, `pause_after_timer` – Standard an, `beamer_reveal` – Standard an, `round_start_target` – Standard „reihe“) sind optional, alte Stände laden weiter. Beim Import werden Typen, Kartenregeln, Ziehreihenfolge und Links geprüft; ungültige Dateien werden abgelehnt, statt still repariert zu werden.

## Kataloge

`musik_bingo/data/catalogs/*.txt` mit Kopf:

```text
# name: Charts aktuell (Top 50, KW 47/2026)
# kategorie: charts            # oder: weihnachten
# quelle: Offizielle Deutsche Charts …
Housewife – Tate McRae
```

Mitgeliefert: Weihnachten (2 Listen) und Charts: Jahrzehnte `charts_1990er`, `charts_2000er`, `charts_2010er`, `charts_2020_2024` (Single-Jahrescharts, Platz 1–10 je Jahr) sowie die aktuellen Listen 2025/2026. Jede Datei erscheint im Zufallsmix automatisch als eigenes Häkchen (sortiert nach Name).
Regel (Test `test_shipped_catalogs_have_unique_titles`): Ein Titel kommt über alle Listen hinweg nur mit **einem** Interpreten vor – bei Konflikten bleibt die bekanntere Fassung.

## Tests

| Ordner | Inhalt |
|---|---|
| `tests/unit` | Fachlogik, Import/Export, Matching, Regressionen |
| `tests/integration` | MPRIS gegen simuliertes Spotify (privater D-Bus), GStreamer, Druck, Installer |
| `tests/security` | kein Netzwerk, Link-Positivliste (Fuzzing), Dateirechte, manipulierte Dateien, Exec-Injection |
| `tests/gui` | echte GTK-Fenster unter Xvfb: Gesamtablauf inkl. PDF, Spotify-E2E, Grenzfälle, Screenshots |
| `tests/support` | simulierter MPRIS-Player |

Release: `scripts/build-release.sh <tag>` baut aus Git ZIP/tar.gz/Prüfsummen und Release-Notizen; `.github/workflows/release.yml` läuft bei Tags `v*`.
