"""Automatische Sicherungen des Spielstands (Schutz für bereits gedruckte Karten)."""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from musik_bingo.application.game_service import GameService
from musik_bingo.infrastructure.file_store import MAX_BACKUPS, FileStore


def service(seed_text: str) -> GameService:
    result = GameService()
    result.set_song_text("\n".join(f"{seed_text} {i} – A" for i in range(12)))
    result.create_cards(3, False, 4)
    return result


class BackupTests(unittest.TestCase):
    def test_backup_keeps_old_cards_and_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "spielstand.json")
            self.assertIsNone(store.backup("leer"))  # noch kein Spielstand
            first = service("Alt")
            store.save(first)
            backup = store.backup("vor-neuen-karten")
            store.save(service("Neu"))
            restored = FileStore.import_from(backup)
            self.assertEqual(restored.game.cards[0].songs, first.game.cards[0].songs)
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode) & 0o077, 0)
            self.assertEqual(stat.S_IMODE(store.backup_dir.stat().st_mode) & 0o077, 0)

    def test_rotation_and_safe_names(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "spielstand.json")
            store.save(service("X"))
            for index in range(MAX_BACKUPS + 5):
                store.backup(f"../../etc/passwd {index}")
            backups = store.backups()
            self.assertEqual(len(backups), MAX_BACKUPS)
            self.assertTrue(all(b.parent == store.backup_dir for b in backups))
            self.assertTrue(all(".." not in b.name and "/" not in b.name for b in backups))
            self.assertTrue(all(json.loads(b.read_text())["version"] == 1 for b in backups))
            # neueste zuerst, die ältesten wurden entfernt
            self.assertIn(f"passwd-{MAX_BACKUPS + 4}", backups[0].name)  # 15 Sicherungen: 0 … 14
            self.assertIn("passwd-5", backups[-1].name)


if __name__ == "__main__":
    unittest.main()
