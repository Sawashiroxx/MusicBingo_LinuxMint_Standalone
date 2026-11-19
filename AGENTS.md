# Projektregeln

- Stack: Python 3 + GTK 3 (PyGObject). GStreamer optional. Keine pip-Abhängigkeiten.
- Schichten einhalten (siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md)): keine GTK-, Datei- oder D-Bus-Importe in `domain/`.
- **Offline:** Die App stellt selbst keine Netzwerkverbindung her. Spotify/YouTube nur lokal über MPRIS oder als vom Nutzer ausgelöstes Öffnen im Browser.
- Sichtbare Texte auf Deutsch.
- Für Änderungen an Spielregeln, Import/Export, Player oder Druck passende Tests ergänzen.
- Vor dem Commit: `PYTHONPATH=. python3 -m unittest discover -v` und `ruff check musik_bingo tests`
- Tests in den passenden Ordner: `unit`, `integration`, `security`, `gui`
- Änderungen über Branch + Pull Request nach `main`; CI muss grün sein.
- Keine Spielstände, Audiodateien, privaten Notizen, persönlichen Pfade oder Zugangsdaten committen.
- Bei Änderungen an Ablauf, Datenformat oder Start: README und `docs/` mitpflegen.
