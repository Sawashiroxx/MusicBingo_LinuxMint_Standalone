# Änderungsprotokoll

## Unveröffentlicht

- Zufallsmix: Neue Listen mit deutschen Hits 1990 bis 2024, aus den offiziellen Single-Jahrescharts, jeweils Platz 1–10 je Jahr:
  - 1990er-Hits (97 Songs)
  - 2000er-Hits (99 Songs)
  - 2010er-Hits (98 Songs)
  - 2020er-Hits 2020–2024 (46 Songs)

  Jede Liste ist einzeln wählbar, die aktuellen Listen 2025/2026 bleiben erhalten. Bei gleichem Titel verschiedener Interpreten ist nur die bekanntere Fassung enthalten, etwa „It's My Life“ von Bon Jovi.
- Tests: Neues GUI-Szenario „wie am Abend“ auf einem 1366×768-Bildschirm. Es nutzt echte Dialoge statt automatischer Bestätigung, gehaltene Tasten, echte Mausklicks und Doppelklicks, Tippfehler bei der Kartennummer, lange Spotify-Titel, den Beamer mit langem Gewinnernamen und einen Speicherfehler. Gegen den Stand vor 2.5.1 schlagen 19 von 21 Prüfungen an.
- CI: Fehlt ein GUI-Werkzeug, schlägt der Test fehl, statt still übersprungen zu werden.
- Behoben nach der Abendprüfung (Claude Fable 5.2; geprüft wurde ein Abend mit 3×3-Karten, nur „Volle Karte“, mehreren Runden, Song-Timer und Spotify):
  - **Song-Timer:** Eine eingetippte Zahl gilt, sobald der nächste Song gezogen wird – auch ohne Enter oder Tab. Vorher stand z. B. „15“ im Feld, der Timer blieb aber aus, wenn danach geklickt oder die Leertaste gedrückt wurde.
  - **Song-Timer ohne „Beim Ziehen automatisch abspielen“:** Mit den Vorgaben der App zog der Timer Song um Song weiter, ohne dass je Musik lief, und die Statuszeile meldete „Spotify ist nicht verbunden“. Jetzt erscheint ein Hinweis mit dem Knopf „Automatisch abspielen“ (setzt den Haken und startet den aktuellen Song); „Ausblenden“ merkt sich, dass von Hand abgespielt wird.
  - **Warnungen sichtbar:** Der Warnkasten („läuft, steht aber nicht auf den Karten“, „Spotify hat den Titel nicht gestartet“) steht direkt unter den Knöpfen. Vorher lag er auf einem 1366×768-Laptop unter dem sichtbaren Bereich – „Überspringen“ war nur nach Scrollen zu erreichen.
  - **Mehrere Runden nur mit „Volle Karte“:** Eine neue Runde beginnt mit dem Gewinnziel, das vor dem ersten Song gewählt war. Vorher sprang das Ziel bei jeder neuen Runde auf „1 Reihe“ zurück – auch auf dem Beamer.
  - **Player folgen mit Song-Timer:** Nach „Als Gewinner eintragen“ bleibt der Timer aus, bis die Spielleitung weitermacht. Vorher lief er wieder an, sobald Spotify von selbst zum nächsten Titel wechselte, und schaltete während der Ehrung alle paar Sekunden weiter. Die Rückfrage „Neue Runde“ weist im Folgen-Modus darauf hin, dass der laufende Titel sofort zählt.
  - **Beamer:** Auf kleinen Beamern (1280×720, 1024×768) lag „Zuletzt“ über dem BINGO-Banner, wenn der Titel zweizeilig war. Der Inhalt wird jetzt verkleinert, bis alles passt; das Beamer-Fenster lässt sich auf jede Größe bringen.
  - **Tastatur:** Nach einem versehentlichen Tab beendet auch ein Klick auf einen Knopf (z. B. „Nächsten Song ziehen“) die Tastatur-Navigation. Vorher schaltete die nächste Leertaste dann das Gewinnziel um.
  - **Fenster:** Mit 3×3-Karten war das Fenster mindestens 1380 px breit, breiter als ein 1366-px-Laptop. Die Startgröße passt jetzt auf 1366×768 (die Kopfleiste wurde nicht mitgerechnet).
  - **Import:** Aus Excel/LibreOffice kopierte Zellen und Excel-„Unicode-Text (*.txt)“ werden als Tabelle gelesen. Vorher wurde die Kopfzeile zum Song und der Interpret fehlte.
  - **Zuordnung:** „Killing Me Softly (With His Song)“ wird auch erkannt, wenn der Player den Titel ohne Klammer meldet.
  - **Listen:** „ABBA-esque“ (eine EP mit vier Titeln) steht in der 1990er-Liste jetzt als „Take A Chance On Me – Erasure“.
  - **Texte:** Der Zufallsmix nennt Faustregeln für 3×3, 4×4 und 5×5 statt nur für 5×5; der Tooltip spricht nicht mehr nur von „aktuellen Charts“. README: Hinweis auf „Beim Ziehen automatisch abspielen“ und Planung für 3×3.
  - **Tests:** Zwei GUI-Tests hingen vom Zufall ab („Ohne Kartennummer“ schlug in rund 2 % der Läufe fehl) und stellen ihre Ausgangslage jetzt sicher. Neu: Abend nur mit „Volle Karte“, Beamer mit kleiner Auflösung, Mindestgröße mit 3×3-Karten, Startgröße, Song-Timer ohne automatisches Abspielen, Lage der Warnung auf 1366×768.

