# Prüfprotokoll

Stand: 26.11.2026 (v2.6.2: Rundennummer auf dem Beamer abschaltbar; v2.6.1: „Zuletzt“ auf dem Beamer einstellbar, geprüft von Claude Fable 5.2; v2.6.0: Abendprüfung + Gewinnkontrolle/Beamer-Aufdecken) · Umgebung: Ubuntu 24.04 (= Basis Linux Mint 22), Python 3.12, GTK 3.24, Xvfb

## Automatisch (auch in der GitHub-Pipeline)

| Suite | Tests | Ergebnis |
|---|---|---|
| Unit (Gewinngarantie, Prognose, Abend-Logik, Timer, Songliste-Fuzzing mit 40 000 Zufallsfällen, Kartensuche, Spotify-Links, Spotify-Prüfliste, CSV ohne Raten, ungültige Zeichen im Spielstand, Jahrzehnt-Kataloge, Startziel der Runde, Tabellen-Text, Gewinnkontrolle, Beamer ohne Aufdecken, „Zuletzt“-Anzahl/-Größe inkl. manipulierter Werte) | 190 | ✅ |
| Integration (Spotify-/YouTube-Simulation inkl. hängendem, verzögertem und umverknüpftem Spotify, Abspiel-Kontrolle, GStreamer-Netzwerksperre, Druck, Installer, Update-Skript, Sicherungen, Release-Bau inkl. Release-Notizen je Version) | 83 | ✅ |
| Sicherheit (u. a. Windows-/UTF-16-Dateien auch als *.txt, präparierte Umleitungsdateien ohne Netz) | 21 | ✅ |
| GUI/E2E unter Xvfb (Gesamtablauf, Abend-Funktionen, Spotify-Abspielen in 12 Varianten, Spotify-Links, YouTube im Browser, echte Tastendrücke, Prüfen ohne Kartennummer, Grenzfälle, Kontrast, Fensterklasse, Mindestgröße 1366×768, Screenshots; „wie am Abend“ auf 1366×768 mit echten Dialogen, gehaltenen Tasten, Mausklicks und Speicherfehler; Abend nur mit „Volle Karte“ über mehrere Runden; Beamer auf 1280×720 und 1024×768; Gewinnkontrolle mit Prüfknopf, Gleichstand und Zielwechsel; Beamer ohne Aufdecken; „Zuletzt“ einstellbar auf 1280×720/1024×768/1920×1080 mit einer Zeile je Song; echtes Mausrad über Zahlenfeldern; Gewinnkontrolle mit fester Ziehreihenfolge; Runde auf dem Beamer abschaltbar auf 1366×768; Befunde der Gesamtprüfung 2.6.2 inkl. Pfeiltasten und gehaltenem Enter mit echten Tastendrücken) | 22 | ✅ |
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

## Abendprüfung (v2.5.1 + Jahrzehnt-Listen, Prüfer: Claude Fable 5.2)

Geprüft wurde der geplante Abend: 3×3-Karten, nur „Volle Karte“, mehrere Runden mit denselben Karten, Song-Timer 15 s + 5 s, Spotify (Songs per Link oder „Player folgen“), Laptop 1366×768 mit Beamer. Die Korrekturen aus 2.5.1 hielten (alle Nachstellungen der dritten Gesamtprüfung wiederholt). Neu gefunden und behoben, jeweils mit Regressionstest, der mit dem alten Code fehlschlägt:

- eingetippter Song-Timer galt ohne Enter/Tab nicht („15“ im Feld, Timer aus)
- Song-Timer ohne „Beim Ziehen automatisch abspielen“ (Vorgabe): Die Ziehung lief stumm weiter, ohne Hinweis
- Warnkasten lag auf 1366×768 unter dem sichtbaren Bereich (5 von 62 px zu sehen)
- Gewinnziel sprang bei jeder neuen Runde auf „1 Reihe“ zurück (Beamer zeigte den Gästen das falsche Ziel)
- Folgen-Modus: Der Song-Timer lief nach eingetragenem Gewinner von selbst wieder an, sobald Spotify den Titel wechselte
- Beamer mit 1280×720/1024×768: „Zuletzt“ lag über dem BINGO-Banner
- Klick auf einen Knopf beendete die Tastatur-Navigation nicht
- 3×3: Fenster mindestens 1380 px breit; Startgröße 876 px hoch
- Excel-„Unicode-Text (*.txt)“ und kopierte Tabellenzellen wurden als Textliste gelesen
- ein GUI-Test schlug in rund 2 % der Läufe zufällig fehl

