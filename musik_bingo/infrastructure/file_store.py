import json
import os
import tempfile
from pathlib import Path

from musik_bingo.application.game_service import GameService


def default_data_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "musik-bingo" / "spielstand.json"


MAX_BACKUPS = 10


class FileStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_data_path()

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / "sicherungen"

    def backup(self, reason: str) -> Path | None:
        """Sichert den aktuellen Spielstand, bevor er ersetzt wird (z. B. neue Karten).

        Gedruckte Karten bleiben so prüfbar, auch wenn versehentlich neu erzeugt
        wurde. Es werden die letzten MAX_BACKUPS Sicherungen aufbewahrt.
        """
        if not self.path.is_file():
            return None
        import datetime
        import re
        safe_reason = re.sub(r"[^a-z0-9-]+", "-", reason.casefold()).strip("-")[:30] or "sicherung"
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        target = self.backup_dir / f"spielstand_{stamp}_{safe_reason}.json"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.backup_dir, 0o700)
        data = self.path.read_bytes()
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        backups = sorted(self.backup_dir.glob("spielstand_*.json"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)
        return target

    def backups(self) -> list[Path]:
        return sorted(self.backup_dir.glob("spielstand_*.json"), reverse=True)

    def load(self) -> GameService | None:
        if not self.path.exists():
            return None
        return GameService.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, service: GameService) -> None:
        self._write_atomic(self.path, service)

    @staticmethod
    def export_to(path: Path, service: GameService) -> None:
        FileStore._write_atomic(path, service)

    @staticmethod
    def _write_atomic(path: Path, service: GameService) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(service.to_dict(), temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def import_from(path: Path) -> GameService:
        return GameService.from_dict(json.loads(path.read_text(encoding="utf-8")))
