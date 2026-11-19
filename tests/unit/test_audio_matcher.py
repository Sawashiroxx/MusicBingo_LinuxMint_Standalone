import tempfile
import unittest
from pathlib import Path

from musik_bingo.domain.models import Song
from musik_bingo.infrastructure.audio_matcher import match_audio_files


class AudioMatcherTests(unittest.TestCase):
    def make_files(self, folder: Path, names: list[str]) -> None:
        for name in names:
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def test_matches_exact_title_artist_case_and_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.make_files(folder, ["sammlung/Jól – Beyoncé.mp3"])
            songs = [Song("Jol", "Beyonce")]

            matched, unmatched = match_audio_files(songs, folder)

            self.assertEqual(matched, {"jol – beyonce": str((folder / "sammlung/Jól – Beyoncé.mp3").resolve())})
            self.assertEqual(unmatched, [])

    def test_unique_title_only_file_is_a_safe_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.make_files(folder, ["Last Christmas.ogg"])

            matched, unmatched = match_audio_files([Song("Last Christmas", "Wham!")], folder)

            self.assertEqual(len(matched), 1)
            self.assertEqual(unmatched, [])

    def test_ambiguous_title_or_duplicate_file_is_not_matched(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.make_files(folder, ["Song.mp3", "Song.wav"])
            songs = [Song("Song", "Artist A"), Song("Song", "Artist B")]

            matched, unmatched = match_audio_files(songs, folder)

            self.assertEqual(matched, {})
            self.assertEqual(unmatched, songs)

    def test_multiple_exact_audio_files_remain_unmatched(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.make_files(folder, ["Title – Artist.mp3", "archive/Title – Artist.wav"])

            matched, unmatched = match_audio_files([Song("Title", "Artist")], folder)

            self.assertEqual(matched, {})
            self.assertEqual(unmatched, [Song("Title", "Artist")])

    def test_composite_names_do_not_collide_at_title_artist_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.make_files(folder, ["AB – C.mp3"])
            songs = [Song("AB", "C"), Song("A", "BC")]

            matched, unmatched = match_audio_files(songs, folder)

            self.assertEqual(len(matched), 1)
            self.assertEqual(matched["ab – c"], str((folder / "AB – C.mp3").resolve()))
            self.assertEqual(unmatched, [songs[1]])

    def test_unsupported_extensions_are_ignored_and_missing_folder_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.make_files(folder, ["Song.txt"])

            matched, unmatched = match_audio_files([Song("Song")], folder)

            self.assertEqual(matched, {})
            self.assertEqual(unmatched, [Song("Song")])
            with self.assertRaises(NotADirectoryError):
                match_audio_files([], folder / "missing")


if __name__ == "__main__":
    unittest.main()
