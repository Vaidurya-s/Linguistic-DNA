"""Rule-based romanisation of Indic scripts to ISO 15919 (our own code, no external data).

Used only to *find* romanised records for a native-script query; results say they were matched
through transliteration. An inherent vowel follows every consonant without a vowel sign or
virama. For scripts of schwa-deleting languages it is dropped word-finally and in the medial
context V C _ C V; this is approximate, and the loose search key (which ignores length marks)
absorbs the rest.
"""

import unicodedata

# Offsets inside each Brahmic Unicode block share the same layout (ISCII-derived).
BLOCKS = {
    "Devanagari": 0x0900,
    "Bengali": 0x0980,
    "Gurmukhi": 0x0A00,
    "Gujarati": 0x0A80,
    "Oriya": 0x0B00,
    "Tamil": 0x0B80,
    "Telugu": 0x0C00,
    "Kannada": 0x0C80,
    "Malayalam": 0x0D00,
}

VOWELS = {  # independent vowels, by offset
    0x05: "a",
    0x06: "ā",
    0x07: "i",
    0x08: "ī",
    0x09: "u",
    0x0A: "ū",
    0x0B: "r̥",
    0x0C: "l̥",
    0x0E: "e",
    0x0F: "ē",
    0x10: "ai",
    0x12: "o",
    0x13: "ō",
    0x14: "au",
    0x60: "r̥̄",
    0x61: "l̥̄",
}
SIGNS = {  # dependent vowel signs
    0x3E: "ā",
    0x3F: "i",
    0x40: "ī",
    0x41: "u",
    0x42: "ū",
    0x43: "r̥",
    0x44: "r̥̄",
    0x46: "e",
    0x47: "ē",
    0x48: "ai",
    0x4A: "o",
    0x4B: "ō",
    0x4C: "au",
    0x62: "l̥",
    0x63: "l̥̄",
}
CONSONANTS = {
    0x15: "k",
    0x16: "kh",
    0x17: "g",
    0x18: "gh",
    0x19: "ṅ",
    0x1A: "c",
    0x1B: "ch",
    0x1C: "j",
    0x1D: "jh",
    0x1E: "ñ",
    0x1F: "ṭ",
    0x20: "ṭh",
    0x21: "ḍ",
    0x22: "ḍh",
    0x23: "ṇ",
    0x24: "t",
    0x25: "th",
    0x26: "d",
    0x27: "dh",
    0x28: "n",
    0x29: "ṉ",
    0x2A: "p",
    0x2B: "ph",
    0x2C: "b",
    0x2D: "bh",
    0x2E: "m",
    0x2F: "y",
    0x30: "r",
    0x31: "ṟ",
    0x32: "l",
    0x33: "ḷ",
    0x34: "ḻ",
    0x35: "v",
    0x36: "ś",
    0x37: "ṣ",
    0x38: "s",
    0x39: "h",
    0x58: "q",
    0x59: "ḵh",
    0x5A: "ġ",
    0x5B: "z",
    0x5C: "ṛ",
    0x5D: "ṛh",
    0x5E: "f",
    0x5F: "ẏ",
}
MARKS = {0x01: "m̐", 0x02: "ṁ", 0x03: "ḥ", 0x70: "ṁ", 0x3C: ""}  # 0x70 is Gurmukhi tippi
VIRAMA, NUKTA = 0x4D, 0x3C
DIGITS = range(0x66, 0x70)

# Script-specific values that differ from the shared layout.
OVERRIDES = {
    "Bengali": {0x2C: "b", 0x35: "b"},  # Bengali has no separate v; য় (0x5F) is ẏ
    "Tamil": {0x0E: "e", 0x0F: "ē", 0x12: "o", 0x13: "ō"},
}
NUKTA_FORMS = {"k": "q", "kh": "ḵh", "g": "ġ", "j": "z", "ḍ": "ṛ", "ḍh": "ṛh", "ph": "f", "y": "ẏ"}
# Languages written in these scripts usually do not pronounce some inherent vowels.
SCHWA_DELETING = {"Devanagari", "Bengali", "Gurmukhi", "Gujarati"}


def script_of(text: str) -> str | None:
    for ch in text:
        cp = ord(ch)
        for name, base in BLOCKS.items():
            if base <= cp < base + 0x80:
                return name
    return None


SCHWA = object()  # an inherent vowel, which may be deleted


def romanize(text: str, drop_schwa: bool | None = None) -> str | None:
    """ISO 15919-style romanisation, or None if the text is not in a supported script."""
    script = script_of(text)
    drop = script in SCHWA_DELETING if drop_schwa is None else drop_schwa
    return _romanize(text, drop, "consonant")


def _romanize(text: str, drop: bool, nasal: str) -> str | None:
    text = unicodedata.normalize("NFC", text)
    script = script_of(text)
    if not script:
        return None
    base = BLOCKS[script]
    over = OVERRIDES.get(script, {})
    words = []
    for word in text.split(" "):
        tokens = _tokens(word, base, over)
        if drop:
            tokens = _delete_schwas(tokens)
        words.append(_render(tokens, nasal))
    return unicodedata.normalize("NFC", " ".join(words))


