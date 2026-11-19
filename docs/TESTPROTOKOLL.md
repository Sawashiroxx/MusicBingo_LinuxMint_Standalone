# Prüfprotokoll

Stand: 19.11.2026 (v2.2) · Umgebung: Ubuntu 24.04 (= Basis Linux Mint 22), Python 3.12, GTK 3.24, Xvfb

## Automatisch (auch in der GitHub-Pipeline)

| Suite | Tests | Ergebnis |
|---|---|---|
| Unit (inkl. Gewinngarantie, Prognose, Design-Klassen) | 98 | ✅ |
| Integration (Spotify-Simulation über D-Bus, GStreamer, Druck, Installer, Sicherungen) | 22 | ✅ |
| Sicherheit | 14 | ✅ |
| GUI/E2E unter Xvfb (Gesamtablauf, Spotify, Grenzfälle, Kontrast, Fensterklasse, Screenshots) | 6 | ✅ |
| ruff (Fehler, Bugs, bandit-Sicherheitsregeln), shellcheck | – | ✅ |

## Gewinngarantie (140 Gäste)

- Simulation mit 120/140/170 Karten und 60/75/90 Songs: Die Kartenzahl ändert den Ablauf kaum, die Songzahl bestimmt die Spiellänge.
- Standard (75 Songs, 160 Karten, 5×5): 1 Reihe nach ~16, 2 Reihen nach ~30, volle Karte nach ~63 Songs; meist genau ein Gewinner.
- Getestet: Nach allen Songs gewinnt jede Karte jedes Ziel; in 40 zufälligen Spielen gab es immer Gewinner; fehlt ein Kartensong in der Playlist, schlägt die Garantie-Prüfung an.

## Unabhängige Code-Prüfung

Ein separater Prüfdurchgang fand 11 Befunde. Alle wurden behoben und durch Regressionstests abgesichert (`tests/unit/test_regressions.py`, `tests/integration/test_mpris.py`, `tests/gui/scenarios/follow_spotify.py`):

- „Zurück“ wurde im Folgen-Modus sofort wieder gezogen
- „Vom Player einlesen“ zog im Folgen-Modus alle Songs
- Regex-Rückfallexplosion bei manipulierten Titeln (> 100 s → < 1 ms)
- Cover anderer Künstler wurden als Original erkannt
- Bindestriche im Titel gingen beim Speichern verloren
- falscher Player nach Zielwechsel; synchrones D-Bus im Einlesen; Werbung/Abbruch beim Einlesen
- sehr tief verschachtelte JSON verhinderte den Start; CSV-Fehler; Kleinigkeiten (Rundung, URL-Kodierung)

Zusätzlich durch die neuen Tests gefunden und behoben: leeres PDF ohne `python3-gi-cairo`, Absturz bei Player-Metadaten mit falschen Typen, Exec-Maskierung bei Sonderzeichen im Ordnernamen.

## Zweite Gesamtprüfung (v2.2)

Unabhängige Prüfung plus eigene Tests fanden 8 weitere Punkte, alle behoben und mit Tests abgesichert: unlesbarer Dateidialog (Meldung aus dem echten Einsatz), falsche Fensterklasse, fehlende Sicherung vor neuen Karten, irreführende Kartenfußzeile, Gewinnziel nicht sichtbar, Leertaste auf Schalter, veraltete Prognose, doppelter Titel „Last Christmas“.
Belegt ohne Befund: Prognose stimmt für 3×3/4×4/5×5 mit/ohne Freifeld/Diagonalen exakt mit Nachspielen überein; 160 Karten → 80 A4-Seiten in 0,3 s; `pip install` enthält alle Daten; Start über den Menüeintrag aus frischem GitHub-Klon.

## Vor der Feier einmal von Hand (echter Rechner)

1. `bash scripts/install-desktop.sh`, App über das Menü starten
2. Karten erzeugen → *Drucken / PDF* → eine Seite prüfen
3. Spotify-Desktop-App starten, Playlist abspielen → *Player folgen* → Song wird gezogen
4. Einen Song ohne Folgen-Modus mit *Abspielen* in Spotify starten
5. App schließen und neu öffnen → Stand ist erhalten

Nicht automatisch prüfbar: echte Spotify-/Browser-Anbindung (simuliert getestet), echter Drucker, Tonausgabe.
