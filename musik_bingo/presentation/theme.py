"""Farbwelten und GTK-CSS für Musik Bingo (dunkel und hell)."""

PALETTES = {
    "dark": {
        "bg": "#0e1318", "surface": "#151c23", "surface2": "#1b242d", "raised": "#212c37",
        "border": "#2a3744", "text": "#edf1f5", "muted": "#8d9bab", "accent": "#e5b647",
        "accent_text": "#1a1406", "accent_hover": "#f1c868", "green": "#3fb984", "red": "#ef6b5f",
        "hero1": "#1d4a37", "hero2": "#0f2a20", "hero_text": "#ffffff", "hero_muted": "#b9d6c7",
        "card": "#fbf8f0", "card_text": "#1f2622", "cell": "#ffffff", "cell_border": "#d9d2c0",
        "free": "#f3dc9a", "free_text": "#5b4310", "selection": "#2c3a48",
    },
    "light": {
        "bg": "#f3f0e8", "surface": "#ffffff", "surface2": "#faf8f3", "raised": "#f1ede4",
        "border": "#e2dccd", "text": "#1c2329", "muted": "#66717c", "accent": "#c9952a",
        "accent_text": "#ffffff", "accent_hover": "#b6841d", "green": "#24875a", "red": "#c43d31",
        "hero1": "#21543f", "hero2": "#143528", "hero_text": "#ffffff", "hero_muted": "#c4dfd0",
        "card": "#fffdf7", "card_text": "#1f2622", "cell": "#ffffff", "cell_border": "#ddd6c4",
        "free": "#f3dc9a", "free_text": "#5b4310", "selection": "#efe6d2",
    },
}

