"""Gewinngarantie und Spielprognose: Es muss immer einen Gewinner geben."""
import random
import unittest

from musik_bingo.application.game_service import GameService
from musik_bingo.domain.caller import Caller
from musik_bingo.domain.card_generator import generate_cards
from musik_bingo.domain.catalog import mix_key, parse_catalog
from musik_bingo.domain.forecast import (
    WIN_TARGETS, card_status, forecast, guarantee, recommend_pool_size, target_reached,
)
from musik_bingo.domain.models import BingoCard, Song
from musik_bingo.domain.song_list import parse_songs
from musik_bingo.paths import CATALOG_DIR, DEFAULT_SONGS


def pool_of(n: int) -> list[Song]:
    return [Song(f"Song {i}", f"Artist {i}") for i in range(n)]


class WinnerGuaranteeTests(unittest.TestCase):
    """Wird jeder Song der Liste gespielt, gibt es für jedes Gewinnziel einen Gewinner."""

    def test_every_card_is_full_after_all_songs(self):
        for size, free, pool_size, count in ((5, True, 75, 160), (5, False, 40, 50), (4, False, 30, 80), (3, True, 12, 40)):
            with self.subTest(size=size, free=free, pool=pool_size):
                pool = pool_of(pool_size)
                cards = generate_cards(pool, size, free, count, random.Random(size))
                caller = Caller(pool)
                while caller.draw_next():
                    pass
                for card in cards:
                    lines, full = card_status(card, size, free, caller.drawn)
                    self.assertTrue(full)
                    for target in WIN_TARGETS:
                        self.assertTrue(target_reached(target, lines, full))
                self.assertTrue(guarantee(cards, pool, size, free).ok)

    def test_many_random_games_always_produce_a_winner(self):
        pool = pool_of(75)
        cards = generate_cards(pool, 5, True, 140, random.Random(7))
        for seed in range(40):
            order = random.Random(seed).sample(pool, len(pool))
            caller = Caller(pool, order, -1)
            found = {target: None for target in WIN_TARGETS}
            while None in found.values() and caller.draw_next():
                for card in cards:
                    lines, full = card_status(card, 5, True, caller.drawn)
                    for target in WIN_TARGETS:
                        if found[target] is None and target_reached(target, lines, full):
                            found[target] = len(caller.drawn)
            with self.subTest(seed=seed):
                self.assertNotIn(None, found.values())
                self.assertLess(found["reihe"], found["zwei_reihen"])
                self.assertLessEqual(found["zwei_reihen"], found["volle_karte"])
                self.assertLessEqual(found["volle_karte"], 75)

    def test_playlist_mismatch_breaks_guarantee(self):
        pool = pool_of(30)
        cards = generate_cards(pool, 5, True, 10, random.Random(1))
        playlist = pool[:-1]  # ein Kartensong fehlt in der gespielten Playlist
        result = guarantee(cards, playlist, 5, True)
        self.assertFalse(result.ok)
        self.assertIn("nicht in der Playlist", result.problems[0])
        self.assertFalse(guarantee([], pool, 5, True).ok)
        broken = [BingoCard(pool[:5])]
        self.assertIn("statt 24", guarantee(broken, pool, 5, True).problems[0])


