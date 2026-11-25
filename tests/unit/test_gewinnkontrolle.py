"""Gewinnkontrolle: Die App zeigt der Spielleitung nach jedem Song, welche Karten das Ziel erreicht haben."""
import random
import unittest

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.caller import Caller
from musik_bingo.domain.card_generator import generate_cards
from musik_bingo.domain.forecast import WIN_TARGETS, card_status, missing_to_target, target_reached
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


class TargetStatusServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = GameService()
        self.service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(50)))
        self.service.create_cards(3, True, 160)
        self.service.set_win_target("volle_karte")

    def test_empty_before_first_song(self):
        status = self.service.target_status()
        self.assertEqual((status.reached, status.entered, status.one_missing), ((), (), 0))

    def test_reports_full_cards_and_near_misses(self):
        card = self.service.game.cards[0]
        for song in card.songs[:-1]:
            self.service.draw_song(song)
        status = self.service.target_status()
        self.assertNotIn(1, status.reached)
        self.assertGreaterEqual(status.one_missing, 1)
        self.service.draw_song(card.songs[-1])
        status = self.service.target_status()
        self.assertIn(1, status.reached)
        # Dieselbe Liste wie eine Einzelprüfung aller Karten
        expected = tuple(n for n in range(1, 161) if self.service.check_win(n)[0])
        self.assertEqual(status.reached, expected)

    def test_entered_winner_is_listed_separately(self):
        card = self.service.game.cards[0]
        for song in card.songs:
            self.service.draw_song(song)
        self.service.add_winner(1, "Anna")
        status = self.service.target_status()
        self.assertNotIn(1, status.reached)
        self.assertEqual(status.entered, (1,))
        # Nächste Stufe/Runde: Eintrag zählt dort nicht mehr
        self.service.advance_stage()
        self.assertEqual(self.service.target_status().entered, ())

    def test_follows_current_target(self):
        card = self.service.game.cards[0]
        for song in card.songs[:3]:  # obere Reihe
            self.service.draw_song(song)
        self.assertNotIn(1, self.service.target_status().reached)
        self.service.set_win_target("reihe")
        self.assertIn(1, self.service.target_status().reached)


if __name__ == "__main__":
    unittest.main()
