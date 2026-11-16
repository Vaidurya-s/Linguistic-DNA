"""Word-identity keys: the same word written in another script or spelling.

The database keys a word by (language, normalized_form). Many sources write a word in its own script
(Cyrillic, Devanagari, Greek, ...) while others, IE-CoR for one, write it in Latin letters, so the
same word gets two identities. This module adds deterministic keys, by rule and never by fuzzy
matching, so that a caller can still tell HOW two spellings were matched.

Key kinds (a lexeme has at most one key of each kind; only keys that differ from `native` are
stored):

native    lexeme.normalized_form, the identity the database already uses. Not stored again.
fold      fold_key(normalized_form), see below.
translit  fold_key of the lexeme's romanisation, for words NOT written in Latin letters only. The
          romanisation is the source's own `transliteration` column when there is one, else
          `services.transliterate.romanize` for the Indic scripts it supports (the schwa rule by
          language, as the project's search does). Words in a script with neither stay without a
          translit key. For Latin-script words the translit key would equal the fold key, so it is
          not stored.

fold_key(text) rules, applied in this order (rules_version FOLD_RULES):
  1. case-fold (so also ß -> ss, final sigma -> sigma);
  2. NFKD decomposition (ä -> a + diaeresis, ʰ -> h, ʷ -> w, fullwidth and ligature forms);
  3. drop combining marks after a Latin, Greek, Arabic or Hebrew letter (diacritics, tone and
     breathing marks, Arabic harakat, niqqud); after a Cyrillic letter only the stress marks
     U+0300 and U+0301 are dropped, so й, ё and ї stay distinct from и, е and і; marks of every
     other script (Indic vowel signs, viramas, Armenian, ...) are kept because they carry vowels;
  4. drop every character that is not a letter, digit or mark: hyphens, apostrophes, spaces,
     dots, brackets, reconstruction stars and the like; the apostrophe-like modifier letters
     ʼ ʻ ʹ ʽ and the stress marks ˈ ˌ are dropped too (ʔ ʾ ʿ are consonants and stay);
  5. the stroke letters that do not decompose: ø -> o, đ -> d, ł -> l, ħ -> h, ı -> i;
  6. NFC.
Nothing else is folded: æ, œ, þ, ð, ŋ, ə keep their identity, and no letters are merged across
scripts.

Matching is always inside one language: resolve_form never returns a lexeme of another language.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path

import psycopg

from app.layers.romanise import rule_key, rule_query_keys
from app.services.normalize import normalize_form
from app.services.transliterate import SCHWA_DELETING_LANGUAGES, romanize, script_of

KINDS = ("native", "fold", "translit")
RULE_KIND = "translit_rule"  # table-driven romanisation (layers/romanise.py); not part of KINDS
ALL_KINDS = KINDS + (RULE_KIND,)
FOLD_RULES = "fold-1"
RULES_VERSION = "keys-1/" + FOLD_RULES
SQL_FILE = Path(__file__).with_name("keys.sql")

_STRIP_ALL_MARKS = {"LATIN", "GREEK", "ARABIC", "HEBREW"}
_CYRILLIC_STRESS = {"̀", "́"}
_DROP_LETTERS = set("ʼʻʹʽˈˌ")
_STROKE = str.maketrans({"ø": "o", "đ": "d", "ł": "l", "ħ": "h", "ı": "i"})


@lru_cache(maxsize=4096)
def _script_name(ch: str) -> str:
    name = unicodedata.name(ch, "")
    return name.split(" ", 1)[0] if name else ""


def fold_key(text: str) -> str:
    """Spelling-insensitive key of a word (rules in the module docstring)."""
    out: list[str] = []
    base = ""  # script of the last kept base letter
    for ch in unicodedata.normalize("NFKD", normalize_form(text).casefold()):
        cat = unicodedata.category(ch)
        if cat[0] == "M":
            if base in _STRIP_ALL_MARKS or (base == "CYRILLIC" and ch in _CYRILLIC_STRESS):
                continue
            out.append(ch)
        elif cat[0] in "LN" and ch not in _DROP_LETTERS:
            out.append(ch)
            base = _script_name(ch)
        # everything else (punctuation, symbols, separators, controls) is dropped
    return unicodedata.normalize("NFC", "".join(out).translate(_STROKE))


def is_latin_script(text: str) -> bool:
    """True when every letter of the text is a Latin letter (or a modifier letter); empty or
    letterless text counts as Latin."""
    for ch in text:
        if ch.isalpha() and unicodedata.category(ch) != "Lm" and _script_name(ch) != "LATIN":
            return False
    return True


def romanisation(
    normalized_form: str, transliteration: str | None, language_id: str | None
) -> str | None:
    """The romanisation a translit key is built from: the source's own, else the project's rules
    for Indic scripts, else None."""
    if transliteration and transliteration.strip():
        return transliteration
    if script_of(normalized_form):
        drop = language_id in SCHWA_DELETING_LANGUAGES if language_id else None
        return romanize(normalized_form, drop_schwa=drop)
    return None


def lexeme_keys(
    normalized_form: str,
    transliteration: str | None = None,
    language_id: str | None = None,
    rule: bool = False,
) -> dict[str, str]:
    """The stored keys of one lexeme: {kind: key} for the kinds that differ from native. The
    table-driven `translit_rule` key is only produced with rule=True (see romanise.py)."""
    keys: dict[str, str] = {}
    fold = fold_key(normalized_form)
    if fold and fold != normalized_form:
        keys["fold"] = fold
    if not is_latin_script(normalized_form):
        roman = romanisation(normalized_form, transliteration, language_id)
        tl = fold_key(roman) if roman else ""
        if tl and tl != normalized_form:
            keys["translit"] = tl
    if rule:
        rk = rule_key(normalized_form, language_id)
        if rk and rk != normalized_form:
            keys[RULE_KIND] = rk
    return keys


def query_keys(form: str, language_id: str | None = None) -> dict:
    """The keys of a query form. `translit` is the key of its romanisation when the form is in a
    script the project can romanise, else the fold key (a Latin query is its own romanisation)."""
    native = normalize_form(form)
    fold = fold_key(form)
    translit = fold
    if not is_latin_script(native) and script_of(native):
        roman = romanisation(native, None, language_id)
        translit = fold_key(roman) if roman else None
    elif not is_latin_script(native):
        translit = None
    return {
        "native": native,
        "fold": fold,
        "translit": translit,
        RULE_KIND: rule_query_keys(form, language_id),
    }


# --- schema and build ---------------------------------------------------------------------------


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(SQL_FILE.read_text(encoding="utf-8"))


def target_languages(conn: psycopg.Connection) -> list[str]:
    """Enabled languages plus the languages of the gold datasets (IE-CoR, WOLD, DunniLex)."""
    rows = conn.execute(
        """
        SELECT id FROM language WHERE is_enabled
        UNION
        SELECT DISTINCT language_id FROM lexeme WHERE dataset IN ('iecor', 'wold', 'dunnielex')
        ORDER BY 1
        """
    ).fetchall()
    return [r[0] for r in rows]


def build_language(conn: psycopg.Connection, language_id: str, batch: int = 100_000) -> dict:
    """Replace the keys of one language (delete, then insert), streaming in batches: a server-side
    cursor reads `batch` lexemes, their keys are written with COPY, then the next batch is read
    (a read and a COPY never run at the same time on one connection). One transaction per
    language."""
    n = 0
    conn.execute("DELETE FROM layers.word_key WHERE language_id = %s", (language_id,))
    counts = {"fold": 0, "translit": 0}
    with conn.cursor(name="wk_reader") as reader:
        reader.execute(
            "SELECT id, normalized_form, transliteration FROM lexeme WHERE language_id = %s",
            (language_id,),
        )
        while True:
            chunk = reader.fetchmany(batch)
            if not chunk:
                break
            n += len(chunk)
            rows = []
            for lex_id, nf, tr in chunk:
                for kind, key in lexeme_keys(nf, tr, language_id).items():
                    rows.append((lex_id, language_id, kind, key))
                    counts[kind] += 1
            with (
                conn.cursor() as cur,
                cur.copy(
                    "COPY layers.word_key (lexeme_id, language_id, key_kind, key) FROM STDIN"
                ) as copy,
            ):
                for row in rows:
                    copy.write_row(row)
    conn.execute(
        """
        INSERT INTO layers.word_key_build
            (language_id, rules_version, lexemes, fold_rows, translit_rows)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (language_id) DO UPDATE SET rules_version = EXCLUDED.rules_version,
            lexemes = EXCLUDED.lexemes, fold_rows = EXCLUDED.fold_rows,
            translit_rows = EXCLUDED.translit_rows, built_at = now()
        """,
        (language_id, RULES_VERSION, n, counts["fold"], counts["translit"]),
    )
    conn.commit()
    return {"language_id": language_id, "lexemes": n, **counts}


def build_rule_language(conn: psycopg.Connection, language_id: str, batch: int = 100_000) -> dict:
    """Replace only the `translit_rule` keys of one language (the other kinds are untouched)."""
    conn.execute(
        "DELETE FROM layers.word_key WHERE language_id = %s AND key_kind = %s",
        (language_id, RULE_KIND),
    )
    n = 0
    with conn.cursor(name="wk_rule_reader") as reader:
        reader.execute(
            "SELECT id, normalized_form FROM lexeme WHERE language_id = %s", (language_id,)
        )
        while True:
            chunk = reader.fetchmany(batch)
            if not chunk:
                break
            rows = []
            for lex_id, nf in chunk:
                rk = rule_key(nf, language_id)
                if rk and rk != nf:
                    rows.append((lex_id, language_id, RULE_KIND, rk))
            n += len(rows)
            with (
                conn.cursor() as cur,
                cur.copy(
                    "COPY layers.word_key (lexeme_id, language_id, key_kind, key) FROM STDIN"
                ) as copy,
            ):
                for row in rows:
                    copy.write_row(row)
    conn.execute(
        "UPDATE layers.word_key_build SET rule_rows = %s WHERE language_id = %s", (n, language_id)
    )
    conn.commit()
    return {"language_id": language_id, "translit_rule": n}


_RULE_SCRIPT_RANGES = (
    "\u0370-\u03ff\u1f00-\u1fff"  # Greek, polytonic Greek
    "\u0400-\u052f"  # Cyrillic
    "\u0530-\u058f"  # Armenian
    "\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff"  # Arabic script
)


def rule_languages(conn: psycopg.Connection) -> list[str]:
    """Languages that have at least one word in a script romanise.py covers."""
    rows = conn.execute(
        "SELECT DISTINCT language_id FROM lexeme WHERE normalized_form ~ %s ORDER BY 1",
        ("[" + _RULE_SCRIPT_RANGES + "]",),
    ).fetchall()
    return [r[0] for r in rows]


def build(
    conn: psycopg.Connection, languages: Iterable[str] | None = None, log=print
) -> dict[str, int]:
    """Build the keys for `languages` (default: target_languages), language by language."""
    import time

    ensure_schema(conn)
    conn.commit()
    langs = list(languages) if languages is not None else target_languages(conn)
    t0 = time.time()
    total = {"languages": 0, "lexemes": 0, "fold": 0, "translit": 0}
    for i, lang in enumerate(langs, 1):
        t1 = time.time()
        res = build_language(conn, lang)
        total["languages"] += 1
        for k in ("lexemes", "fold", "translit"):
            total[k] += res[k]
        if res["lexemes"] >= 100_000 or i % 100 == 0 or i == len(langs):
            log(
                f"{time.strftime('%H:%M:%S')} {i}/{len(langs)} {lang} lexemes={res['lexemes']} "
                f"fold={res['fold']} translit={res['translit']} {time.time() - t1:.1f}s "
                f"(total {time.time() - t0:.0f}s, rows {total['fold'] + total['translit']})"
            )
    total["seconds"] = round(time.time() - t0)
    return total


# --- lookup ---------------------------------------------------------------------------------------


def resolve_form(
    conn: psycopg.Connection,
    language_id: str,
    form: str,
    kinds: Sequence[str] = KINDS,
    exclude_datasets: Sequence[str] = (),
) -> list[tuple[str, str]]:
    """Lexemes of one language that spell `form` the same way, as [(lexeme_id, kind)].

    Exact native matches come first, then fold matches, then translit matches; a lexeme is listed
    once, under the first kind that found it, so the caller keeps the evidence of how the word was
    matched. Order inside a kind is by lexeme id. `exclude_datasets` drops lexemes of those
    datasets (used to hold out a gold dataset).
    """
    q = query_keys(form, language_id)
    found: dict[str, str] = {}

    def add(kind: str, ids: Iterable[str]) -> None:
        for lex_id in sorted(ids):
            found.setdefault(lex_id, kind)

    ex = list(exclude_datasets)
    ds_filter = " AND l.dataset <> ALL(%(ex)s)" if ex else ""
    p = {"lang": language_id, "ex": ex}

    def by_form(value: str) -> list[str]:
        sql = (
            "SELECT l.id FROM lexeme l WHERE l.language_id = %(lang)s AND l.normalized_form = %(v)s"
            + ds_filter
        )
        return [r[0] for r in conn.execute(sql, {**p, "v": value}).fetchall()]

    def by_key(kind: str, value: str) -> list[str]:
        sql = (
            "SELECT k.lexeme_id FROM layers.word_key k JOIN lexeme l ON l.id = k.lexeme_id"
            " WHERE k.language_id = %(lang)s AND k.key_kind = %(kind)s AND k.key = %(v)s"
            + ds_filter
        )
        return [r[0] for r in conn.execute(sql, {**p, "kind": kind, "v": value}).fetchall()]

    if "native" in kinds and q["native"]:
        add("native", by_form(q["native"]))
    if "fold" in kinds and q["fold"]:
        # a lexeme whose own fold key equals its spelling is not stored: it is the native lookup
        # of the folded query
        add("fold", by_form(q["fold"]) + by_key("fold", q["fold"]))
    if "translit" in kinds and q["translit"]:
        ids = by_key("translit", q["translit"])
        if q["translit"] != q["fold"]:
            # the query was romanised: Latin-script words spelled like its romanisation match too
            ids += by_form(q["translit"]) + by_key("fold", q["translit"])
        add("translit", ids)
    if RULE_KIND in kinds:
        ids = []
        for key in q[RULE_KIND]:
            ids += by_key(RULE_KIND, key)
            if not is_latin_script(q["native"]) and not key.startswith("sk:"):
                # a covered-script query was romanised: Latin-script words spelled like it match too
                ids += by_form(key) + by_key("fold", key)
        add(RULE_KIND, ids)
    # exact matches first, then the kinds in the order given by ALL_KINDS
    order = {k: i for i, k in enumerate(ALL_KINDS)}
    return sorted(found.items(), key=lambda kv: (order[kv[1]], kv[0]))
