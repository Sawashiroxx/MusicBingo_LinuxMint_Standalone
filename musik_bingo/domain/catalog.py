"""Mitgelieferte Songkataloge (Charts, Weihnachten) und Zufallsmix."""
import random
from dataclasses import dataclass, field

from .models import Song
from .song_list import parse_songs
from .text import normalize

CATEGORIES = ("weihnachten", "charts")


@dataclass
class Catalog:
    key: str
    name: str
    category: str
    source: str = ""
    songs: list[Song] = field(default_factory=list)


def parse_catalog(key: str, text: str) -> Catalog:
    """Katalogdatei: Kopfzeilen „# name: …“, „# kategorie: …“, „# quelle: …“, danach Songs."""
    meta: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and ":" in stripped:
            name, value = stripped[1:].split(":", 1)
            meta[name.strip().casefold()] = value.strip()
    category = meta.get("kategorie", "charts").casefold()
    if category not in CATEGORIES:
        raise ValueError(f"Unbekannte Katalogkategorie „{category}“ in {key}.")
    songs = parse_songs(text)
    if not songs:
        raise ValueError(f"Der Katalog {key} enthält keine Songs.")
    return Catalog(key, meta.get("name", key), category, meta.get("quelle", ""), songs)


def mix_key(song: Song) -> tuple[str, str]:
    """Vergleichsschlüssel über Kataloge hinweg (Schreibweisen, Akzente egal)."""
    return normalize(song.title), normalize(song.artist)


def unique_songs(catalogs: list[Catalog]) -> list[Song]:
    result: list[Song] = []
    seen: set[tuple[str, str]] = set()
    for catalog in catalogs:
        for song in catalog.songs:
            key = mix_key(song)
            if key not in seen:
                seen.add(key)
                result.append(song)
    return result


@dataclass
class MixResult:
    songs: list[Song]
    christmas: int
    charts: int
    shortfall: int  # wie viele Songs zur Wunschmenge fehlen


def random_mix(
    christmas_pool: list[Song],
    chart_pool: list[Song],
    total: int,
    christmas_percent: int,
    rng: random.Random | None = None,
) -> MixResult:
    """Zufällige Auswahl aus Weihnachts- und Chartsongs im gewünschten Verhältnis.

    Reicht eine Kategorie nicht, wird mit der anderen aufgefüllt. Ein Song,
    der in beiden Pools vorkommt (z. B. „Last Christmas“ in den Charts),
    wird nur einmal gewählt.
    """
    if not isinstance(total, int) or isinstance(total, bool) or not 1 <= total <= 2000:
        raise ValueError("Die Anzahl Songs muss zwischen 1 und 2000 liegen.")
    if not isinstance(christmas_percent, int) or isinstance(christmas_percent, bool) or not 0 <= christmas_percent <= 100:
        raise ValueError("Der Weihnachtsanteil muss zwischen 0 und 100 Prozent liegen.")
    randomizer = rng or random.SystemRandom()

    def dedupe(pool: list[Song], exclude: set[tuple[str, str]]) -> list[Song]:
        seen = set(exclude)
        result = []
        for song in pool:
            key = mix_key(song)
            if key not in seen:
                seen.add(key)
                result.append(song)
        return result

    xmas = dedupe(christmas_pool, set())
    charts = dedupe(chart_pool, {mix_key(song) for song in xmas})
    # Gleicher Titel von verschiedenen Interpreten („Last Christmas“ von Wham! und
    # Taylor Swift) ist für Gäste nicht unterscheidbar: nur eine Version zulassen.
    titles: set[str] = set()
    distinct = []
    for song in xmas + charts:
        if mix_key(song)[0] not in titles:
            titles.add(mix_key(song)[0])
            distinct.append(song)
    xmas = [song for song in distinct if song in xmas]
    charts = [song for song in distinct if song not in xmas]
    want_xmas = (total * christmas_percent + 50) // 100  # kaufmännisch runden
    want_charts = total - want_xmas
    take_xmas = min(want_xmas, len(xmas))
    take_charts = min(want_charts, len(charts))
    # Fehlende Plätze mit der anderen Kategorie auffüllen.
    take_charts = min(len(charts), take_charts + (want_xmas - take_xmas))
    take_xmas = min(len(xmas), take_xmas + (total - take_xmas - take_charts))
    chosen = randomizer.sample(xmas, take_xmas) + randomizer.sample(charts, take_charts)
    randomizer.shuffle(chosen)
    return MixResult(chosen, take_xmas, take_charts, total - len(chosen))
