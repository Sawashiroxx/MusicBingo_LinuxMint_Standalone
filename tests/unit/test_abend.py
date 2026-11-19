"""Ablauf des Abends: Stufen/Runden, Gewinnerliste, Feiertitel, Song-Timer, Beamer-Inhalt."""
import copy
import csv
import io
import unittest

from musik_bingo.application.beamer_state import HIDDEN, build_beamer_state
from musik_bingo.application.game_service import GameService
from musik_bingo.application.song_timer import SongTimer
from musik_bingo.domain.evening import (
    DuplicateWinner, Winner, check_new_winner, clean_event_title, next_stage, next_stage_label, winners_csv,
)


def service(cards: int = 10) -> GameService:
    result = GameService()
    result.set_song_text("\n".join(f"Song {i} – Artist {i}" for i in range(30)))
    result.create_cards(5, True, cards)
    return result


def complete_row(svc: GameService, card_number: int, rows: int = 1) -> None:
    card = svc.game.cards[card_number - 1]
    # Reihe 1 = Felder 0–4, Reihe 2 = Felder 5–9 (keine Freifeld-Verschiebung vor Feld 12)
    for song in card.songs[: 5 * rows]:
        svc.draw_song(song)


class StageTests(unittest.TestCase):
    def test_stage_order_and_labels(self):
        self.assertEqual(next_stage("reihe"), ("zwei_reihen", False))
        self.assertEqual(next_stage("zwei_reihen"), ("volle_karte", False))
        self.assertEqual(next_stage("volle_karte"), ("reihe", True))
        self.assertEqual(next_stage_label("reihe"), "Weiter: 2 Reihen")
        self.assertEqual(next_stage_label("volle_karte"), "Neue Runde (neu mischen)")
        with self.assertRaises(ValueError):
            next_stage("jackpot")

    def test_draw_continues_within_round_and_reshuffles_for_new_round(self):
        svc = service()
        for _ in range(7):
            svc.game.caller.draw_next()
        self.assertEqual(svc.advance_stage(), ("zwei_reihen", False))
        self.assertEqual(len(svc.game.caller.drawn), 7)  # Ziehung läuft weiter
        svc.advance_stage()
        self.assertEqual(svc.advance_stage(), ("reihe", True))
        self.assertEqual((svc.round_number, len(svc.game.caller.drawn)), (2, 0))
        self.assertEqual(len(svc.game.cards), 10)  # gedruckte Karten bleiben gültig

    def test_restart_round_allows_same_card_to_win_again(self):
        """Regression: „Neu mischen“ ohne neue Runde blockierte echte Gewinner."""
        svc = service()
        complete_row(svc, 1)
        svc.add_winner(1, "A")
        svc.restart_round()
        self.assertEqual((svc.round_number, svc.win_target, svc.game.caller.drawn), (2, "reihe", []))
        complete_row(svc, 1)
        self.assertEqual(svc.add_winner(1, "A", allow_repeat=True).round, 2)
        with self.assertRaises(ValueError):
            GameService().restart_round()

    def test_advance_without_round_fails(self):
        with self.assertRaises(ValueError):
            GameService().advance_stage()


class WinnerTests(unittest.TestCase):
    def test_only_real_winners_can_be_entered(self):
        svc = service()
        with self.assertRaisesRegex(ValueError, "noch nicht erreicht"):
            svc.add_winner(1, "Oma Erna")
        complete_row(svc, 1)
        winner = svc.add_winner(1, "  Oma\tErna\x00 ")
        self.assertEqual((winner.round, winner.target, winner.card, winner.name, winner.song_count),
                         (1, "reihe", 1, "Oma Erna", 5))
        with self.assertRaises(ValueError):
            svc.add_winner(999)

    def test_same_card_cannot_win_twice(self):
        svc = service()
        complete_row(svc, 1, rows=2)
        svc.add_winner(1, "A")
        with self.assertRaises(DuplicateWinner):
            svc.add_winner(1, "A")  # gleiche Stufe: nie
        svc.advance_stage()
        with self.assertRaisesRegex(DuplicateWinner, "bereits gewonnen: Runde 1, 1 Reihe"):
            svc.add_winner(1, "A")  # andere Stufe: nur mit Freigabe
        self.assertEqual(svc.add_winner(1, "A", allow_repeat=True).target, "zwei_reihen")
        self.assertEqual(len(svc.winners), 2)
        self.assertEqual(svc.remove_winner(1).target, "zwei_reihen")
        with self.assertRaises(ValueError):
            svc.remove_winner(5)

    def test_check_new_winner_limit(self):
        winners = [Winner(1, "reihe", i, "", 3) for i in range(1, 1001)]
        with self.assertRaisesRegex(ValueError, "voll"):
            check_new_winner(winners, Winner(1, "reihe", 5000, "", 3))

    def test_csv_export_blocks_formulas(self):
        text = winners_csv([Winner(2, "volle_karte", 12, "=HYPERLINK(\"x\")", 63)], "+Feier")
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0], ["Feier", "Runde", "Gewinnziel", "Karte", "Name", "nach Songs"])
        self.assertEqual(rows[1], ["'+Feier", "2", "Volle Karte", "12", "'=HYPERLINK(\"x\")", "63"])

    def test_new_cards_reset_the_evening(self):
        svc = service()
        complete_row(svc, 1)
        svc.add_winner(1)
        svc.advance_stage()
        svc.create_cards(5, True, 10)
        self.assertEqual((svc.round_number, svc.win_target, svc.winners), (1, "reihe", []))


