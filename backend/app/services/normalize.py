"""Search normalisation. The raw form is always kept; this only builds a separate search key."""

import re
import unicodedata

_CONTROL = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]")
_SPACE = re.compile(r"\s+")


def normalize_form(raw: str) -> str:
    """NFC-normalise, drop control characters and collapse whitespace.

    Diacritics, case and punctuation are kept: they are meaningful in the source
    transliterations (see docs/LINGUISTIC_ENGINE.md §3, step 1).
    """
    text = _CONTROL.sub("", unicodedata.normalize("NFC", raw))
    return _SPACE.sub(" ", text).strip()


_FOLD = str.maketrans({"ʰ": "h", "ŋ": "ng", "ə": "e", "ʷ": "w", "ʸ": "y", "ɛ": "e", "ɔ": "o"})
_MARKERS = re.compile(r"[*√\-°()\[\]]")


def search_key(raw: str) -> str:
    """Loose key for romanised input: lowercase, no diacritics or reconstruction markers.

    Only used to *find* candidates ("dant" finds "dā̃t"); results say they matched loosely.
    Native-script text is returned unchanged apart from normalisation.
    """
    text = normalize_form(raw).lower().translate(_FOLD)
    decomposed = unicodedata.normalize("NFD", text)
    if any(ord(ch) > 0x2FF and not unicodedata.combining(ch) for ch in decomposed):
        return text  # contains non-Latin letters: do not strip marks that carry vowels
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _MARKERS.sub("", stripped).replace(" ", "")
