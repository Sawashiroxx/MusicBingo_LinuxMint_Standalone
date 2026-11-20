# Änderungsprotokoll

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