## 2.5.1 – November 2026

Behoben nach der dritten Gesamtprüfung (Claude Fable 5.2, höchste Stufe):

- **Bedienung am Abend:**
  - Der Knopf „Nächsten Song ziehen“ springt nicht mehr, wenn ein Titel ein- statt zweizeilig ist. Vorher lag dann „Weiter: 2 Reihen“ unter der Maus.
  - Eine gehaltene Leertaste, Rücktaste, T oder P löst nur noch einmal aus (vorher bis zu 36 Songs in 2 s). Ein Doppelklick auf „Ziehen“ zieht nur einen Song.
  - „Bingo prüfen“: Eine Tippfehler-Nummer (leer, zu groß) meldet „Ungültige Kartennummer“ statt still Karte 1 bzw. die letzte Karte zu prüfen.
  - „Player folgen“ zieht nur Titel, die wirklich laufen, keine pausiert geladenen.
- **Stabilität und Speichern:**
  - Eine Audiodatei ohne Leserecht verhindert nicht mehr den Start und hält den Song-Timer nicht mehr an.
  - Gezogene Songs werden vor dem Neuzeichnen gespeichert.
  - Schlägt das Speichern fehl (Platte voll, alte Ordnernamen), erscheinen ein Dialog und die Markierung „NICHT GESPEICHERT“.
  - Ein beschädigter Spielstand mit ungültigen Zeichen führt zu einer Warnung und einer neuen Runde statt zu einem Start ohne Fenster.
