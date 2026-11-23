# Prüfprotokoll

Stand: 20.11.2026 (v2.5.1) · Umgebung: Ubuntu 24.04 (= Basis Linux Mint 22), Python 3.12, GTK 3.24, Xvfb

## Automatisch (auch in der GitHub-Pipeline)

| Suite | Tests | Ergebnis |
|---|---|---|
| Unit (Gewinngarantie, Prognose, Abend-Logik, Timer, Songliste-Fuzzing mit 40 000 Zufallsfällen, Kartensuche, Spotify-Links, Spotify-Prüfliste, CSV ohne Raten, ungültige Zeichen im Spielstand, Jahrzehnt-Kataloge) | 159 | ✅ |
| Integration (Spotify-/YouTube-Simulation inkl. hängendem, verzögertem und umverknüpftem Spotify, Abspiel-Kontrolle, GStreamer-Netzwerksperre, Druck, Installer, Update-Skript, Sicherungen, Release-Bau) | 79 | ✅ |
| Sicherheit (u. a. Windows-/UTF-16-Dateien, präparierte Umleitungsdateien ohne Netz) | 21 | ✅ |
| GUI/E2E unter Xvfb (Gesamtablauf, Abend-Funktionen, Spotify-Abspielen in 11 Varianten, Spotify-Links, YouTube im Browser, echte Tastendrücke, Prüfen ohne Kartennummer, Grenzfälle, Kontrast, Fensterklasse, Mindestgröße 1366×768, Screenshots; „wie am Abend“ auf 1366×768 mit echten Dialogen, gehaltenen Tasten, Mausklicks und Speicherfehler) | 14 | ✅ |
| ruff (Fehler, Bugs, bandit-Sicherheitsregeln), shellcheck | – | ✅ |

In der CI ist ein fehlendes GUI-Werkzeug (xvfb-run, xdotool, xprop …) ein Fehler, kein Überspringen.

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

## Prüfung der Abend-Funktionen (v2.3, Prüfer: Claude Fable 5.2)

8 Befunde, alle behoben und mit Regressionstests abgesichert:
- Leertaste auf zuletzt geklicktem „Titel aufdecken“ hätte den Titel den Gästen gezeigt → Klicks setzen keinen Fokus mehr, T/P wirken immer
- Timer lief bei offenen Dialogen weiter → steht, solange ein Dialog offen ist
- „Bingo prüfen“ hob eine manuelle Timer-Pause auf; Folgen-Modus + Timer blieb bei bekanntem/fremdem Titel stehen
- „Neu mischen“ blockierte echte Gewinner → gilt jetzt als neue Runde
- Aufdecken-Knopf nach Import, Kartenvorschau nach Titeländerung, überlange Titel im Druck, doppelte Gewinner in Dateien, Tasten im Beamer-Fenster, Release: Checkout fest auf den Tag, GUI-Tests auch vor jedem Release

Selbst gefunden: Release-ZIP hätte bei nicht committeten Änderungen neue Versionsnummer mit altem Inhalt bekommen.
Nicht prüfbar: Platzierung auf einem echten zweiten Bildschirm (Testumgebung hat einen Monitor).

## Prüfung v2.4 (YouTube Music, Prüfer: Claude Fable 5.2, zwei Durchgänge)

1. Durchgang: 11 Befunde (keiner schwer), alle nachgestellt, behoben und mit Regressionstests abgesichert. Jeder neue Test schlägt mit dem alten Code fehl.
- Song-Timer zog nach Ende von „Player folgen“ weiter Songs, die niemand gehört hat
- Playlist einlesen brach bei doppelten Titeln oder gleichem Titel anderer Interpreten vorzeitig ab
- YouTube-Music-Titel mit „ - “ wurden zerlegt
- als .mp3 getarnte HLS-Playlist ließ GStreamer Daten aus dem Netz laden (Verstoß gegen „offline“)
- unlesbarer Spielstand wurde beim Schließen ohne Kopie überschrieben
- weitere: dritte Bingo-Prüfung, Warnung nach Markieren von Hand, Songliste im Editor, mehr als 2000 Songs, Statustext, Spotify-Rückfall

