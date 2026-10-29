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
