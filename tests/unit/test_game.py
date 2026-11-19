import json
import tempfile
import unittest
from pathlib import Path

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.caller import Caller
from musik_bingo.domain.card_generator import (
    NotEnoughSongs,
    generate_cards,
    required_songs,
    unique_card_capacity,
    winning_lines,
)
from musik_bingo.domain.models import BingoCard, Song
from musik_bingo.domain.song_list import parse_songs
from musik_bingo.infrastructure.file_store import FileStore


class SongListTests(unittest.TestCase):
    def test_parses_and_deduplicates_case_insensitively(self):
        songs = parse_songs("Last Christmas – Wham!\n\nlast christmas – wham!\nSilent Night")
        self.assertEqual(songs, [Song("Last Christmas", "Wham!"), Song("Silent Night")])

    def test_accepts_hyphen_and_em_dash(self):
        self.assertEqual(parse_songs("Song — Artist\nOther - Performer"), [Song("Song", "Artist"), Song("Other", "Performer")])


class CardGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.songs = [Song(f"Song {i}", f"Artist {i}") for i in range(30)]

    def test_free_middle_field_changes_required_song_count(self):
        self.assertEqual(required_songs(5, True), 24)
        self.assertEqual(required_songs(4, True), 16)
        self.assertEqual(unique_card_capacity(self.songs[:24], 5, True), 1)
        self.assertEqual(unique_card_capacity(self.songs[:23], 5, True), 0)
        self.assertEqual(unique_card_capacity(self.songs[:24] * 2, 5, True), 1)

    def test_too_small_pool_is_rejected(self):
        with self.assertRaises(NotEnoughSongs):
            generate_cards(self.songs[:23], 5, True, 1)

    def test_size_and_card_count_limits(self):
        with self.assertRaisesRegex(ValueError, "Kartengröße"):
            generate_cards(self.songs, 2, False, 1)
        with self.assertRaisesRegex(ValueError, "Kartengröße"):
            required_songs(3.0, False)
        with self.assertRaisesRegex(ValueError, "Freifeld"):
            required_songs(3, "false")
        for count in (0, 501):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "Kartenanzahl"):
                generate_cards(self.songs, 3, False, count)
        with self.assertRaisesRegex(ValueError, "Kartenanzahl"):
            generate_cards(self.songs, 3, False, True)

    def test_unique_cards_and_cell_count(self):
        cards = generate_cards(self.songs, 5, True, 25)
        signatures = {tuple(sorted(song.title for song in card.songs)) for card in cards}
        self.assertEqual(len(cards), 25)
        self.assertEqual(len(signatures), 25)
        self.assertTrue(all(len(card.songs) == 24 for card in cards))

    def test_impossible_unique_card_count_is_reported(self):
        with self.assertRaisesRegex(ValueError, "höchstens"):
            generate_cards(self.songs[:9], 3, False, 2)

    def test_duplicate_inputs_do_not_inflate_available_combinations(self):
        with self.assertRaisesRegex(NotEnoughSongs, "eindeutige Songs"):
            generate_cards([Song("gleich") for _ in range(9)], 3, False, 2)


class CallerTests(unittest.TestCase):
    def setUp(self):
        self.pool = [Song("A"), Song("B"), Song("C")]
        self.caller = Caller(self.pool, self.pool, -1)

    def test_draw_undo_and_end_of_pool(self):
        self.assertEqual(self.caller.draw_next(), Song("A"))
        self.assertEqual(self.caller.undo(), Song("A"))
        self.assertIsNone(self.caller.current)
        self.assertIsNone(Caller(self.pool, self.pool, 2).draw_next())

    def test_duplicate_song_entries_are_only_called_once(self):
        caller = Caller([Song("A"), Song("a"), Song("B")])
        self.assertEqual(len(caller.pool), 2)
        self.assertEqual(len(caller.order), 2)

    def test_invalid_saved_order_and_index_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "jeden Song"):
            Caller(self.pool, [self.pool[0], self.pool[0], self.pool[2]])
        with self.assertRaisesRegex(ValueError, "Ziehindex"):
            Caller(self.pool, self.pool, True)

    def test_reshuffle_resets_progress_and_keeps_the_pool(self):
        caller = Caller(self.pool, self.pool, 1)

        caller.reshuffle()

        self.assertIsNone(caller.current)
        self.assertEqual(caller.drawn, [])
        self.assertEqual(set(caller.order), set(self.pool))


