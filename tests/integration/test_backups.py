"""Automatische Sicherungen des Spielstands (Schutz für bereits gedruckte Karten)."""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from musik_bingo.application.game_service import GameService
from musik_bingo.infrastructure.file_store import MAX_BACKUPS, MAX_CARD_SET_BACKUPS, FileStore


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

    def test_card_sets_are_not_pushed_out_by_other_backups(self):
        """Regression 2.6.2: Sicherungen „vor neuen Karten“ (ein anderer, evtl. gedruckter Kartensatz) rotierten
        mit allen übrigen nach 10 heraus – z. B. nach zehn Importen war der gedruckte Satz weg."""
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "spielstand.json")
            printed = service("Gedruckt")
            store.save(printed)
            first = store.backup("vor-neuen-karten")
            for i in range(MAX_BACKUPS + 5):
                store.save(service(f"S{i}"))
                store.backup("vor-import")
            self.assertTrue(first.exists())
            self.assertEqual(FileStore.import_from(first).game.cards[0].songs, printed.game.cards[0].songs)
            names = [path.name for path in store.backups()]
            self.assertEqual(sum(name.endswith("_vor-import.json") for name in names), MAX_BACKUPS)
            for _ in range(MAX_CARD_SET_BACKUPS + 2):
                store.backup("vor-neuen-karten")
            card_sets = [path for path in store.backups() if path.name.endswith("_vor-neuen-karten.json")]
            self.assertEqual(len(card_sets), MAX_CARD_SET_BACKUPS)
            self.assertFalse(first.exists())  # auch Kartensätze haben eine Grenze, nur eine großzügige

    def test_copy_of_unreadable_file_is_never_rotated_away(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "spielstand.json")
            store.path.write_text('{"version": 99}')
            kept = store.backup("unlesbar", keep=True)
            self.assertTrue(kept.name.startswith("unlesbar_"))
            for i in range(MAX_BACKUPS + 3):
                store.save(service(f"S{i}"))
                store.backup(f"runde-{i}")
            self.assertEqual(kept.read_text(), '{"version": 99}')
            self.assertEqual(len(store.backups()), MAX_BACKUPS)
            self.assertEqual(stat.S_IMODE(kept.stat().st_mode) & 0o077, 0)

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