2. Durchgang (Prüfung der Korrekturen): 9 von 11 bestätigt; Lücken behoben: YouTube Music im Browser ohne URL, erster Titel doppelt in der Playlist, Zuordnungen über „Ordner zuordnen“, gescheitertes Einschalten von „Player folgen“ stoppte den Timer, „#Abschnitt“-Zeilen bleiben Kommentare.
Bewusst so belassen: Titel, die mit „# “ beginnen, werden im Editor als „＃ “ geschrieben; Gedankenstriche im Interpreten als Bindestrich.
Nicht prüfbar: echte YouTube-Music-App, echter Browser (ob „Weiter“ und Titel-URL über MPRIS ankommen), echte Lautsprecher.

## v2.4.1: Meldung aus dem Einsatz

Tastenkürzel wirkten nicht. Ursache: GTK schaltet bei jedem echten Tastendruck die Fokus-Anzeige ein; die App hielt den Seitenleisten-Eintrag deshalb für „per Tab angesteuert“ und gab ihm die Leertaste. Die bisherigen Tests riefen den Tasten-Handler direkt auf und konnten das nicht sehen. Neu: Test mit echten Tastendrücken über xdotool (schlägt mit dem alten Code fehl).

## v2.5: Prüfung und Test-Audit (Claude Fable 5.2, zwei Durchgänge)

**Funktionen** – 1. Durchgang, 8 Befunde, alle behoben:
- Oberfläche fror ~26 s ein, wenn Spotify hängt
- Updater hätte einen noch nicht gemergten Stand auf main zurückgesetzt
- Spotify-Warnung blieb nach spätem Start stehen
- „Nach Ablauf pausieren“ wirkte nicht bei Auflösung 0 s
- Fenster mindestens 960 px hoch (passte nicht auf 1366×768)
- „Spotify testen“ konnte doppelt laufen bzw. einen noch nicht gezogenen Song abspielen
- Songliste: Titel mit Gedankenstrich am Ende
- „1 Links“

2. Durchgang: alle Korrekturen hielten; 7 Randfälle behoben (Warnung nach erneutem Abspielen, Pause wenn der nächste Song keinen Link hat, Klon nur eines Zweigs im Updater, Nachbeobachtung nach „Karten erzeugen“, Umverknüpfung mit Zusätzen/mehreren Interpreten, Einzahl/Mehrzahl bei Songs/Karten/Zeilen, ein unzuverlässiger Testschritt).

**Test-Audit** (wurden Tests an Fehler angepasst?):
- Alle 9 geprüften Stellen, an denen Erwartungen geändert wurden, testen das richtige Verhalten. Zwei waren zu schwach und wurden verschärft: Songliste-Fuzzing jetzt auch mit Zufallszeichen und ausdrücklicher Ersetzungsliste; Mindestgröße prüft jetzt auch die Höhe.
- Mutationstest (absichtlich eingebaute Fehler): 1. Durchgang 25 von 27 erkannt, 2. Durchgang 19 von 24 (+1 gleichwertig). Alle nicht erkannten, die echtes Verhalten betreffen, sind jetzt mit Tests abgedeckt – auch die letzten drei (Signal während des Ladens, Schließen der Player-Verbindung, Hinweis im Testdialog ohne Testsong); jeder neue Test schlägt mit der jeweiligen Mutation fehl.
- Jeder neue Test schlägt mit dem alten Code fehl (geprüft).

Nicht prüfbar ohne echtes Gerät: echtes Spotify (Startzeit, Umverknüpfung, Verhalten bei Hängern), Fenster unter Cinnamon mit Panel, Beamer, Lautsprecher.

## Vor der Feier einmal von Hand (echter Rechner)

1. `bash scripts/install-desktop.sh`, App über das Menü starten
2. Karten erzeugen → *Drucken / PDF* → eine Seite prüfen
3. In Spotify „Autoplay“ ausschalten, dann in der App *Spotify testen* – alle Punkte ✓, Playlist abspielen → *Player folgen* → Song wird gezogen; *Weiter* springt im Player zum nächsten Titel
4. Einen Song ohne Folgen-Modus mit *Abspielen* in Spotify starten
5. App schließen und neu öffnen → Stand ist erhalten
6. Beamer anschließen, *Beamer öffnen* → Fenster erscheint im Vollbild auf dem Beamer, Titel verdeckt, T deckt auf

Nicht automatisch prüfbar: echte Spotify-/Browser-Anbindung (simuliert getestet), echter Drucker, Tonausgabe.