class BingoCheckTests(unittest.TestCase):
    def setUp(self):
        self.card = BingoCard([Song(f"Song {i}") for i in range(8)])

    def test_checks_rows_columns_and_free_center(self):
        drawn = [Song("Song 0"), Song("Song 1"), Song("Song 2")]
        self.assertEqual(winning_lines(self.card, 3, True, drawn), ["Reihe 1"])
        middle_row = [Song("Song 3"), Song("Song 4")]
        self.assertIn("Reihe 2", winning_lines(self.card, 3, True, middle_row))
        first_column = [Song("Song 0"), Song("Song 3"), Song("Song 5")]
        self.assertIn("Spalte A", winning_lines(self.card, 3, True, first_column))

    def test_diagonals_follow_the_active_rule(self):
        drawn = [Song("Song 0"), Song("Song 7")]
        self.assertEqual(winning_lines(self.card, 3, True, drawn), [])
        self.assertIn("Diagonale ↘", winning_lines(self.card, 3, True, drawn, True))
        self.assertEqual(winning_lines(self.card, 3, True, []), [])

    def test_rejects_card_with_wrong_size(self):
        with self.assertRaisesRegex(ValueError, "passt nicht"):
            winning_lines(self.card, 4, False, [])

    def test_game_service_checks_the_selected_card_against_drawn_songs(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i}" for i in range(9)))
        service.create_cards(3, False, 1)
        card = service.game.cards[0]
        service.game.caller = Caller(card.songs, card.songs, -1)
        service.game.caller.draw_next()
        service.game.caller.draw_next()
        self.assertEqual(service.check_bingo(1), [])
        service.game.caller.draw_next()
        self.assertIn("Reihe 1", service.check_bingo(1))
        for invalid_number in (0, 2, 1.5, True):
            with self.subTest(card_number=invalid_number), self.assertRaisesRegex(ValueError, "Kartennummer"):
                service.check_bingo(invalid_number)

    def test_game_service_rejects_check_without_cards(self):
        with self.assertRaisesRegex(ValueError, "zwischen 1 und 0"):
            GameService().check_bingo(1)