_CSS = """
window, dialog, messagedialog, filechooser, .main-bg {{ background-color: {bg}; color: {text}; }}
dialog .dialog-action-area, messagedialog .dialog-action-area {{ background-color: {bg}; }}
scale value {{ color: {text}; font-weight: 700; }}
headerbar {{ background-image: none; background-color: {surface}; color: {text};
  border-bottom: 1px solid {border}; box-shadow: none; padding: 4px 10px; min-height: 46px; }}
headerbar .title {{ font-weight: 800; letter-spacing: 0.5px; }}
headerbar .subtitle {{ color: {muted}; }}
headerbar button {{ min-height: 30px; }}
label {{ color: {text}; }}
.muted, .muted label {{ color: {muted}; }}
.small {{ font-size: 0.88em; }}
.tiny {{ font-size: 0.78em; letter-spacing: 1px; font-weight: 700; }}
.page-title {{ font-size: 1.55em; font-weight: 800; }}
.panel-title {{ font-size: 1.08em; font-weight: 800; }}
.pill {{ background-color: {surface2}; border: 1px solid {border}; border-radius: 999px; padding: 2px 10px; }}
.pill-ok {{ color: {green}; border-color: {green}; }}
.pill-warn {{ color: {red}; border-color: {red}; }}
.pool-ready {{ color: {green}; font-weight: 700; }}
.pool-warning {{ color: {red}; font-weight: 700; }}

/* Seitenleiste */
.app-sidebar {{ background-color: {surface}; border-right: 1px solid {border}; }}
.app-sidebar list, .app-sidebar row {{ background-color: transparent; }}
.nav-row {{ border-radius: 12px; margin: 3px 10px; padding: 10px 12px; }}
.nav-row:hover {{ background-color: {surface2}; }}
.nav-row:selected, .nav-row:selected:hover {{ background-color: {selection}; }}
.nav-row:selected .nav-title {{ color: {accent}; }}
.nav-number {{ background-color: {raised}; border-radius: 999px; min-width: 26px; min-height: 26px;
  font-weight: 800; color: {muted}; }}
.nav-row:selected .nav-number {{ background-color: {accent}; color: {accent_text}; }}
.nav-title {{ font-weight: 800; }}
.brand {{ font-size: 1.25em; font-weight: 900; letter-spacing: 0.5px; }}
.summary {{ background-color: {surface2}; border: 1px solid {border}; border-radius: 14px; padding: 12px; margin: 10px; }}
.summary-value {{ font-weight: 800; }}

/* Flächen */
.panel {{ background-color: {surface}; border: 1px solid {border}; border-radius: 16px; padding: 18px; }}
.panel-flat {{ background-color: {surface2}; border: 1px solid {border}; border-radius: 12px; padding: 12px; }}
.hero {{ background-image: linear-gradient(135deg, {hero1}, {hero2}); border-radius: 22px; padding: 30px 28px; }}
.hero label {{ color: {hero_text}; }}
.hero .hero-muted {{ color: {hero_muted}; }}
.hero-kicker {{ font-size: 0.82em; font-weight: 800; letter-spacing: 2px; color: {accent}; }}
.hero .hero-kicker {{ color: {accent}; }}
.song-title {{ font-size: 2.6em; font-weight: 900; }}
.song-artist {{ font-size: 1.35em; font-weight: 600; }}
.hero .chip {{ background-color: alpha(#ffffff, 0.12); border-radius: 999px; padding: 3px 12px; }}

/* Bedienelemente */
button {{ background-image: none; background-color: {raised}; color: {text}; border: 1px solid {border};
  border-radius: 10px; padding: 7px 14px; box-shadow: none; text-shadow: none; }}
button:hover {{ background-color: {selection}; }}
button:disabled {{ opacity: 0.45; }}
button:disabled label {{ color: {muted}; }}
button.primary {{ background-color: {accent}; border-color: {accent}; color: {accent_text}; font-weight: 800; }}
button.primary label {{ color: {accent_text}; }}
button.primary:hover {{ background-color: {accent_hover}; border-color: {accent_hover}; }}
button.big {{ padding: 13px 18px; font-size: 1.08em; }}
button.danger label {{ color: {red}; }}
button.flat {{ background-color: transparent; border-color: transparent; }}
button.flat:hover {{ background-color: {surface2}; }}
.linked button {{ border-radius: 0; }}
.linked button:first-child {{ border-radius: 10px 0 0 10px; }}
.linked button:last-child {{ border-radius: 0 10px 10px 0; }}
.linked button:checked {{ background-color: {accent}; border-color: {accent}; }}
.linked button:checked label {{ color: {accent_text}; font-weight: 800; }}
entry, spinbutton, combobox button {{ background-image: none; background-color: {surface2}; color: {text};
  border: 1px solid {border}; border-radius: 9px; min-height: 30px; box-shadow: none; }}
spinbutton button {{ border: none; background-color: transparent; }}
textview, textview text, textview border {{ background-color: {surface2}; color: {text}; }}
.editor {{ border: 1px solid {border}; border-radius: 12px; }}
.editor textview {{ font-size: 1.02em; }}
check, radio {{ background-image: none; background-color: {surface2}; border: 1px solid {border}; color: {accent_text}; }}
check:checked, radio:checked {{ background-color: {accent}; border-color: {accent}; }}
switch {{ background-image: none; background-color: {raised}; border: 1px solid {border}; border-radius: 999px; }}
switch:checked {{ background-color: {green}; border-color: {green}; }}
switch slider {{ background-image: none; background-color: #ffffff; border-radius: 999px; border: none; }}
scale trough {{ background-color: {raised}; border-radius: 6px; min-height: 6px; }}
scale highlight {{ background-color: {accent}; border-radius: 6px; }}
scale slider {{ background-image: none; background-color: {accent}; border-radius: 999px; min-width: 18px; min-height: 18px; border: none; }}
progressbar trough {{ min-height: 10px; border-radius: 8px; background-color: {raised}; border: none; }}
progressbar progress {{ min-height: 10px; border-radius: 8px; background-color: {accent}; border: none; }}
popover, popover.background {{ background-color: {surface}; border: 1px solid {border}; border-radius: 12px; }}
popover modelbutton {{ padding: 6px 10px; border-radius: 8px; }}
popover modelbutton:hover {{ background-color: {surface2}; }}
tooltip, tooltip.background {{ background-color: {raised}; color: {text}; border-radius: 8px; }}
tooltip label {{ color: {text}; }}
list, row {{ background-color: transparent; }}
treeview.view {{ background-color: {surface}; color: {text}; }}
treeview.view:hover {{ background-color: {surface2}; }}
treeview.view:selected, treeview.view:selected:focus {{ background-color: {accent}; color: {accent_text}; }}
treeview.view header button {{ background-color: {surface2}; color: {muted}; border-radius: 0;
  border-width: 0 1px 1px 0; border-color: {border}; padding: 4px 8px; }}
treeview.view header button label {{ color: {muted}; font-weight: 700; }}
placessidebar row label, filechooser label {{ color: {text}; }}
filechooser pathbar button:checked {{ background-color: {accent}; }}
.pool-row {{ border-radius: 9px; padding: 2px 4px; }}
.pool-row:hover {{ background-color: {surface2}; }}
.pool-drawn label.name {{ color: {muted}; }}
.pool-badge {{ font-weight: 800; color: {accent}; min-width: 28px; }}
.pool-open {{ color: {muted}; min-width: 28px; }}
.history-chip {{ background-color: {surface2}; border: 1px solid {border}; border-radius: 10px; padding: 7px 11px; }}
.warning-box {{ background-color: alpha({red}, 0.14); border: 1px solid {red}; border-radius: 12px; padding: 10px 14px; }}
.warning-box label {{ color: {text}; }}
.warning-text {{ color: {red}; font-weight: 600; }}
.info-box {{ background-color: alpha({green}, 0.13); border: 1px solid {green}; border-radius: 12px; padding: 10px 14px; }}
.statusbar {{ background-color: {surface}; border-top: 1px solid {border}; padding: 6px 16px; }}
.statusbar label {{ color: {muted}; }}
scrollbar slider {{ background-color: {border}; border-radius: 999px; min-width: 6px; min-height: 6px; }}
scrollbar {{ background-color: transparent; border: none; }}

/* Kartenvorschau */
.bingo-card {{ background-color: {card}; border: 1px solid {cell_border}; border-radius: 14px; padding: 12px; }}
.bingo-card label {{ color: {card_text}; }}
.card-head {{ background-color: {hero1}; border-radius: 9px; padding: 6px 10px; }}
.card-head label {{ color: #ffffff; font-weight: 800; }}
label.bingo-cell {{ background-color: {cell}; border: 1px solid {cell_border}; border-radius: 6px; padding: 6px 3px; font-size: 0.82em; }}
.bingo-cell-free {{ background-color: {free}; border-color: #d9bd6a; }}
.bingo-cell-free label, label.bingo-cell-free {{ color: {free_text}; font-weight: 800; }}
.bingo-cell-hit {{ background-color: #2e8b57; border-color: #2e8b57; }}
.bingo-cell-hit label, label.bingo-cell-hit {{ color: #ffffff; font-weight: 700; }}
.bingo-cell-line {{ background-color: {accent}; border-color: {accent}; }}
.bingo-cell-line label, label.bingo-cell-line {{ color: #1a1406; font-weight: 800; }}
dialog .dialog-vbox, messagedialog .dialog-vbox, dialog box, messagedialog box {{ background-color: transparent; }}
dialog headerbar, messagedialog headerbar {{ border-bottom: none; }}

/* Beamer-Fenster für die Gäste */
.beamer {{ background-image: linear-gradient(160deg, {hero1}, {hero2}); }}
.beamer label {{ color: #ffffff; }}
.beamer-event {{ font-size: 30px; font-weight: 900; letter-spacing: 3px; color: {accent}; }}
.beamer .beamer-event {{ color: {accent}; }}
.beamer-round {{ font-size: 26px; font-weight: 700; color: {hero_muted}; }}
.beamer .beamer-round {{ color: {hero_muted}; }}
.beamer-song {{ font-size: 64px; font-weight: 900; }}
.beamer-title {{ font-size: 92px; font-weight: 900; }}
.beamer-artist {{ font-size: 48px; font-weight: 600; color: {hero_muted}; }}
.beamer .beamer-artist {{ color: {hero_muted}; }}
.beamer-timer {{ font-size: 40px; font-weight: 800; color: {accent}; }}
.beamer .beamer-timer {{ color: {accent}; }}
.beamer-recent {{ font-size: 24px; color: {hero_muted}; }}
.beamer .beamer-recent {{ color: {hero_muted}; }}
.beamer-banner {{ background-color: {accent}; border-radius: 24px; padding: 18px 40px; }}
.beamer .beamer-banner label {{ color: {accent_text}; font-size: 54px; font-weight: 900; }}
"""


def css_for(theme: str) -> str:
    return _CSS.format(**PALETTES["light" if theme == "light" else "dark"])
