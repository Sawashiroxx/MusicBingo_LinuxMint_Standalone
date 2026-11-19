# Mitwirken

1. Branch `feature/<kurzname>` von `main` anlegen
2. Änderung in der passenden Schicht umsetzen (siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md)) und Tests ergänzen
3. Lokal prüfen:
   ```bash
   PYTHONPATH=. python3 -m unittest discover -v   # GUI-Tests brauchen xvfb + dbus
   ruff check musik_bingo tests
   shellcheck scripts/*.sh
   ```
4. Pull Request nach `main`; CI muss grün sein

Keine Spielstände, Audiodateien, privaten Notizen oder Zugangsdaten committen.
