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


class RoundStartTargetTests(unittest.TestCase):
    """Abend nur mit „Volle Karte“: Jede neue Runde begann wieder mit „1 Reihe“ – auch auf dem Beamer."""

    def test_new_round_starts_with_target_chosen_before_first_song(self):
        svc = service()
        svc.set_win_target("volle_karte")  # vor dem ersten Song gewählt = Startziel
        for _ in range(12):
            svc.game.caller.draw_next()
        self.assertEqual(svc.advance_stage(), ("volle_karte", True))
        self.assertEqual((svc.round_number, svc.win_target, svc.game.caller.drawn), (2, "volle_karte", []))
        svc.game.caller.draw_next()
        self.assertEqual(svc.advance_stage(), ("volle_karte", True))  # auch Runde 3, ohne neu einzustellen
        self.assertEqual((svc.round_number, svc.win_target), (3, "volle_karte"))

    def test_target_change_during_round_does_not_move_the_start(self):
        svc = service()
        svc.game.caller.draw_next()
        svc.set_win_target("volle_karte")  # mitten in der Runde: Stufe übersprungen, Startziel bleibt „1 Reihe“
        self.assertEqual(svc.round_start_target, "reihe")
        self.assertEqual(svc.advance_stage(), ("reihe", True))

    def test_stage_button_keeps_classic_order(self):
        svc = service()
        self.assertEqual([svc.advance_stage(), svc.advance_stage(), svc.advance_stage()],
                         [("zwei_reihen", False), ("volle_karte", False), ("reihe", True)])
        self.assertEqual(svc.round_start_target, "reihe")

    def test_reshuffle_round_and_new_cards(self):
        svc = service()
        svc.set_win_target("zwei_reihen")
        svc.game.caller.draw_next()
        svc.restart_round()  # „Neu mischen“ mitten im Spiel
        self.assertEqual((svc.round_number, svc.win_target), (2, "zwei_reihen"))
        svc.create_cards(5, True, 10)  # neue Karten = neuer Abend
        self.assertEqual((svc.win_target, svc.round_start_target), ("reihe", "reihe"))

    def test_start_target_is_saved_and_validated(self):
        svc = service()
        svc.set_win_target("volle_karte")
        svc.game.caller.draw_next()
        data = svc.to_dict()
        restored = GameService.from_dict(copy.deepcopy(data))
        self.assertEqual(restored.advance_stage(), ("volle_karte", True))
        del data["settings"]["round_start_target"]  # Stand aus 2.5.1: wie bisher „1 Reihe“
        self.assertEqual(GameService.from_dict(copy.deepcopy(data)).round_start_target, "reihe")
        data["settings"]["round_start_target"] = "jackpot"
        with self.assertRaisesRegex(ValueError, "Start-Gewinnziel"):
            GameService.from_dict(data)


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

    def test_third_check_reports_same_stage_first(self):
        """Regression (Fable 2.4): nach 1 Reihe + 2 Reihen meldete die 3. Prüfung erst „1 Reihe“,
        die Rückfrage „trotzdem?“ endete dann in einer unbehandelten Ausnahme."""
        winners = [Winner(1, "reihe", 7, "A", 16), Winner(1, "zwei_reihen", 7, "A", 30)]
        with self.assertRaises(DuplicateWinner) as caught:
            check_new_winner(winners, Winner(1, "zwei_reihen", 7, "", 31))
        self.assertEqual(caught.exception.previous.target, "zwei_reihen")
        with self.assertRaises(DuplicateWinner):
            check_new_winner(winners, Winner(1, "zwei_reihen", 7, "", 31), allow_repeat=True)
        # andere Stufe: ohne Freigabe Rückfrage (jüngster Eintrag), mit Freigabe erlaubt
        with self.assertRaises(DuplicateWinner) as caught:
            check_new_winner(winners, Winner(1, "volle_karte", 7, "", 63))
        self.assertEqual(caught.exception.previous.target, "zwei_reihen")
        check_new_winner(winners, Winner(1, "volle_karte", 7, "", 63), allow_repeat=True)

    def test_song_limit_matches_load_limit(self):
        """Regression (Fable 2.4): 2001 Songs ließen sich erzeugen und speichern, aber nicht laden."""
        from musik_bingo.application.game_service import MAX_GAME_SONGS
        service = GameService()
        service.set_song_text("\n".join(f"Song {i} – A" for i in range(MAX_GAME_SONGS + 1)))
        with self.assertRaisesRegex(ValueError, "Höchstens 2000 Songs"):
            service.create_cards(5, True, 10)
        service.set_song_text("\n".join(f"Song {i} – A" for i in range(MAX_GAME_SONGS)))
        service.create_cards(5, True, 10)
        for song in service.game.songs:
            service.assign_audio_file(song, f"/musik/{song.title}.mp3")
        restored = GameService.from_dict(copy.deepcopy(service.to_dict()))
        self.assertEqual(len(restored.game.songs), MAX_GAME_SONGS)
        # Zuordnungen bleiben über neue Runden erhalten …
        service.set_song_text("\n".join(f"Neu {i} – B" for i in range(30)) + "\nSong 1 – A")
        service.create_cards(5, True, 10)
        self.assertEqual(len(service.audio_files), MAX_GAME_SONGS)
        # … nur beim Überlauf fallen die nicht mehr benötigten weg (auch über „Ordner zuordnen“ ohne Karten)
        dropped = service.merge_audio_files({f"neu {i} – b": f"/musik/neu{i}.mp3" for i in range(30)})
        self.assertEqual(dropped, MAX_GAME_SONGS + 30 - 31)
        self.assertEqual(set(service.audio_files), {f"neu {i} – b" for i in range(30)} | {"song 1 – a"})
        GameService.from_dict(service.to_dict())
        fresh = GameService()
        fresh.set_song_text("\n".join(f"T {i} – X" for i in range(MAX_GAME_SONGS + 1)))
        fresh.merge_audio_files({f"t {i} – x": f"/m/{i}.mp3" for i in range(MAX_GAME_SONGS + 1)})
        GameService.from_dict(fresh.to_dict())  # vorher: „Ungültige Audiozuordnungen im Spielstand.“

    def test_new_song_ends_manual_timer_pause(self):
        """Nach einem neuen Song stand sonst „Pausiert · noch 30 s“ und nichts lief weiter."""
        timer = SongTimer(30, 5)
        timer.start()
        timer.pause()
        self.assertIsNone(timer.tick())
        timer.start()
        self.assertFalse(timer.paused)
        self.assertEqual(timer.label(), "noch 30 s")
        timer.tick()
        self.assertEqual(timer.remaining, 29)

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
        svc.beamer_reveal = False
        svc.beamer_recent_count, svc.beamer_recent_size = 1, "gross"
        restored = GameService.from_dict(svc.to_dict())
        self.assertEqual((restored.beamer_reveal, restored.beamer_recent_count, restored.beamer_recent_size),
                         (False, 1, "gross"))
        data = svc.to_dict()
        for key in ("event_title", "round_number", "timer_seconds", "reveal_seconds", "beamer_reveal",
                    "beamer_recent_count", "beamer_recent_size"):
            del data["settings"][key]
        del data["winners"]
        old = GameService.from_dict(data)
        self.assertEqual((old.event_title, old.round_number, old.timer_seconds, old.winners), ("Musik Bingo", 1, 0, []))
        self.assertTrue(old.beamer_reveal)  # alte Spielstände: Aufdecken wie bisher an
        self.assertEqual((old.beamer_recent_count, old.beamer_recent_size), (3, "normal"))

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
            ("settings", "beamer_reveal", "nein"), ("settings", "beamer_reveal", 0),
            ("settings", "beamer_recent_count", 6), ("settings", "beamer_recent_count", -1),
            ("settings", "beamer_recent_count", True), ("settings", "beamer_recent_count", "3"),
            ("settings", "beamer_recent_size", "riesig"), ("settings", "beamer_recent_size", 2),
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

    def test_reveal_can_be_switched_off(self):
        """„Titel auf dem Beamer aufdecken“ aus: kein Titel – weder aufgedeckt noch unter „Zuletzt“."""
        svc = service()
        svc.beamer_reveal = False
        first = svc.game.caller.draw_next()
        svc.game.caller.draw_next()
        state = build_beamer_state(svc, revealed=True, timer_text="Auflösung", banner="BINGO!")
        self.assertEqual((state.title, state.artist, state.revealed, state.recent), (HIDDEN, "", False, ()))
        self.assertEqual((state.song_line, state.timer, state.banner), ("Song 2", "Auflösung", "BINGO!"))
        self.assertNotIn(first.display_name, repr(state))
        svc.beamer_reveal = True
        self.assertEqual(build_beamer_state(svc, revealed=True).recent, (first.display_name,))

    def test_recent_size_reaches_beamer(self):
        svc = service()
        svc.game.caller.draw_next()
        svc.game.caller.draw_next()
        self.assertEqual(build_beamer_state(svc, revealed=False).recent_scale, 1.0)
        svc.beamer_recent_size = "sehr_gross"
        self.assertEqual(build_beamer_state(svc, revealed=False).recent_scale, 2.0)

    def test_recent_list_is_limited(self):
        svc = service()
        for _ in range(12):
            svc.game.caller.draw_next()
        drawn = svc.game.caller.drawn
        # Standard: die letzten 3 vorherigen Songs, neuester zuerst, ohne den aktuellen
        self.assertEqual(build_beamer_state(svc, revealed=True).recent,
                         tuple(song.display_name for song in reversed(drawn[-4:-1])))
        for count in range(0, 6):
            svc.beamer_recent_count = count
            self.assertEqual(len(build_beamer_state(svc, revealed=True).recent), count)
        self.assertEqual(build_beamer_state(GameService(), revealed=False).song_line, "Noch keine Runde")


if __name__ == "__main__":
    unittest.main()