Offen und für den Abend wichtig: Tab oder Pfeiltasten schalten weiterhin die Tastatur-Navigation ein (danach bedient die Leertaste das markierte Element, bis geklickt wird).
Nicht prüfbar: Verhalten unter Cinnamon (Maximieren, Vollbild auf dem zweiten Bildschirm), echtes Spotify, echter Beamer.

## v2.6.2: Runde auf dem Beamer abschaltbar (Prüfer: Claude Fable 5.2)

Anlass: Nach Proberunden mit „Neu mischen“ stand auf dem Beamer „Runde 10“; die Karten waren schon gedruckt.

Geprüft: Laden, Speichern, Import (auch alte und manipulierte Stände), Start mit und ohne Spielstand, neue Runde, Zielwechsel, BINGO-Banner (kein Beamer-Text enthält dann „Runde“), Tastatur und Tab-Reihenfolge, Mausrad, Einpassen auf 1280×720, Update von 2.6.1 mit `aktualisieren.sh` (Spielstand byte-gleich, Karten identisch) und Rückweg auf 2.6.1.

Selbst gefunden (GUI-Test): In der Zeile neben „Titel auf dem Beamer aufdecken“ machte der Schalter das Fenster mindestens 1466 px breit. Jetzt eigene Zeile, Mindestbreite 1272 px.

Mutationsprüfung: 8 von 8 eingebauten Fehlern erkannt. Jeder neue Test schlägt mit dem alten Code fehl.

### Gesamtprüfung 2.6.2 (Claude Fable 5.2)

Urteil: einsatzfähig, kein blockierender Befund. Geprüft u. a.:
- 400 Zufallsspiele: Gewinnkontrolle, „Bingo prüfen“ und Nachspielen Song für Song stimmen überein, keine Abweichung.
- 11 Läufe zufälliger Bedienung mit bis zu 1500 Schritten, Prüfungen nach jedem Schritt.
- `kill -9` mitten in Runde 2: nach dem Neustart alles wieder da.
- Zweiter Start, Tempo mit 170 Karten.

Behoben, jeweils mit Test, der mit dem Stand davor anschlägt:
- Gleichstand hinter einer Reservekarte
- Pfeiltasten mit Fokus in der Seitenleiste
- Steuerung drängte sich vor die Spotify-Suche
- Bildschirmschoner während des Spiels
- Sicherungen gedruckter Kartensätze rotierten heraus
- Banner nach „Gewinner löschen“
- Gehaltenes Enter
- Export ohne lokalen Pfad
- Sicherungsordner im Import-Dialog

Bewusst offen: „Nicht vergeben“ wird nicht gespeichert. Gespeichert bräuchte es einen Weg zum Zurücksetzen, sonst bliebe ein Fehlklick dauerhaft.

Nicht prüfbar: Beamer als echter zweiter Bildschirm (auch Aus- und Einstecken), Spotify-Fokus unter Cinnamon, ob Cinnamon die Bildschirmschoner-Sperre beachtet.

Bekannt, nicht durch diese Änderung: `tasten.py` auf 1366×768 statt 1600×1000 scheitert an einer Prüfung (Feld „Auflösung“ liegt unter dem Bildschirmrand, der echte Klick trifft daneben) – mit 2.6.1 genauso. In der Pipeline läuft das Szenario auf 1600×1000.

## v2.6.1: Prüfung „Zuletzt“ auf dem Beamer (Prüfer: Claude Fable 5.2)