- **Offline-Versprechen:** Präparierte Audiodateien (z. B. QuickTime-Verweise) können keine Netzwerkverbindung mehr auslösen. Die App nutzt nur noch Dateiquellen und spielt nur Ton.
- **Import:**
  - CSV-Dateien mit Hochkommas in Titeln („'N Sync“) verlieren keine Zeilen mehr.
  - Windows-Dateien (cp1252) und Excel-„Unicode-Text“ (UTF-16) werden richtig gelesen.
  - Die Spalte „Spotify ID“ ergibt jetzt Links.
- **Anzeige:**
  - Lange Gewinnernamen oder Feiertitel sprengen die Beamer-Breite nicht mehr.
  - Der Ergebnisdialog passt auf 1366×768.
- **Skripte:**
  - Ein Projektordner mit Backslash im Namen funktioniert im Menüeintrag.
  - Das Update stört sich nicht an verlorenen Ausführungsrechten (USB-Stick, Cloud-Ordner).
- **Aufgeräumt:** Die alte HTML-Urversion (`docs/legacy/`) ist entfernt.
- **Neu:** Die Anleitung für die Spielleitung liegt als PDF in `docs/ANLEITUNG-SPIELLEITUNG.pdf`, mit Spielzeit-Planung, Ablauf und Notfall-Tabelle. Die Screenshots sind aktualisiert.

## 2.5 – November 2026

- **Spotify im Mittelpunkt:**
  - Abspiel-Kontrolle: Nach dem Ziehen prüft die App, ob der Titel in Spotify wirklich läuft. Notfalls schickt sie „Play“ oder öffnet ihn ein zweites Mal, sonst gibt es eine Warnung.
  - Spotify wird automatisch gestartet, wenn es nicht läuft (normale Installation, Snap, Flatpak).
  - Knopf **Spotify testen**: Prüfliste vor der Feier mit Verbindung, Abspielen, Pause, Link-Abdeckung und Autoplay-Hinweis.
  - **Nach Ablauf pausieren:** Läuft die Spielzeit des Song-Timers ab, pausiert die Musik bis zum nächsten Ziehen.
  - **Link-Übersicht:** „x von y Songs direkt abspielbar“. Fehlende Spotify-Links lassen sich per Einfügen nachtragen; „Mit Playlist abgleichen“ überträgt Links auf vorhandene Songs.
- YouTube Music entfernt, normales YouTube bleibt. Alte Spielstände mit YouTube Music laden als YouTube.
- Fenster passt jetzt auf 1366×768-Bildschirme (Seiten scrollen bei Bedarf).
- Update-Menüeintrag sicherer: bricht ab statt einen noch nicht gemergten Stand zurückzusetzen; erkennt neue Stände auch bei gleicher Versionsnummer.
- Behoben (Prüfung durch Claude Fable 5.2, zwei Durchgänge, plus Test-Audit): kein Einfrieren bei hängendem Spotify, Warnung verschwindet bei spätem Start, Pause auch bei Auflösung 0 s, Songliste mit Gedankenstrichen, Einzahl/Mehrzahl in Meldungen.

## 2.4.2 – November 2026

- Neu: Menüeintrag **Musik Bingo aktualisieren** – Update per Klick ohne Terminal. Bricht ab, wenn die App
  läuft oder Dateien im Ordner geändert wurden; bei ZIP-Installation öffnet er die Release-Seite.

## 2.4.1 – November 2026

- Behoben: Tastenkürzel (Leertaste, T, P, Rücktaste) wirkten mit echten Tastendrücken nicht, sobald die
  Seitenleiste den Fokus hatte (Meldung aus dem Einsatz). Neuer Test mit echten Tastendrücken (xdotool).
- Neu: *Bingo prüfen → Ohne Kartennummer …* – Songs der Gewinnreihe anhaken; die App zeigt, ob sie
  gespielt wurden, und findet die passende Karte (bevorzugt Karten mit erreichtem Gewinnziel).

## 2.4 – November 2026

- YouTube Music als viertes Wiedergabeziel (neben lokalen Dateien, Spotify und YouTube): Titel bzw. Suche auf
  music.youtube.com öffnen, „Player folgen“ und „Vom Player einlesen“ mit YouTube-Music-Desktop-App oder Browser.
- Spielleitung: „Player folgen“ in eigener Zeile, damit das Fenster auf 1366-px-Bildschirme passt.
- Hilfe: Abschnitt YouTube Music, Tastenkürzel T und P ergänzt.
- Behoben (Prüfung durch Claude Fable 5.2, zwei Durchgänge):
  - Player beendet/Folgen aus → Song-Timer stoppt, Warnung an die Spielleitung.
  - Playlist einlesen: gleicher Titel/anderer Interpret, doppelte Titel und ein wiederholter erster Titel
    beenden das Einlesen nicht mehr vorzeitig.
  - YouTube Music/Spotify: „ - “ im Titel wird nicht zerlegt.
  - Lokale Wiedergabe kann keine Netzwerkverbindungen mehr auslösen (getarnte HLS/DASH-Dateien).
  - Unlesbarer Spielstand wird vor dem Überschreiben gesichert (`sicherungen/unlesbar_*`).
  - Dritte Bingo-Prüfung derselben Karte, Warnung nach Markieren von Hand, Songliste im Editor
    (`#SELFIE`, Titel mit „ - “), Grenze 2000 Songs, Spotify-Rückfall auf den Webplayer.

## 2.3 – November 2026

- Beamer-Ansicht für die Gäste: zweites Fenster (Vollbild auf dem zweiten Bildschirm), Songtitel verborgen bis
  zum Aufdecken (Taste T), Runde, Gewinnziel, Countdown, zuletzt gespielte Songs, BINGO-Banner.
- Song-Timer: nach einstellbaren Sekunden kurze Auflösung, dann automatisch der nächste Song (auch mit Spotify);
  pausiert während der Bingo-Prüfung, Taste P.
- Gewinnerliste: Eintrag direkt aus „Bingo prüfen“, nur bei erreichtem Ziel, dieselbe Karte nicht doppelt,
  Export als CSV.
- Stufen-Button: 1 Reihe → 2 Reihen → Volle Karte (Ziehung läuft weiter), danach neue Runde (neu gemischt).
- Titel der Feier auf Karten, Kartenvorschau und Beamer.
- Automatisches GitHub-Release: Tag `v*` → Tests → ZIP, tar.gz, Prüfsummen und Release-Notizen.

## 2.2 – November 2026

- Behoben: Dateidialog im dunklen Design unlesbar (App-Design deutete GTK-Klassen `cell`/`sidebar` um).
- Behoben: Fensterklasse passte nicht zum Menüeintrag (Taskleiste/Icon).
- Behoben: Gewinnziel fehlte in der Kopfzeile; Leertaste auf dem „Player folgen“-Schalter zog einen Song;
  veraltete Prognose nach Import ohne Karten.
- Automatische Sicherung vor neuen Karten und vor Import (letzte 10, nur für den Benutzer lesbar).
- Kartenfußzeile neutral: Gewinnziel wird angesagt (statt fest „Reihe oder Spalte“).
- Gleiche Titel von verschiedenen Interpreten: Zufallsmix nimmt nur eine Version, Songliste warnt.
- Tests: Design-Klassen, Text-Kontrast (WCAG), Fensterklasse, Sicherungen; insgesamt 140.

## 2.1 – November 2026

- Startliste neu: 75 Songs, 45 Chart-Hits 2025/26 und 30 Weihnachtslieder gemischt.
- Kataloge: Jahrescharts 2025 komplett (Top 100), weitere Hits 2026.
- Gewinnziel pro Runde (1 Reihe, 2 Reihen, volle Karte); „Bingo prüfen“ prüft genau dieses Ziel.
- Spielprognose nach dem Erzeugen und Gewinngarantie-Prüfung.
- Standardwerte für ~140 Gäste: 160 Karten, Zufallsmix 75 Songs / 40 % Weihnachten.
- Neues App-Icon in allen Größen.

## 2.0 – November 2026

- Neue Oberfläche: Seitenleiste mit drei Bereichen, große Jetzt-Anzeige, Songpool mit Suche, überarbeitetes dunkles/helles Design, eigenes App-Icon, Vollbild (F11).
- Neu gestaltete Druckkarten (Kopfband, Kartennummer, Namensfeld, Gewinnregel).
- Playlist-Import: CSV (Exportify, TuneMyMusic, Soundiiz), M3U/M3U8, kopierte YouTube-Titel; Bereinigung von „(Official Video)“, „Remastered“, „feat.“.
- Playlist-Export als Text (für Spotify/YouTube-Import), CSV oder M3U; Abgleich Karten ↔ Playlist.
- Spotify/YouTube: Wiedergabeziel wählbar, Titel direkt in Spotify starten (MPRIS `OpenUri`) oder im Browser öffnen.
- „Player folgen“: Die Playlist läuft im Player, die App zieht den laufenden Song automatisch und warnt bei Titeln, die nicht auf den Karten stehen; Werbung wird ignoriert.
- „Vom Player einlesen“: laufende Playlist Titel für Titel übernehmen.
- Offline-Kataloge (Stand KW 47/2026): aktuelle Top 50, Jahrescharts 2025, Nummer-1-Hits 2026, Weihnachts-Hits, deutsche Weihnachtslieder; Zufallsmix mit einstellbarem Weihnachtsanteil.
- Bingo-Prüfung zeigt die Karte mit gezogenen Feldern und Gewinnlinie.
- Songpool: Song per Doppelklick von Hand als gezogen markieren.
- Menüeintrag mit Icon, Start ohne Ausführungsrecht, passende Fensterklasse für die Taskleiste.
- Struktur: Daten unter `musik_bingo/data/`, Skripte unter `scripts/`, Tests nach unit/integration/security/gui.
- Sicherheit: Spielstand nur für den Benutzer lesbar (0600), strikte Link-Positivliste, Schutz vor ReDoS und
  Befehls-Injection über Ordnernamen, robuste Behandlung manipulierter Dateien und Player-Daten.
- GitHub-Pipeline: Lint, Unit (Mint 21/22), Integration, Sicherheit, GUI/E2E mit Screenshots.

## 1.0

- Native GTK-3-Desktopanwendung mit geschichteter Python-Struktur.
- Songliste, unterschiedliche Bingo-Karten, PDF-Druck über GTK, Ziehen, Rückgängigmachen und Neu-Mischen.
- Prüfung von Reihen, Spalten und optionalen Diagonalen anhand der gezogenen Songs.
- Optionale lokale Audiowiedergabe, eindeutige Ordnerzuordnung und Autoplay beim Ziehen.
- Versionierter lokaler Spielstand, atomarer Export/Import und Dark-/Light-Design.
