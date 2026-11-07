"""Text measurement and wrapping with Liberation Sans (Arial metrics)."""
import os
from functools import lru_cache

_FONT_DIRS = [
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/liberation2",
    "/usr/share/fonts/liberation",
    "/Library/Fonts",
    "C:/Windows/Fonts",
]
_FILES = {
    (False, False): ["LiberationSans-Regular.ttf", "Arial.ttf", "arial.ttf"],
    (True, False): ["LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"],
    (False, True): ["LiberationSans-Italic.ttf", "Arial Italic.ttf", "ariali.ttf"],
    (True, True): ["LiberationSans-BoldItalic.ttf", "Arial Bold Italic.ttf", "arialbi.ttf"],
}


@lru_cache(maxsize=None)
def _font(size, bold=False, italic=False):
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for d in _FONT_DIRS:
        for f in _FILES[(bold, italic)]:
            p = os.path.join(d, f)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return None


def width(text, size, bold=False, italic=False):
    """Rendered width in px. Falls back to an average-width estimate."""
    if not text:
        return 0.0
    f = _font(size, bold, italic)
    if f is None:
        return len(text) * size * (0.60 if bold else 0.55)
    return float(f.getlength(text))


def font_available():
    return _font(12) is not None


def wrap(text, size, max_w, bold=False):
    """Greedy word wrap to max_w px. Words longer than max_w are kept whole."""
    words = str(text).split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if width(trial, size, bold) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def line_height(size):
    return round(size * 1.25)
