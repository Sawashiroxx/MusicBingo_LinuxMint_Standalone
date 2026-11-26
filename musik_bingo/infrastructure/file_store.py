import json
import os
import tempfile
from pathlib import Path

from musik_bingo.application.game_service import GameService


def default_data_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "musik-bingo" / "spielstand.json"


MAX_BACKUPS = 10
MAX_CARD_SET_BACKUPS = 50
CARD_SET_REASON = "vor-neuen-karten"


class FileStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_data_path()

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / "sicherungen"

    def backup(self, reason: str, keep: bool = False) -> Path | None:
        """Sichert den aktuellen Spielstand, bevor er ersetzt wird (z. B. neue Karten).

        Gedruckte Karten bleiben so prüfbar, auch wenn versehentlich neu erzeugt
        wurde. Sicherungen „vor neuen Karten“ (ein anderer, evtl. gedruckter Kartensatz) werden bis
        MAX_CARD_SET_BACKUPS aufbewahrt, alle übrigen bis MAX_BACKUPS – getrennt gezählt, damit Importe oder
        andere Sicherungen einen gedruckten Kartensatz nicht verdrängen.
        ``keep``: Kopie einer unlesbaren Datei – sie zählt nicht zur Rotation und wird nie gelöscht.
        """
        if not self.path.is_file():
            return None
        import datetime
        import re
        safe_reason = re.sub(r"[^a-z0-9-]+", "-", reason.casefold()).strip("-")[:30] or "sicherung"
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        prefix = "unlesbar" if keep else "spielstand"
        target = self.backup_dir / f"{prefix}_{stamp}_{safe_reason}.json"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.backup_dir, 0o700)
        data = self.path.read_bytes()
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        backups = sorted(self.backup_dir.glob("spielstand_*.json"))
        # Sicherungen „vor neuen Karten“ enthalten einen ANDEREN (evtl. gedruckten) Kartensatz: eigene, großzügige Grenze
        card_sets = [path for path in backups if path.name.endswith(f"_{CARD_SET_REASON}.json")]
        others = [path for path in backups if path not in card_sets]
        for old in others[:-MAX_BACKUPS] + card_sets[:-MAX_CARD_SET_BACKUPS]:
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
                # ensure_ascii: Dateipfade mit Bytes außerhalb von UTF-8 (alte Latin-1-Ordnernamen) kommen als
                # Ersatzzeichen an und ließen sich sonst nicht schreiben – danach scheiterte JEDES Speichern.
                json.dump(service.to_dict(), temporary, ensure_ascii=True, indent=2)
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
