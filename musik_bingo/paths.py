"""Zentrale Pfade zu mitgelieferten Daten (Songlisten, Icon)."""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
DEFAULT_SONGS = DATA_DIR / "default_songs.txt"
CATALOG_DIR = DATA_DIR / "catalogs"
ICON_THEME_DIR = DATA_DIR / "icons" / "hicolor"
ICON_PATH = ICON_THEME_DIR / "scalable" / "apps" / "musik-bingo.svg"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