class PersistenceTests(unittest.TestCase):
    def test_missing_saved_game_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "missing.json")

            self.assertIsNone(store.load())

    def test_save_and_load_preserve_cards_settings_and_caller(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(30)))
        service.create_cards(3, True, 4)
        service.game.caller.draw_next()
        service.per_page = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spielstand.json"
            store = FileStore(path)
            store.save(service)
            restored = store.load()
            self.assertEqual(restored.to_dict(), service.to_dict())
            self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["cards"])

    def test_export_and_import_round_trip_preserves_audio(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – Artist" for i in range(9)))
        service.create_cards(3, False, 1)
        service.assign_audio_file(service.game.songs[0], "/music/song.mp3")
        service.auto_play = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.json"

            FileStore.export_to(path, service)
            imported = FileStore.import_from(path)
            self.assertEqual([item.name for item in Path(directory).iterdir()], ["export.json"])

        self.assertEqual(imported.to_dict(), service.to_dict())

    def test_import_rejects_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("{ kaputt", encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                FileStore.import_from(path)

    def test_rejects_unsupported_save_version(self):
        with self.assertRaisesRegex(ValueError, "Version"):
            GameService.from_dict({"version": 900})

    def test_rejects_non_object_and_duplicate_song_imports(self):
        with self.assertRaisesRegex(ValueError, "JSON-Objekt"):
            GameService.from_dict([])
        with self.assertRaisesRegex(ValueError, "Duplikate"):
            GameService.from_dict({"version": 1, "songs": [{"title": "Same"}, {"title": "same"}]})

    def test_rejects_wrong_types_in_imported_songs_and_flags(self):
        with self.assertRaisesRegex(ValueError, "müssen Text sein"):
            GameService.from_dict({"version": 1, "songs": [{"title": 42}]})
        with self.assertRaisesRegex(ValueError, "Freifeld"):
            GameService.from_dict({"version": 1, "free_space": "false"})
        with self.assertRaisesRegex(ValueError, "Songliste muss Text"):
            GameService.from_dict({"version": 1, "song_text": ["not text"]})

    def test_rejects_card_that_does_not_match_song_pool(self):
        with self.assertRaisesRegex(ValueError, "passt nicht"):
            GameService.from_dict({
                "version": 1,
                "size": 3,
                "free_space": True,
                "songs": [{"title": "a"}],
                "cards": [{"songs": [{"title": "unbekannt"} for _ in range(8)]}],
            })

    def test_rejects_duplicate_cards_in_import(self):
        songs = [{"title": f"Song {i}"} for i in range(9)]
        card = {"songs": songs}
        with self.assertRaisesRegex(ValueError, "passt nicht"):
            GameService.from_dict({
                "version": 1,
                "size": 3,
                "free_space": False,
                "songs": songs,
                "cards": [card, card],
            })

    def test_unsaved_song_draft_does_not_mutate_active_round(self):
        service = GameService()
        service.set_song_text("\n".join(f"Aktiver Song {i} – Artist" for i in range(9)))
        service.create_cards(3, False, 1)
        old_pool = list(service.game.songs)
        service.set_song_text("Neuer Entwurf – Andere")
        self.assertEqual(service.game.songs, old_pool)
        self.assertEqual(service.song_text, "Neuer Entwurf – Andere")

    def test_preparation_settings_do_not_corrupt_active_cards(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(30)))
        service.create_cards(5, True, 3)
        service.card_size = 3
        service.card_count = 10
        restored = GameService.from_dict(service.to_dict())
        self.assertEqual(restored.card_size, 3)
        self.assertEqual(restored.card_count, 10)
        self.assertEqual(restored.game.size, 5)
        self.assertEqual(len(restored.game.cards[0].songs), 24)

    def test_active_diagonal_rule_survives_save_and_restore(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i}" for i in range(9)))
        service.create_cards(3, True, 1, diagonal_wins=True)
        restored = GameService.from_dict(service.to_dict())
        self.assertTrue(restored.game.diagonal_wins)
        self.assertTrue(restored.diagonal_wins)

    def test_audio_assignments_and_autoplay_survive_save_and_restore(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – Artist" for i in range(9)))
        service.create_cards(3, False, 1)
        song = service.game.songs[0]
        service.assign_audio_file(song, "/music/song.mp3")
        service.auto_play = True

        restored = GameService.from_dict(service.to_dict())

        self.assertEqual(restored.audio_file_for(song), "/music/song.mp3")
        self.assertTrue(restored.auto_play)
        with self.assertRaisesRegex(ValueError, "gehört nicht"):
            service.assign_audio_file(Song("Außerhalb"), "/music/other.mp3")

    def test_import_rejects_a_broken_saved_draw_order(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i}" for i in range(9)))
        service.create_cards(3, False, 1)
        service.game.caller.draw_next()
        data = service.to_dict()
        data["caller_order"][0] = data["caller_order"][1]

        with self.assertRaisesRegex(ValueError, "Ziehreihenfolge passt nicht"):
            GameService.from_dict(data)

    def test_import_rejects_invalid_settings_without_clamping_them(self):
        service = GameService()
        data = service.to_dict()
        data["settings"]["card_count"] = 501

        with self.assertRaisesRegex(ValueError, "vorbereitete Kartenanzahl"):
            GameService.from_dict(data)

    def test_import_rejects_duplicate_audio_mapping_keys(self):
        data = GameService().to_dict()
        data["audio_files"] = {"Song": "/music/first.mp3", "song": "/music/second.mp3"}

        with self.assertRaisesRegex(ValueError, "doppelte Audiozuordnungen"):
            GameService.from_dict(data)

    def test_failed_generation_keeps_previous_round_intact(self):
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(30)))
        service.create_cards(3, False, 2)
        original_state = service.to_dict()
        service.set_song_text("Zu wenige Songs")
        with self.assertRaises(NotEnoughSongs):
            service.create_cards(5, True, 5)
        self.assertEqual(service.game.songs, [Song(f"Song {i}", f"Artist {i}") for i in range(30)])
        self.assertEqual(service.game.size, 3)
        self.assertEqual(service.game.cards, GameService.from_dict(original_state).game.cards)


if __name__ == "__main__":
    unittest.main()


class CardsContainingTests(unittest.TestCase):
    """„Ohne Kartennummer prüfen“: Karte über die Songs der Gewinnreihe finden."""

    def test_finds_exactly_the_cards_with_all_songs(self):
        from musik_bingo.domain.card_generator import cards_containing, generate_cards
        songs = [Song(f"Song {i}", "A") for i in range(40)]
        cards = generate_cards(songs, 5, True, 160)
        line = cards[41].songs[:5]  # erste Reihe von Karte #42
        found = cards_containing(cards, line)
        self.assertIn(42, found)
        for number in found:
            self.assertTrue({song.key for song in line} <= {song.key for song in cards[number - 1].songs})
        self.assertEqual(len(found), sum(1 for card in cards
                                         if {s.key for s in line} <= {s.key for s in card.songs}))
        self.assertEqual(cards_containing(cards, []), [])
        self.assertEqual(cards_containing(cards, [Song("Gibt es nicht", "X")]), [])
        # Groß-/Kleinschreibung wie bei der Song-Identität egal
        self.assertIn(42, cards_containing(cards, [Song(s.title.upper(), s.artist.lower()) for s in line]))
