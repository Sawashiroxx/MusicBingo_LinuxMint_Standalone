import unittest
from types import SimpleNamespace

import cairo

from musik_bingo.domain.card_generator import required_songs
from musik_bingo.domain.models import BingoCard, Song
from musik_bingo.presentation.gtk_app import MusikBingoWindow


class PrintRendererTests(unittest.TestCase):
    def test_all_card_sizes_and_free_space_options_render(self):
        class Renderer:
            _draw_centered_text = staticmethod(MusikBingoWindow._draw_centered_text)
            _draw_card = MusikBingoWindow._draw_card

        renderer = Renderer()
        for size in (3, 4, 5):
            for free_space in (False, True):
                with self.subTest(size=size, free_space=free_space):
                    renderer.service = SimpleNamespace(
                        game=SimpleNamespace(size=size, free_space=free_space)
                    )
                    songs = [
                        Song("UngewöhnlichlangesWeihnachtstitelwort", f"Interpret {i}")
                        for i in range(required_songs(size, free_space))
                    ]
                    card = BingoCard(songs)
                    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 595, 842)
                    renderer._draw_card(cairo.Context(surface), card, 1, 24, 24, 547, 387)
                    surface.flush()
                    self.assertTrue(any(surface.get_data()))
                    surface.finish()


if __name__ == "__main__":
    unittest.main()
