"""Sound-class skeleton keys for blocking cognate candidates.

A cognate search over 14 million words cannot compare a query with every word. A *blocking key*
puts words that might be related into one bucket so that only the bucket is compared. The key
here is a short sound-class skeleton, in the spirit of SCA sound classes (List 2012): spelling is
read as sounds by rule, voicing and aspiration are ignored, places of articulation are kept, the
consonants form the skeleton, and the first vowel is kept in three classes.

    skey = <consonant classes in order, repeats merged, at most MAX_CONS> ':' <first vowel class>

    pater, father   ->  PTR:a        (p, f -> P; t, th -> T; the Grimm's-law pair shares a key)
    Wasser, water   ->  WSR:a / WTR:a   (not the same key: s and t differ; found by relaxed level)

Three blocking levels, from strict to loose (`block` / `LEVELS`):
    1 exact   same skeleton and same first-vowel class
    2 cons    same skeleton, any vowel          (skey LIKE 'PTR:%')
    3 prefix  same first PREFIX_CONS consonants (skey LIKE 'PT%')

The class table is fixed here (not tuned on any gold pair). Everything is computed, never
documented: a block member is only a candidate, to be scored (layers/candidate.py) and shown as
computed.

Built only for lexemes of enabled languages, in streaming batches: `python -m app.cli
build-sound-key`.
"""

from __future__ import annotations

import time
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

SQL_FILE = Path(__file__).with_name("sound_key.sql")
RULES_VERSION = "skey-1"
MAX_CONS = 6
PREFIX_CONS = 2
LEVELS = ("exact", "cons", "prefix")

# --- class table -------------------------------------------------------------------------------
# letter or IPA symbol -> consonant class, or a vowel class (lower case a, e, o).

_C: dict[str, str] = {}


def _reg(cls: str, chars: str) -> None:
    for ch in chars:
        _C[ch] = cls


_reg("P", "pbfɸ")  # labial obstruents: p/b/f merge (Grimm's law, Armenian, Celtic p-loss)
_reg("W", "wvβʋ")  # labial glides and v
_reg("T", "tdθðþʈɖđ")  # dental and alveolar stops and dental fricatives
_reg("K", "kgqxɣχɡhɦ")  # velars, uvulars, h
_reg("S", "szʃʒɕʑʂʐśṣšžç")  # sibilants and sibilant-like affricates read as sibilants
_reg("C", "ʧʤʦʣʨʥčćǆ")  # affricates (merged with S at the digraph step: see _AFFRICATE_AS_S)
_reg("M", "m")
_reg("N", "nŋɲɳɴñṇ")
_reg("L", "lɫɭʎɬɮʟł")
_reg("R", "rɾɹɻʀʁɽ")
_reg("J", "jʝ")
_reg("a", "aɑɐäæåə")  # open and central vowels, schwa
_reg("e", "eɛiɪyɨøœ")  # front vowels
_reg("o", "oɔuʊʉɯ")  # back and rounded vowels
VOWEL_CLASSES = frozenset("aeo")
_AFFRICATE_AS_S = True
if _AFFRICATE_AS_S:
    for _k, _v in list(_C.items()):
        if _v == "C":
            _C[_k] = "S"
# Cyrillic and Greek letters, read as sounds (marks are stripped before this lookup).
_C.update(
    {
        **{c: "a" for c in "аαя"},
        **{c: "e" for c in "еэиіыηιεє"},
        **{c: "o" for c in "оуюωου"},
        "б": "P", "п": "P", "ф": "P", "β": "W", "π": "P", "φ": "P", "в": "W",
        "д": "T", "т": "T", "δ": "T", "θ": "T", "τ": "T",
        "г": "K", "к": "K", "х": "K", "γ": "K", "κ": "K", "χ": "K", "ґ": "K",
        "з": "S", "с": "S", "ж": "S", "ш": "S", "щ": "S", "ц": "S", "ч": "S",
        "ζ": "S", "σ": "S", "ς": "S", "ψ": "P", "ξ": "K",
        "м": "M", "μ": "M", "н": "N", "ν": "N", "л": "L", "λ": "L", "р": "R", "ρ": "R", "й": "J",
        "ь": "", "ъ": "",
    }
)  # fmt: skip

