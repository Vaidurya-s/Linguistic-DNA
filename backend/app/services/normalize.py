"""Search normalisation. The raw form is always kept; this only builds a separate search key."""

import html
import re
import unicodedata

from app.models.enums import FormKind

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


def form_kind(raw: str, is_compound: bool = False) -> FormKind:
    """Classify a form so stems, affixes, roots and phrases are never exact word matches."""
    form = normalize_form(raw).lstrip("*")
    if form.startswith("√"):
        return FormKind.root
    if form.startswith("-") or form.startswith("°"):
        return FormKind.affix
    if form.endswith("-"):
        return FormKind.stem
    if " " in form:
        return FormKind.phrase
    return FormKind.compound if is_compound else FormKind.word


def lexeme_search_key(form: str, language_id: str | None) -> str:
    """Loose key for a stored record. Forms written in a native script are keyed by their
    romanisation, so romanised queries can find them (e.g. 'angara' -> अंगारा)."""
    from app.services.transliterate import native_search_key_source  # avoids an import cycle

    romanised = native_search_key_source(form, language_id)
    return search_key(romanised) if romanised else search_key(form)


# --- Cleaning of source text before it is stored -------------------------------------------
# normalize_form (above) feeds deterministic ids and is never changed. These helpers clean what
# is *displayed*: markup left over from a source's own format, entity escapes, invisible junk.

_ANY_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
# Only real HTML tags are removed from a form: linguists write infixes as l<əm>idiʔ and
# proto-forms as <PIH *a->, which must survive.
_HTML_TAG = re.compile(
    r"</?(?:i|b|u|em|strong|sup|sub|small|smallcaps|big|nowiki|ref|br|span|s|code)\b[^<>]*>",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_WIKILINK = re.compile(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]*)\]\]")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
# U+FFFD, zero width space, word joiner, byte order mark. U+200C and U+200D are kept: they
# change how Indic and Persian words are written.
_INVISIBLE = re.compile(r"[\ufffd\u200b\u2060\ufeff]")


def _unescape(text: str) -> str:
    """HTML entities, also when a source escaped them twice (&amp;lt; -> <)."""
    for _ in range(3):
        out = html.unescape(text)
        if out == text:
            break
        text = out
    return text


def plain_text(text: str | None) -> str:
    """A gloss or definition as plain text: markup, wiki links, templates and entities removed,
    whitespace collapsed."""
    if not text:
        return ""
    text = _COMMENT.sub("", _unescape(text))
    text = _WIKILINK.sub(r"\1", text)
    text = _TEMPLATE.sub("", text)
    text = _ANY_TAG.sub("", text)
    return _SPACE.sub(" ", _CONTROL.sub("", _INVISIBLE.sub("", text))).strip()


def clean_form(raw: str) -> str:
    """A word as stored: entities and HTML tags from the source's format removed, invisible and
    control characters dropped, whitespace collapsed. Infix and affix notation is kept."""
    text = _COMMENT.sub("", _unescape(raw))
    text = _WIKILINK.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    return _SPACE.sub(" ", _CONTROL.sub("", _INVISIBLE.sub("", text))).strip()


def is_placeholder_form(form: str) -> bool:
    """True when nothing letter-like is left: a lone dash, question mark, bracket or combining
    mark is the source's way of saying "no form", not a word."""
    # Private-use characters count: scripts such as Klingon pIqaD live there and have no letter
    # category, but they are real writing.
    return not any(ch.isalnum() or unicodedata.category(ch) == "Co" for ch in clean_form(form))