class TitleTests(unittest.TestCase):
    def test_title_is_cleaned_and_limited(self):
        self.assertEqual(clean_event_title("  Weihnachtsfeier\n2026  "), "Weihnachtsfeier 2026")
        self.assertEqual(clean_event_title(""), "Musik Bingo")
        self.assertEqual(clean_event_title("‮evil​"), "evil")
        self.assertEqual(len(clean_event_title("x" * 500)), 60)
        svc = GameService()
        self.assertEqual(svc.set_event_title("<b>Feier</b> & Co"), "<b>Feier</b> & Co")  # Escaping macht die Anzeige


class PersistenceTests(unittest.TestCase):
    def test_round_trip_and_old_saves(self):
        svc = service()
        complete_row(svc, 2)
        svc.add_winner(2, "Paul")
        svc.set_event_title("Weihnachtsfeier 2026")
        svc.set_timer(45, 5)
        svc.advance_stage()
        data = svc.to_dict()
        restored = GameService.from_dict(data)
        self.assertEqual((restored.event_title, restored.round_number, restored.win_target), ("Weihnachtsfeier 2026", 1, "zwei_reihen"))
        self.assertEqual((restored.timer_seconds, restored.reveal_seconds), (45, 5))
        self.assertEqual(restored.winners, svc.winners)
        for key in ("event_title", "round_number", "timer_seconds", "reveal_seconds"):
            del data["settings"][key]
        del data["winners"]
        old = GameService.from_dict(data)
        self.assertEqual((old.event_title, old.round_number, old.timer_seconds, old.winners), ("Musik Bingo", 1, 0, []))

    def test_duplicate_winners_in_file_are_rejected(self):
        svc = service()
        complete_row(svc, 1)
        svc.add_winner(1)
        data = svc.to_dict()
        data["winners"] = data["winners"] * 2
        with self.assertRaisesRegex(ValueError, "Gewinnerliste"):
            GameService.from_dict(data)

    def test_manipulated_values_are_rejected(self):
        base = service().to_dict()
        bad = [
            ("settings", "round_number", 0), ("settings", "round_number", True), ("settings", "timer_seconds", 9999),
            ("settings", "reveal_seconds", -1), ("settings", "event_title", 5),
            ("winners", None, [{"round": 1, "target": "reihe", "card": 99, "name": "", "song_count": 1}]),
            ("winners", None, [{"round": 1, "target": "jackpot", "card": 1, "name": "", "song_count": 1}]),
            ("winners", None, [{"round": "1", "target": "reihe", "card": 1, "name": "", "song_count": 1}]),
            ("winners", None, "keine Liste"),
        ]
        for section, key, value in bad:
            data = copy.deepcopy(base)
            if key is None:
                data[section] = value
            else:
                data[section][key] = value
            with self.subTest(section=section, key=key, value=value), self.assertRaises(ValueError):
                GameService.from_dict(data)


class SongTimerTests(unittest.TestCase):
    def test_countdown_reveal_and_next(self):
        timer = SongTimer(3, 2)
        timer.start()
        self.assertEqual([timer.tick(), timer.tick()], [None, None])
        self.assertEqual(timer.label(), "noch 1 s")
        self.assertEqual(timer.tick(), "reveal")
        self.assertIn("Auflösung", timer.label())
        self.assertEqual([timer.tick(), timer.tick()], [None, "next"])
        self.assertIsNone(timer.tick())  # danach ruhig, bis wieder start()

    def test_pause_without_reveal_and_disabled(self):
        timer = SongTimer(2, 0)
        timer.start()
        timer.pause()
        self.assertEqual([timer.tick(), timer.tick()], [None, None])
        self.assertTrue(timer.label().startswith("Pausiert"))
        timer.resume()
        self.assertEqual([timer.tick(), timer.tick()], [None, "next"])
        off = SongTimer(0, 5)
        off.start()
        self.assertEqual((off.tick(), off.label()), (None, "Timer aus"))

    def test_limits(self):
        for seconds, reveal in ((-1, 0), (601, 0), (10, 31), (True, 0), (1.5, 0)):
            with self.subTest(seconds=seconds, reveal=reveal), self.assertRaises(ValueError):
                SongTimer(seconds, reveal)
        timer = SongTimer(10, 0)
        timer.start()
        timer.configure(0, 0)
        self.assertEqual(timer.phase, "aus")


class BeamerStateTests(unittest.TestCase):
    def test_title_hidden_until_revealed(self):
        svc = service()
        svc.set_event_title("Weihnachtsfeier 2026")
        state = build_beamer_state(svc, revealed=False)
        self.assertEqual((state.song_line, state.title, state.recent), ("Gleich geht's los", "", ()))
        first = svc.game.caller.draw_next()
        second = svc.game.caller.draw_next()
        hidden = build_beamer_state(svc, revealed=False, timer_text="noch 30 s")
        self.assertEqual((hidden.song_line, hidden.title, hidden.artist), ("Song 2", HIDDEN, ""))
        self.assertEqual(hidden.recent, (first.display_name,))  # aktueller Song nicht verraten
        self.assertNotIn(second.display_name, hidden.recent)  # exakter Vergleich, kein Teiltext („Song 1“ ⊂ „Song 17“)
        self.assertNotEqual(hidden.title, second.title)
        shown = build_beamer_state(svc, revealed=True, banner="BINGO!")
        self.assertEqual((shown.title, shown.recent, shown.banner), (second.title, (first.display_name,), "BINGO!"))
        self.assertEqual(shown.round_line, "Runde 1 · Ziel: 1 Reihe")
        self.assertEqual(shown.event_title, "Weihnachtsfeier 2026")

    def test_recent_list_is_limited(self):
        svc = service()
        for _ in range(12):
            svc.game.caller.draw_next()
        self.assertEqual(len(build_beamer_state(svc, revealed=True).recent), 5)
        self.assertEqual(build_beamer_state(GameService(), revealed=False).song_line, "Noch keine Runde")


if __name__ == "__main__":
    unittest.main()