def _tokens(word: str, base: int, over: dict) -> list:
    """Sequence of ('C'|'V'|'X', text) tokens and SCHWA markers."""
    out: list = []
    pending = False
    geminate = False
    for ch in word:
        off = ord(ch) - base
        inside = 0 <= off < 0x80
        if inside and off in CONSONANTS:
            if pending:
                out.append(SCHWA)
            value = over.get(off, CONSONANTS[off])
            if geminate:  # Gurmukhi addak doubles the next consonant
                value = value[0] + value
                geminate = False
            out.append(("C", value))
            pending = True
        elif inside and base == BLOCKS["Bengali"] and off == 0x4E:  # khanda ta: t, no vowel
            if pending:
                out.append(SCHWA)
            out.append(("C", "t"))
            pending = False
        elif inside and base == BLOCKS["Gurmukhi"] and off == 0x71:
            if pending:
                out.append(SCHWA)
                pending = False
            geminate = True
        elif inside and off == NUKTA and out and out[-1] is not SCHWA:
            kind, val = out[-1]
            out[-1] = (kind, NUKTA_FORMS.get(val, val))
        elif inside and off in SIGNS:
            out.append(("V", SIGNS[off]))
            pending = False
        elif inside and off == VIRAMA:
            pending = False
        else:
            if pending:
                out.append(SCHWA)
                pending = False
            if inside and off in VOWELS:
                out.append(("V", over.get(off, VOWELS[off])))
            elif inside and off in MARKS:
                out.append(("N" if MARKS[off] in ("m̐", "ṁ") else "X", MARKS[off]))
            elif inside and off in DIGITS:
                out.append(("X", str(off - 0x66)))
            elif not inside:
                out.append(("X", ch))
    if pending:
        out.append(SCHWA)
    return out


def _delete_schwas(tokens: list) -> list:
    """Drop the word-final inherent vowel, then medial ones in V C _ C V, right to left
    (so that of two candidate schwas only the later one goes: samajhnā, not samjhnā)."""

    def vowelish(tok) -> bool:  # a nasal mark belongs to the vowel before it
        return tok is SCHWA or tok[0] in ("V", "N")

    def consonant(tok) -> bool:
        return tok is not SCHWA and tok[0] == "C"

    out = list(tokens)
    if len(out) > 2 and out[-1] is SCHWA:
        out.pop()
    i = len(out) - 3
    while i >= 2:
        if (
            out[i] is SCHWA
            and consonant(out[i - 1])
            and vowelish(out[i - 2])
            and consonant(out[i + 1])
            and vowelish(out[i + 2])
        ):
            del out[i]
        i -= 1
    return out


def _render(tokens: list, nasal: str = "consonant") -> str:
    """Candrabindu as a tilde on its vowel and anusvara as the homorganic nasal before a
    consonant, the convention of the scholarly sources (dā̃t, dant)."""
    out = []
    for i, tok in enumerate(tokens):
        if tok is SCHWA:
            out.append("a")
            continue
        kind, val = tok
        if kind == "N" and val == "m̐" or kind == "N" and val == "ṁ" and nasal == "vowel":
            out.append("\u0303")
        elif kind == "N" and val == "ṁ":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            out.append(
                _homorganic(nxt[1])
                if nxt is not None and nxt is not SCHWA and nxt[0] == "C"
                else "ṁ"
            )
        else:
            out.append(val)
    return "".join(out)


def _homorganic(consonant: str) -> str:
    first = consonant[:1]
    if first in "kgṅ":
        return "ṅ"
    if first in "cjñ":
        return "ñ"
    if first in "ṭḍṇ":
        return "ṇ"
    if first in "pbm":
        return "m"
    return "n"


ISO15924 = {
    "Devanagari": "Deva",
    "Bengali": "Beng",
    "Gurmukhi": "Guru",
    "Gujarati": "Gujr",
    "Oriya": "Orya",
    "Tamil": "Taml",
    "Telugu": "Telu",
    "Kannada": "Knda",
    "Malayalam": "Mlym",
}


def romanize_variants(text: str) -> list[str]:
    """Plausible romanisations of a native-script word, most likely first.

    Varies the two choices the script leaves open: whether inherent vowels are pronounced
    (Sanskrit keeps them, Hindi drops some) and whether anusvara is a nasal consonant or a
    nasalised vowel (dant vs dā̃t).
    """
    script = script_of(text)
    if not script:
        return []
    deleting = script in SCHWA_DELETING
    out: list[str] = []
    for drop in (True, False) if deleting else (False,):
        for nasal in ("consonant", "vowel"):
            r = _romanize(text, drop, nasal)
            if r and r not in out:
                out.append(r)
    return out


# Languages that do not pronounce some inherent vowels (by language, not script: Sanskrit
# in Devanagari keeps them).
SCHWA_DELETING_LANGUAGES = {"hin", "mar", "ben", "asm", "pan", "guj"}


def native_search_key_source(text: str, language_id: str | None) -> str | None:
    """Romanisation used to key a native-script record for loose search."""
    if not script_of(text):
        return None
    drop = language_id in SCHWA_DELETING_LANGUAGES if language_id else None
    return romanize(text, drop_schwa=drop)