# Digraphs read as one sound, longest first (applied to the lower-case Latin string).
_DIGRAPHS = (
    ("tsch", "S"), ("tch", "S"), ("dzh", "S"), ("sch", "S"), ("sh", "S"), ("zh", "S"),
    ("ch", "K"), ("th", "T"), ("ph", "P"), ("kh", "K"), ("gh", "K"), ("bh", "P"), ("dh", "T"),
    ("ts", "S"), ("dz", "S"), ("ck", "K"), ("qu", "KW"), ("ng", "N"),
)  # fmt: skip
# Letters with a context rule or two sounds.
_X = "KS"
_SOFT = "eiyéèêíîýæœ"  # c before these is read as a sibilant (Romance, Slavic)


def _fold_marks(text: str) -> str:
    """Case-fold and drop everything but letters: reconstruction stars, hyphens, brackets,
    digits and combining marks go (the letters whose mark changes the sound, such as c with caron
    or s with acute, are in the class table as precomposed letters and kept whole)."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", text.casefold()):
        if ch in _C or ch in "xqcyjhw":
            out.append(ch)
            continue
        base = unicodedata.normalize("NFD", ch)[0]
        if unicodedata.category(base)[0] == "L":
            out.append(base)
    return "".join(out)


def classes(text: str) -> str:
    """The sound-class string of a spelling: consonant classes in upper case, vowels a, e, o."""
    s = _fold_marks(text or "")
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        matched = False
        for dg, cls in _DIGRAPHS:
            if s.startswith(dg, i):
                out.append(cls)
                i += len(dg)
                matched = True
                break
        if matched:
            continue
        ch = s[i]
        i += 1
        if ch == "x":
            out.append(_X)
        elif ch == "c":
            nxt = s[i] if i < n else ""
            out.append("S" if nxt in _SOFT else "K")
        elif ch == "y":
            prev_v = bool(out) and out[-1] in VOWEL_CLASSES
            nxt_v = i < n and _C.get(s[i], "") in VOWEL_CLASSES
            out.append("J" if (not out and nxt_v) or (prev_v and nxt_v) else "e")
        else:
            out.append(_C.get(ch, ""))
    return "".join(out)


def skeleton(text: str) -> tuple[str, str]:
    """(consonant skeleton, first-vowel class or '_') of a spelling. A doubled sound counts once."""
    cons: list[str] = []
    vowel = "_"
    prev = ""
    for c in classes(text):
        if c in VOWEL_CLASSES:
            if vowel == "_":
                vowel = c
        elif c != prev:  # a doubled sound counts once; the same sound after a vowel counts
            cons.append(c)
        prev = c
    return "".join(cons[:MAX_CONS]), vowel


def _source_text(form: str, transliteration: str | None, search_key: str | None) -> str:
    """The Latin-letter text to read as sounds: the source's own romanisation when it has one,
    else the form itself when it is in Latin, Cyrillic or Greek letters, else the project's search
    key (the rule-based romanisation of the Indic scripts), else nothing."""
    if transliteration and transliteration.strip():
        return transliteration
    for ch in form:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            first = name.split(" ", 1)[0]
            if first in ("LATIN", "CYRILLIC", "GREEK", "MODIFIER"):
                return form
            break
    if search_key and all(ord(c) < 0x250 for c in search_key):
        return search_key
    return ""


def skey(
    form: str, transliteration: str | None = None, search_key: str | None = None
) -> str | None:
    """The blocking key of a word, or None when its text has no consonant."""
    cons, vowel = skeleton(_source_text(form, transliteration, search_key))
    return f"{cons}:{vowel}" if cons else None


def level_pattern(key: str, level: str) -> tuple[str, bool]:
    """(value, is_prefix) for a blocking level: exact key, same consonants, or same prefix."""
    cons, _, _ = key.partition(":")
    if level == "exact":
        return key, False
    if level == "cons":
        return cons + ":", True
    if level == "prefix":
        return cons[:PREFIX_CONS], True
    raise ValueError(f"level must be one of {LEVELS}")


# --- database ----------------------------------------------------------------------------------


def ensure_schema(conn) -> None:
    """Create the sound-key tables if they do not exist (idempotent)."""
    conn.execute(SQL_FILE.read_text(encoding="utf-8"))


def enabled_languages(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT id FROM language WHERE is_enabled ORDER BY id")]


def build_language(conn, language_id: str, batch: int = 100_000) -> dict:
    """Replace the keys of one language (delete, then insert), streaming in batches with a
    server-side cursor; one transaction per language."""
    conn.execute("DELETE FROM layers.sound_key WHERE language_id = %s", (language_id,))
    n = keyed = 0
    with conn.cursor(name="sk_reader") as reader:
        reader.execute(
            "SELECT id, form, transliteration, search_key FROM lexeme WHERE language_id = %s",
            (language_id,),
        )
        while True:
            chunk = reader.fetchmany(batch)
            if not chunk:
                break
            n += len(chunk)
            rows = []
            for lex_id, form, tr, sk in chunk:
                key = skey(form, tr, sk)
                if key:
                    rows.append((lex_id, language_id, key))
            keyed += len(rows)
            with (
                conn.cursor() as cur,
                cur.copy("COPY layers.sound_key (lexeme_id, language_id, skey) FROM STDIN") as cp,
            ):
                for row in rows:
                    cp.write_row(row)
    conn.execute(
        "INSERT INTO layers.sound_key_build (language_id, rules_version, lexemes, keyed)"
        " VALUES (%s, %s, %s, %s) ON CONFLICT (language_id) DO UPDATE SET"
        " rules_version = EXCLUDED.rules_version, lexemes = EXCLUDED.lexemes,"
        " keyed = EXCLUDED.keyed, built_at = now()",
        (language_id, RULES_VERSION, n, keyed),
    )
    conn.commit()
    return {"language_id": language_id, "lexemes": n, "keyed": keyed}


def build(conn, languages: Iterable[str] | None = None, log=print) -> dict:
    """Build the keys for `languages` (default: every enabled language). A full build drops the
    two indexes first and recreates them at the end, which is much faster than maintaining them
    through 13 million inserts."""
    ensure_schema(conn)
    conn.commit()
    full = languages is None
    langs = list(languages) if languages is not None else enabled_languages(conn)
    if full:
        conn.execute("DROP INDEX IF EXISTS layers.ix_sound_key_skey")
        conn.execute("DROP INDEX IF EXISTS layers.ix_sound_key_lang_skey")
        conn.commit()
    t0 = time.time()
    total = {"languages": 0, "lexemes": 0, "keyed": 0}
    for i, lang in enumerate(langs, 1):
        t1 = time.time()
        res = build_language(conn, lang)
        total["languages"] += 1
        total["lexemes"] += res["lexemes"]
        total["keyed"] += res["keyed"]
        if res["lexemes"] >= 100_000 or i % 200 == 0 or i == len(langs):
            log(
                f"{time.strftime('%H:%M:%S')} {i}/{len(langs)} {lang} lexemes={res['lexemes']} "
                f"keyed={res['keyed']} {time.time() - t1:.1f}s (total {time.time() - t0:.0f}s,"
                f" rows {total['keyed']})"
            )
    if full:
        log("creating indexes ...")
        ensure_schema(conn)
        conn.commit()
        conn.execute("ANALYZE layers.sound_key")
        conn.commit()
    total["seconds"] = round(time.time() - t0)
    return total


def block(
    conn,
    key: str,
    level: str = "exact",
    language_ids: Sequence[str] | None = None,
    exclude_language: str | None = None,
    exclude_datasets: Sequence[str] = (),
    datasets: Sequence[str] | None = None,
    limit: int = 2000,
) -> list[str]:
    """Lexeme ids in the key's bucket at a blocking level, optionally restricted to languages
    and datasets. The bucket is cut at `limit` (ordered by id, so the cut is deterministic);
    callers that need to know compare the length with `limit`."""
    value, is_prefix = level_pattern(key, level)
    sql = ["SELECT s.lexeme_id FROM layers.sound_key s"]
    args: dict = {"v": value, "limit": limit}
    needs_lexeme = bool(exclude_datasets) or datasets is not None
    if needs_lexeme:
        sql.append("JOIN lexeme l ON l.id = s.lexeme_id")
    sql.append("WHERE " + ("s.skey LIKE %(v)s || '%%'" if is_prefix else "s.skey = %(v)s"))
    if language_ids is not None:
        sql.append("AND s.language_id = ANY(%(langs)s)")
        args["langs"] = list(language_ids)
    if exclude_language:
        sql.append("AND s.language_id <> %(xl)s")
        args["xl"] = exclude_language
    if exclude_datasets:
        sql.append("AND l.dataset <> ALL(%(xd)s)")
        args["xd"] = list(exclude_datasets)
    if datasets is not None:
        sql.append("AND l.dataset = ANY(%(ds)s)")
        args["ds"] = list(datasets)
    sql.append("ORDER BY s.lexeme_id LIMIT %(limit)s")
    return [r[0] for r in conn.execute(" ".join(sql), args).fetchall()]