class ForecastTests(unittest.TestCase):
    def test_fast_forecast_equals_song_by_song_replay(self):
        pool = pool_of(40)
        cards = generate_cards(pool, 5, True, 60, random.Random(3))
        for seed in range(15):
            fast = forecast(cards, pool, 5, True, runs=1, rng=random.Random(seed))
            keys = [song.key for song in pool]
            random.Random(seed).shuffle(keys)
            by_key = {song.key: song for song in pool}
            drawn: list[Song] = []
            first = {}
            for key in keys:
                drawn.append(by_key[key])
                results = [card_status(card, 5, True, drawn) for card in cards]
                for target in WIN_TARGETS:
                    if target not in first and any(target_reached(target, lines, full) for lines, full in results):
                        first[target] = len(drawn)
                        first[target + "_winners"] = sum(target_reached(target, l, f) for l, f in results)
            with self.subTest(seed=seed):
                for target in WIN_TARGETS:
                    self.assertEqual(fast.stages[target].median, first[target])
                    self.assertEqual(fast.stages[target].winners, first[target + "_winners"])

    def test_forecast_for_140_guests(self):
        pool = pool_of(75)
        cards = generate_cards(pool, 5, True, 160, random.Random(5))
        result = forecast(cards, pool, 5, True, runs=300, rng=random.Random(9))
        stages = result.stages
        self.assertTrue(12 <= stages["reihe"].median <= 22, stages["reihe"])
        self.assertTrue(25 <= stages["zwei_reihen"].median <= 36, stages["zwei_reihen"])
        self.assertTrue(58 <= stages["volle_karte"].median <= 68, stages["volle_karte"])
        for stage in stages.values():
            self.assertLessEqual(stage.worst, 75)
            self.assertLessEqual(stage.early, stage.median)
            self.assertLessEqual(stage.median, stage.late)
            self.assertLess(stage.winners, 2.5)  # selten viele Gewinner gleichzeitig

    def test_diagonals_make_first_win_earlier(self):
        pool = pool_of(60)
        cards = generate_cards(pool, 5, True, 100, random.Random(2))
        plain = forecast(cards, pool, 5, True, False, 200, random.Random(1)).stages["reihe"].median
        diag = forecast(cards, pool, 5, True, True, 200, random.Random(1)).stages["reihe"].median
        self.assertLessEqual(diag, plain)

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            forecast([], pool_of(5), 5, True)
        with self.assertRaises(ValueError):
            forecast([BingoCard(pool_of(24))], pool_of(24), 5, True, runs=0)
        with self.assertRaises(ValueError):
            target_reached("alles", 5, True)
        with self.assertRaises(ValueError):
            recommend_pool_size(0)
        self.assertEqual(recommend_pool_size(60), 71)
        self.assertEqual(recommend_pool_size(5), 24)


class WinTargetServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = GameService()
        self.service.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(30)))
        self.service.create_cards(5, True, 20)

    def test_check_win_follows_target(self):
        card = self.service.game.cards[0]
        for song in card.songs[:5]:  # Reihe 1 komplett
            self.service.draw_song(song)
        self.assertTrue(self.service.check_win(1)[0])
        self.service.set_win_target("zwei_reihen")
        self.assertFalse(self.service.check_win(1)[0])
        self.service.set_win_target("volle_karte")
        reached, lines, full = self.service.check_win(1)
        self.assertEqual((reached, full), (False, False))
        for song in card.songs:
            self.service.draw_song(song)
        self.assertEqual(self.service.check_win(1)[0::2], (True, True))
        with self.assertRaises(ValueError):
            self.service.set_win_target("jackpot")

    def test_win_target_is_saved_and_validated(self):
        self.service.set_win_target("volle_karte")
        data = self.service.to_dict()
        self.assertEqual(GameService.from_dict(data).win_target, "volle_karte")
        del data["settings"]["win_target"]
        self.assertEqual(GameService.from_dict(data).win_target, "reihe")
        data["settings"]["win_target"] = "../x"
        with self.assertRaises(ValueError):
            GameService.from_dict(data)

    def test_service_forecast_and_guarantee(self):
        self.assertTrue(self.service.guarantee().ok)
        self.assertEqual(self.service.forecast(runs=20).pool_size, 30)


class DefaultSongListTests(unittest.TestCase):
    def test_default_list_mixes_charts_and_christmas(self):
        songs = parse_songs(DEFAULT_SONGS.read_text(encoding="utf-8"))
        self.assertEqual(len(songs), 75)
        catalogs = [parse_catalog(p.stem, p.read_text(encoding="utf-8")) for p in CATALOG_DIR.glob("*.txt")]
        xmas_keys = {mix_key(s) for c in catalogs if c.category == "weihnachten" for s in c.songs}
        chart_keys = {mix_key(s) for c in catalogs if c.category == "charts" for s in c.songs}
        flags = [mix_key(s) in xmas_keys for s in songs]
        self.assertEqual(sum(flags), 30)
        self.assertTrue(all(mix_key(s) in xmas_keys | chart_keys for s in songs))
        # gut gemischt: in jedem Viertel der Liste beide Kategorien
        for start in range(0, 75, 19):
            chunk = flags[start:start + 19]
            self.assertTrue(any(chunk) and not all(chunk), start)


if __name__ == "__main__":
    unittest.main()