Geprüft: Anzahl 0–5 und Reihenfolge (aktueller Song nie dabei, auch nach „Zurück“), Aufdecken an/aus, Einpassen auf 1280×720, 1024×768 und 1920×1080 mit langen zweizeiligen Titeln, Countdown und BINGO-Banner, Speichern/Laden/Import mit manipulierten Werten, Sperren/Entsperren, Lage des Panels auf 1366×768, Tastatur und Mausrad mit echten Eingaben.

Gefunden und behoben:

- lange Einträge unter „Zuletzt“ brachen um; die Fortsetzungszeile sah wie ein eigener Song aus (bis 9 Zeilen statt 6 auf 1024×768) und verkleinerte den Songtitel unnötig
- Mausrad über Zahlenfeld oder Auswahlliste änderte den Wert, statt die Seite zu rollen (Song-Timer 0 → 5 s, „Zuletzt“ 3 → 2, Normal → Groß) – auch bei den schon vorhandenen Timer-Feldern
- eingetippte Anzahl galt beim Ziehen nicht; leeres Feld (Rücktaste im Feld) wurde zu 0
- Import: Liste/Objekt als Größe → englische Meldung „unhashable type“
- Release-Skript hätte für 2.6.1 die Notizen von 2.6.0 geliefert
- GUI-Szenario „Gewinnkontrolle“ schlug zufällig fehl (Fehler im Test: zufälliger erster Song; 3 von 25 Läufen), jetzt feste Reihenfolge, 20 Läufe in Folge grün

Ergebnis des Einpassens nach der Korrektur: alles im Bild, nichts überlappt, Songtitel nie gekürzt. Kleinste Stufe im GUI-Szenario 66 %, in der Messung mit zweizeiligem Titel 60 % (5 Songs „Sehr groß“, Banner, Countdown). Auf 1280×720 ist ein zweizeiliger Songtitel mit 3 Songs in „Sehr groß“ und Countdown 72 px hoch (mit Banner 61 px), auf 1920×1080 92 px. Im Verhältnis zur Bildhöhe ist das etwa gleich groß oder größer – ein Beamer zeigt beide Auflösungen auf derselben Leinwand.

Die Zeile „Zuletzt“ schiebt im Panel „Beamer & Timer“ nur die Timer-Zeile und die Abspiel-Knöpfe 58 px tiefer. Ziehen-Knopf, Warnkasten und Gewinn-Hinweis liegen darüber und bleiben an ihrer Stelle; das Panel lag auf 1366×768 schon vorher unter dem sichtbaren Bereich.

Mutationsprüfung (absichtlich eingebaute Fehler, in einer Kopie): vor den Ergänzungen 15 von 19 erkannt, danach 18 von 19; der letzte ist gleichwertig (Umbruch zusätzlich zur Ellipse ändert die Anzeige nicht). Jeder neue Test schlägt mit dem alten Code fehl (geprüft).

Nicht geprüft: echter Beamer und Lesbarkeit aus echter Entfernung, Touchpad mit feinem Rollen (geprüft wurde das Mausrad per XTEST), Cinnamon. Das Beamer-Bild in der Anleitung zeigt noch die alte „Zuletzt“-Zeile.

## Vor der Feier einmal von Hand (echter Rechner)

1. `bash scripts/install-desktop.sh`, App über das Menü starten
2. Karten erzeugen → *Drucken / PDF* → eine Seite prüfen
3. In Spotify „Autoplay“ ausschalten, dann in der App *Spotify testen* – alle Punkte ✓, Playlist abspielen → *Player folgen* → Song wird gezogen; *Weiter* springt im Player zum nächsten Titel
4. Einen Song ohne Folgen-Modus mit *Abspielen* in Spotify starten
5. App schließen und neu öffnen → Stand ist erhalten
6. Beamer anschließen, *Beamer öffnen* → Fenster erscheint im Vollbild auf dem Beamer, Titel verdeckt, T deckt auf; von den hintersten Plätzen aus prüfen, ob „Zuletzt“ lesbar ist – sonst unter „Beamer & Timer“ Größe erhöhen oder Anzahl senken

Nicht automatisch prüfbar: echte Spotify-/Browser-Anbindung (simuliert getestet), echter Drucker, Tonausgabe.
