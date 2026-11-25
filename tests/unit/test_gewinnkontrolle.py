"""Gewinnkontrolle: Die App zeigt der Spielleitung nach jedem Song, welche Karten das Ziel erreicht haben."""
import random
import unittest

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.caller import Caller
from musik_bingo.domain.card_generator import generate_cards
from musik_bingo.domain.forecast import WIN_TARGETS, card_status, missing_to_target, reached_at, target_reached
from musik_bingo.domain.models import BingoCard, Song


def pool_of(n: int) -> list[Song]:
    return [Song(f"Song {i}", f"Artist {i}") for i in range(n)]


class MissingToTargetTests(unittest.TestCase):
    def setUp(self):
        # 3×3 mit Freifeld: Felder 0 1 2 / 3 F 5 / 6 7 8 → Songs 0…7
        self.songs = pool_of(8)
        self.card = BingoCard(self.songs)

    def missing(self, drawn_indices, target, diagonals=False):
        drawn = [self.songs[i] for i in drawn_indices]
        return missing_to_target(self.card, 3, True, drawn, target, diagonals)

    def test_nothing_drawn(self):
        # Mittlere Reihe/Spalte haben das Freifeld → nur 2 offene Felder
        self.assertEqual(self.missing([], "reihe"), 2)
        # Mittlere Reihe + mittlere Spalte teilen sich das Freifeld → 4 offene Felder
        self.assertEqual(self.missing([], "zwei_reihen"), 4)
        self.assertEqual(self.missing([], "volle_karte"), 8)

    def test_line_and_full_card(self):
        self.assertEqual(self.missing([0, 1], "reihe"), 1)      # obere Reihe: Song 2 fehlt
        self.assertEqual(self.missing([0, 1, 2], "reihe"), 0)
        self.assertEqual(self.missing(range(7), "volle_karte"), 1)
        self.assertEqual(self.missing(range(8), "volle_karte"), 0)

    def test_two_lines_share_crossing_cell(self):
        # Obere Reihe (0,1,2) + linke Spalte (0,3,5) teilen Feld 0 → 5 Songs reichen
        self.assertEqual(self.missing([0, 1, 2, 3], "zwei_reihen"), 1)
        self.assertEqual(self.missing([0, 1, 2, 3, 5], "zwei_reihen"), 0)

    def test_diagonals_only_when_enabled(self):
        # Diagonale ↘: Felder 0, F, 8 → Songs 0 und 7
        self.assertEqual(self.missing([0, 7], "reihe"), 2)  # ohne Diagonalen: jede Linie hat noch 2 offene Felder
        self.assertEqual(self.missing([0, 7], "reihe", diagonals=True), 0)

    def test_unknown_target(self):
        with self.assertRaises(ValueError):
            self.missing([], "jackpot")

    def test_matches_card_status_in_random_games(self):
        """0 fehlende Songs heißt genau: Gewinnziel erreicht – wie bei „Bingo prüfen“."""
        for size, free in ((3, True), (4, False), (5, True)):
            pool = pool_of(40)
            cards = generate_cards(pool, size, free, 30, random.Random(size))
            for seed in range(5):
                caller = Caller(pool, random.Random(seed).sample(pool, len(pool)), -1)
                while caller.draw_next():
                    for card in cards:
                        lines, full = card_status(card, size, free, caller.drawn, True)
                        for target in WIN_TARGETS:
                            with self.subTest(size=size, seed=seed, target=target):
                                missing = missing_to_target(card, size, free, caller.drawn, target, True)
                                self.assertEqual(missing == 0, target_reached(target, lines, full))


class ReachedAtTests(unittest.TestCase):
    def test_song_number_when_target_was_reached(self):
        """reached_at = erster Song, nach dem target_reached gilt – Song für Song nachgeprüft."""
        for size, free in ((3, True), (4, False), (5, True)):
            pool = pool_of(40)
            cards = generate_cards(pool, size, free, 20, random.Random(size + 10))
            caller = Caller(pool, random.Random(3).sample(pool, len(pool)), -1)
            first_seen = {}
            while caller.draw_next():
                for number, card in enumerate(cards):
                    lines, full = card_status(card, size, free, caller.drawn, True)
                    for target in WIN_TARGETS:
                        if target_reached(target, lines, full):
                            first_seen.setdefault((number, target), len(caller.drawn))
            for number, card in enumerate(cards):
                for target in WIN_TARGETS:
                    with self.subTest(size=size, card=number, target=target):
                        self.assertEqual(reached_at(card, size, free, caller.drawn, target, True),
                                         first_seen[(number, target)])

    def test_not_reached_and_unknown_target(self):
        card = BingoCard(pool_of(8))
        self.assertIsNone(reached_at(card, 3, True, [], "volle_karte"))
        self.assertIsNone(reached_at(card, 3, True, pool_of(8)[:3], "zwei_reihen"))
        with self.assertRaises(ValueError):
            reached_at(card, 3, True, [], "jackpot")


class TargetStatusServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = GameService()
        self.service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(50)))
        self.service.create_cards(3, True, 160)
        self.service.set_win_target("volle_karte")

    def cards(self):
        return self.service.game.cards

    def exact_one_missing(self) -> int:
        game, entered = self.service.game, set(self.service.target_status().entered)
        return sum(1 for number, card in enumerate(game.cards, start=1) if number not in entered
                   and missing_to_target(card, 3, True, game.caller.drawn, self.service.win_target) == 1)

    def test_empty_before_first_song(self):
        status = self.service.target_status()
        self.assertEqual((status.reached, status.entered, status.entered_open, status.earlier, status.one_missing),
                         ((), (), (), (), 0))
        self.assertEqual(status.tied, ())

    def test_reports_full_cards_and_near_misses(self):
        card = self.cards()[0]
        for song in card.songs[:-1]:
            self.service.draw_song(song)
        status = self.service.target_status()
        self.assertNotIn(1, [number for number, _song in status.reached])
        self.assertEqual(status.one_missing, self.exact_one_missing())
        self.assertGreaterEqual(status.one_missing, 1)
        self.service.draw_song(card.songs[-1])
        status = self.service.target_status()
        self.assertIn((1, len(self.service.game.caller.drawn)), status.reached)
        # Dieselben Karten wie eine Einzelprüfung aller Karten
        expected = {n for n in range(1, 161) if self.service.check_win(n)[0]}
        self.assertEqual({number for number, _song in status.reached}, expected)

    def test_earliest_first_and_tie_only_on_same_song(self):
        first, second = self.cards()[0], self.cards()[1]
        for song in first.songs:
            self.service.draw_song(song)
        when_first = len(self.service.game.caller.drawn)
        for song in second.songs:
            self.service.draw_song(song)
        status = self.service.target_status()
        self.assertEqual(status.reached[0], (1, when_first))  # übersehener früherer Gewinn steht vorn
        songs = [song for _number, song in status.reached]
        self.assertEqual(songs, sorted(songs))
        self.assertEqual(status.tied, ())  # #1 war früher fertig – kein Gleichstand
        # Echter Gleichstand: zwei Karten, die mit demselben Song voll werden
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(9)))
        service.create_cards(3, True, 9)  # 9 Songs, 8 je Karte → jede Karte lässt genau einen Song aus
        service.set_win_target("volle_karte")
        missing = {service.game.songs[i].key for i in range(9)} - {s.key for s in service.game.cards[0].songs}
        for song in service.game.songs:
            if song.key not in missing:
                service.draw_song(song)
        self.assertEqual(service.target_status().reached, ((1, 8),))
        last = next(song for song in service.game.songs if song.key in missing)
        service.draw_song(last)
        status = service.target_status()
        self.assertEqual(status.reached[0], (1, 8))
        self.assertEqual(status.tied, ())
        self.assertEqual(len(status.reached), 9)
        self.assertEqual(set(status.reached[1:]), {(n, 9) for n in range(2, 10)})
        service.add_winner(1, "Anna")  # #1 eingetragen → die übrigen 8 kamen gleichzeitig ans Ziel
        self.assertEqual(service.target_status().tied, tuple(range(2, 10)))

    def test_entered_winner_is_listed_separately(self):
        card = self.cards()[0]
        for song in card.songs:
            self.service.draw_song(song)
        self.service.add_winner(1, "Anna")
        status = self.service.target_status()
        self.assertNotIn(1, [number for number, _song in status.reached])
        self.assertEqual((status.entered, status.entered_open), ((1,), ()))
        self.assertEqual(status.one_missing, self.exact_one_missing())
        # „Zurück“: eingetragen, aber nicht mehr am Ziel – zählt nicht als „fehlt nur noch ein Song“
        self.service.game.caller.undo()
        status = self.service.target_status()
        self.assertEqual((status.entered, status.entered_open), ((1,), (1,)))
        self.assertEqual(status.one_missing, self.exact_one_missing())
        # Nächste Stufe/Runde: Eintrag zählt dort nicht mehr, die Karte ist als früherer Gewinner markiert
        self.service.advance_stage()
        self.assertEqual(self.service.target_status().entered, ())
        for song in card.songs:
            self.service.draw_song(song)
        status = self.service.target_status()
        self.assertIn(1, [number for number, _song in status.reached])
        self.assertIn(1, status.earlier)

    def test_follows_current_target(self):
        card = self.cards()[0]
        for song in card.songs[:3]:  # obere Reihe
            self.service.draw_song(song)
        self.assertNotIn(1, [n for n, _s in self.service.target_status().reached])
        self.service.set_win_target("reihe")
        self.assertIn((1, 3), self.service.target_status().reached)

    def test_survives_save_and_load(self):
        card = self.cards()[0]
        for song in card.songs:
            self.service.draw_song(song)
        self.service.add_winner(1, "Anna")
        before = self.service.target_status()
        restored = GameService.from_dict(self.service.to_dict())
        self.assertEqual(restored.target_status(), before)


if __name__ == "__main__":
    unittest.main()
