"""Zentrale Pfade zu mitgelieferten Daten (Songlisten, Icon)."""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
DEFAULT_SONGS = DATA_DIR / "default_songs.txt"
CATALOG_DIR = DATA_DIR / "catalogs"
ICON_PATH = DATA_DIR / "icons" / "musik-bingo.svg"
