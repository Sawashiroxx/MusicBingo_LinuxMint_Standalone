# Änderungsprotokoll

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
