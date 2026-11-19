"""Cairo-Zeichnung der Bingokarten für Druck und PDF (ohne GTK-Fenster nutzbar)."""
import math

GREEN = (0.13, 0.33, 0.25)
GOLD = (0.79, 0.58, 0.16)
FREE_BG = (0.95, 0.86, 0.60)
INK = (0.12, 0.13, 0.13)
LINE = (0.62, 0.60, 0.55)
MUTED = (0.42, 0.44, 0.45)


def _rounded(cr, x: float, y: float, w: float, h: float, r: float) -> None:
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _note(cr, cx: float, cy: float, h: float) -> None:
    """Achtelnote als Vektor (unabhängig von Schriftarten)."""
    head_r = h * 0.2
    stem_x = cx + head_r * 0.95
    cr.save()
    cr.translate(cx, cy + h * 0.32)
    cr.scale(1.0, 0.75)
    cr.arc(0, 0, head_r, 0, 2 * math.pi)
    cr.restore()
    cr.fill()
    cr.set_line_width(max(1.0, h * 0.08))
    cr.move_to(stem_x, cy + h * 0.32)
    cr.line_to(stem_x, cy - h * 0.5)
    cr.curve_to(stem_x + h * 0.15, cy - h * 0.25, stem_x + h * 0.4, cy - h * 0.25, stem_x + h * 0.32, cy)
    cr.stroke()


def _star(cr, cx: float, cy: float, r: float) -> None:
    cr.set_source_rgb(0.78, 0.55, 0.12)
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.45
        angle = -math.pi / 2 + i * math.pi / 5
        point = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        cr.line_to(*point) if i else cr.move_to(*point)
    cr.close_path()
    cr.fill()


def wrap_lines(cr, text: str, max_width: float, max_lines: int = 4) -> list[str]:
    """Bricht Text in Zeilen um; überlange Wörter werden zeichenweise geteilt."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        pieces: list[str] = []
        piece = ""
        for character in word:
            if piece and cr.text_extents(piece + character)[2] > max_width:
                pieces.append(piece)
                piece = character
            else:
                piece += character
        if piece:
            pieces.append(piece)
        for word_piece in pieces:
            candidate = f"{current} {word_piece}".strip()
            if current and cr.text_extents(candidate)[2] > max_width:
                lines.append(current)
                current = word_piece
            else:
                current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and cr.text_extents(last + "…")[2] > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def draw_centered_text(cr, text: str, x: float, y: float, width: float, height: float,
                       bold: bool = False, color=INK) -> None:
    cr.set_source_rgb(*color)
    cr.select_font_face("Sans", 0, 1 if bold else 0)
    font_size = max(7.0, min(10.5, width / 13, height / 4.2))
    cr.set_font_size(font_size)
    max_width = max(4.0, width - 8)
    max_lines = max(1, min(5, int((height - 4) // (font_size * 1.25))))
    lines = wrap_lines(cr, text, max_width, max_lines)
    line_height = font_size * 1.25
    baseline = y + (height - len(lines) * line_height) / 2 + font_size
    for line in lines:
        extents = cr.text_extents(line)
        cr.move_to(x + (width - extents[2]) / 2 - extents[0], baseline)
        cr.show_text(line)
        baseline += line_height


def draw_card(cr, card, number: int, x: float, y: float, width: float, height: float,
              size: int, free_space: bool, diagonal_wins: bool = False, title: str = "MUSIK BINGO") -> None:
    free = free_space and size % 2 == 1
    # Karte
    _rounded(cr, x, y, width, height, 10)
    cr.set_source_rgb(1, 1, 1)
    cr.fill_preserve()
    cr.set_source_rgb(*LINE)
    cr.set_line_width(1)
    cr.stroke()

    pad = 10
    head_h = min(34, height * 0.12)
    _rounded(cr, x + pad, y + pad, width - 2 * pad, head_h, 7)
    cr.set_source_rgb(*GREEN)
    cr.fill()
    cr.select_font_face("Sans", 0, 1)
    cr.set_font_size(head_h * 0.46)
    cr.set_source_rgb(1, 1, 1)
    _note(cr, x + pad + 14, y + pad + head_h * 0.5, head_h * 0.5)
    cr.move_to(x + pad + 14 + head_h * 0.55, y + pad + head_h * 0.66)
    cr.show_text(title)
    label = f"Karte #{number}"
    extents = cr.text_extents(label)
    cr.set_source_rgb(0.98, 0.84, 0.45)
    cr.move_to(x + width - pad - 12 - extents[2], y + pad + head_h * 0.66)
    cr.show_text(label)

    name_y = y + pad + head_h + 16
    cr.select_font_face("Sans", 0, 0)
    cr.set_font_size(9.5)
    cr.set_source_rgb(*MUTED)
    cr.move_to(x + pad + 2, name_y)
    cr.show_text("Name:")
    cr.set_line_width(0.6)
    cr.move_to(x + pad + 36, name_y + 2)
    cr.line_to(x + width * 0.62, name_y + 2)
    cr.stroke()

    rule = "Reihe oder Spalte voll" + (" (auch diagonal)" if diagonal_wins else "") + " → BINGO!"
    footer_h = 16
    grid_x = x + pad
    grid_y = name_y + 10
    grid_w = width - 2 * pad
    grid_h = y + height - pad - footer_h - grid_y
    cell_w = grid_w / size
    cell_h = grid_h / size
    song_index = 0
    for index in range(size * size):
        col, row = index % size, index // size
        cx, cy = grid_x + col * cell_w, grid_y + row * cell_h
        is_free = free and index == size * size // 2
        cr.rectangle(cx, cy, cell_w, cell_h)
        cr.set_source_rgb(*(FREE_BG if is_free else (1, 1, 1)))
        cr.fill_preserve()
        cr.set_source_rgb(*LINE)
        cr.set_line_width(0.7)
        cr.stroke()
        if is_free:
            star_r = min(cell_w, cell_h) * 0.14
            _star(cr, cx + cell_w / 2, cy + cell_h / 2 - star_r * 0.9, star_r)
            draw_centered_text(cr, "FREI", cx, cy + star_r * 1.1, cell_w, cell_h, bold=True, color=(0.36, 0.26, 0.06))
        else:
            draw_centered_text(cr, card.songs[song_index].display_name, cx, cy, cell_w, cell_h)
            song_index += 1
    # kräftiger Außenrahmen des Rasters
    cr.rectangle(grid_x, grid_y, grid_w, grid_h)
    cr.set_source_rgb(*GREEN)
    cr.set_line_width(1.4)
    cr.stroke()

    cr.select_font_face("Sans", 0, 0)
    cr.set_font_size(8.5)
    cr.set_source_rgb(*MUTED)
    extents = cr.text_extents(rule)
    cr.move_to(x + (width - extents[2]) / 2, y + height - pad - 4)
    cr.show_text(rule)
