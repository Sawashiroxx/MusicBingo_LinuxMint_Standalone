"""Text-Normalisierung für robuste Titelvergleiche."""
import re
import unicodedata


def normalize(value: str) -> str:
    """Kleinbuchstaben, ohne Akzente, nur Buchstaben und Ziffern."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return "".join(char for char in without_marks if char.isalnum())


# Zusätze, die auf Streamingdiensten und YouTube an Titel gehängt werden.
# Bewusst als Wortmenge statt Regex-Alternation: keine Rückfall-Explosion (ReDoS).
_NOISE_TOKENS = frozenset({
    "official", "offiziell", "offizielles", "offizielle", "music", "musik", "video", "audio", "lyric",
    "lyrics", "visualizer", "visualiser", "hd", "hq", "4k", "remaster", "remastered", "radio", "edit",
    "single", "album", "version", "mono", "stereo", "live", "clip", "officiel", "videoclip", "explicit",
    "clean", "mv", "musikvideo",
})
MAX_TITLE_LENGTH = 300
_BRACKETS = re.compile(r"\s*[\(\[\{]([^\(\)\[\]\{\}]{0,200})[\)\]\}]")
_TOKEN_SPLIT = re.compile(r"[\s/&,+\-]+")
_FEAT_PREFIX = re.compile(r"^(?:feat\.?|ft\.?|featuring|with)\s", re.IGNORECASE)
# Nur eindeutige Kennzeichen; „with“ würde Titel wie „Dancing with Myself“ zerstören.
_FEAT = re.compile(r"\s+(?:feat\.|ft\.|featuring)\s+.*$", re.IGNORECASE)
_PIPE_SUFFIX = re.compile(r"\s+[|｜]\s+.*$")
_HASHTAGS = re.compile(r"(?:\s+#\w+)+\s*$")
_LEADING_NUMBER = re.compile(r"^\s*\d{1,3}\s*[.)]\s+")


def _is_noise(text: str) -> bool:
    """True, wenn der Text nur aus Zusätzen wie „Official Video“ oder „2011 Remaster“ besteht."""
    tokens = [token for token in _TOKEN_SPLIT.split(text.casefold()) if token]
    return bool(tokens) and all(token in _NOISE_TOKENS or (token.isdigit() and len(token) == 4) for token in tokens)


def _drop_dash_suffix(text: str) -> str:
    """Entfernt „ - Remastered 2011“, „ - Radio Edit“, „ - From „Film““ am Ende."""
    index = text.rfind(" - ")
    if index <= 0:
        return text
    suffix = text[index + 3:].strip()
    if _is_noise(suffix) or suffix.casefold().startswith("from "):
        return text[:index].rstrip()
    return text


def clean_title(title: str) -> str:
    """Entfernt Zusätze wie „(Official Video)“, „- Remastered 2011“, „feat. X“."""
    original = title.strip()[:MAX_TITLE_LENGTH]
    text = _PIPE_SUFFIX.sub("", original)
    text = _HASHTAGS.sub("", text)

    def drop_noise(match: re.Match) -> str:
        inner = match.group(1).strip()
        if _is_noise(inner) or _FEAT_PREFIX.match(inner):
            return ""
        return match.group(0)

    for _ in range(5):  # begrenzte Wiederholung, z. B. „(Live) [Official Video]“
        previous = text
        text = _BRACKETS.sub(drop_noise, text).strip()
        text = _drop_dash_suffix(text)
        if text == previous:
            break
    text = _FEAT.sub("", text).strip()
    return text or original


def strip_leading_number(line: str) -> str:
    return _LEADING_NUMBER.sub("", line, count=1)


def artist_tokens(artist: str) -> set[str]:
    """Einzelne Künstlernamen, z. B. aus „A & B feat. C“ → {a, b, c}."""
    parts = re.split(r"\s*(?:,|&|\+|/|;|\bx\b|\band\b|\bund\b|\bfeat\.?|\bft\.?|\bfeaturing\b|\bwith\b)\s*", artist, flags=re.IGNORECASE)
    tokens = {normalize(part) for part in parts}
    tokens.discard("")
    # „ - Topic“-Kanäle von YouTube und VEVO-Kanäle auf den Künstler zurückführen.
    cleaned = set()
    for token in tokens:
        for suffix in ("topic", "vevo", "official", "music"):
            if token.endswith(suffix) and len(token) > len(suffix) + 1:
                token = token[: -len(suffix)]
        cleaned.add(token)
    return cleaned


def count_text(count: int, singular: str, plural: str) -> str:
    """„1 Link“, „2 Links“, „0 Links“ – Anzahl mit passender Einzahl/Mehrzahl."""
    return f"{count} {singular if count == 1 else plural}"
