"""Candidate layer: same-meaning words of other languages, ranked by sound-aware similarity.

A candidate is COMPUTED, not documented. It has no citation: only a method name, its parameters, a
score, the gate that made the two words comparable, and a precision calibrated on held-out expert
cognate judgements (layers.candidate_calibration). It is never written to `relationship`.

Scoring (pure Python, no external alignment library):
  * `lev`     normalised Levenshtein similarity on case- and diacritic-folded text.
  * `sca`     weighted alignment of two words reduced to sound classes (an SCA-like model, class
              table below: voicing is ignored, related classes substitute at a reduced cost).
  * `sca_c`   the same on the consonant skeleton (vowels removed), which tolerates the large
              vowel changes between old related languages.
  * `blend`   mean of the three.
The class table, the substitution costs and the gap costs are fixed a priori and were not tuned on
any gold pair. Which method is the default was chosen on the DEV half (see DEFAULT_METHOD).

Gates (what makes two words comparable):
  * `concept` the two words are linked to a common concept (lexeme_concept).
  * `gloss`   a common concept, or the glosses share a content word (stop words and
              'form of' boilerplate removed). Needs layers.gloss_token (build_gloss_tokens).
  * `oracle`  only used in experiments, where the gold meaning is known; never offered by the API.

The functions take a psycopg connection.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SQL_FILE = Path(__file__).with_name("candidate.sql")
BIN_WIDTH = 0.05
CALIBRATION_FAMILY = "indo1319"  # the calibration was fitted on Indo-European words only
CALIBRATION_DOMAIN = "indo-european basic vocabulary"
GATES = ("gloss", "concept")
# highest DEV ROC-AUC of the four methods (see the benchmark report, not in the repository)
DEFAULT_METHOD = "blend"
POOL_CAP = 4000  # most candidate words scored per query
RANK_PREFILTER = True


def ensure_schema(conn) -> None:
    """Create the layer tables if they do not exist (idempotent)."""
    conn.execute(SQL_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------
# sound classes (SCA-like)
# --------------------------------------------------------------------------------------------

# Precomposed letters whose mark would change the class if it were simply stripped.
_PRE = {
    "č": "ʧ", "ć": "ʧ", "š": "ʃ", "ž": "ʒ", "ś": "ʃ", "ṣ": "ʃ", "ç": "s", "ß": "s", "ł": "l",
    "đ": "ð", "þ": "θ", "æ": "a", "œ": "o", "ǆ": "ʤ", "й": "j", "ё": "jo",
}  # fmt: skip

# Letters of other scripts, turned into Latin/IPA letters (after marks are stripped).
_TRANSLIT = {
    **{c: "a" for c in "αа"},
    **{c: "e" for c in "εηеэ"},
    **{c: "i" for c in "ιиі"},
    **{c: "o" for c in "οωо"},
    **{c: "u" for c in "υу"},
    "β": "b", "γ": "g", "δ": "ð", "ζ": "z", "θ": "θ", "κ": "k", "λ": "l", "μ": "m", "ν": "n",
    "ξ": "ks", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "φ": "f", "χ": "x", "ψ": "ps",
    "б": "b", "в": "v", "г": "g", "д": "d", "з": "z", "к": "k", "л": "l", "м": "m", "н": "n",
    "п": "p", "р": "r", "с": "s", "т": "t", "ф": "f", "х": "x", "ц": "ʦ", "ч": "ʧ", "ш": "ʃ",
    "щ": "ʃ", "ж": "ʒ", "ы": "ɨ", "я": "ja", "ю": "ju", "ь": "", "ъ": "",
}  # fmt: skip

# Multi-letter spellings read as one sound (applied to the folded string, longest first).
_DIGRAPHS = (
    ("tsch", "ʧ"), ("tch", "ʧ"), ("dzh", "ʤ"), ("sch", "ʃ"), ("sh", "ʃ"), ("zh", "ʒ"),
    ("ch", "x"), ("th", "θ"), ("kh", "x"), ("gh", "g"), ("bh", "b"), ("dh", "d"), ("ph", "p"),
    ("ts", "ʦ"), ("dz", "ʣ"), ("ck", "k"), ("qu", "kw"),
)  # fmt: skip

_CLASS: dict[str, str] = {}


def _reg(cls: str, chars: str) -> None:
    for ch in chars:
        _CLASS[ch] = cls


_reg("A", "aɑɐä")
_reg("E", "eɛəɘ")
_reg("I", "iɪɨı")
_reg("O", "oɔøœ")
_reg("U", "uʊʉɯ")
_reg("J", "jyʝ")  # glides; y is ambiguous (vowel or glide) and read as a glide
_reg("W", "wʍ")
_reg("P", "pb")
_reg("B", "fvɸβʋ")
_reg("M", "m")
_reg("N", "nŋɲɳɴ")
_reg("T", "tdʈɖ")
_reg("D", "θð")
_reg("S", "szʃʒɕʑʂʐ")
_reg("C", "ʧʤʦʣʨʥ")
_reg("K", "kgqcxɣχɡ")
_reg("H", "hɦħʕʔ")
_reg("L", "lɫɭʎɬɮʟ")
_reg("R", "rɾɹɻʀʁ")

VOWELS = frozenset("AEIOU")
CLASSES = frozenset(_CLASS.values())

_GAP = {c: 0.6 for c in "AEIOUHJW"}  # vowels, h and glides are cheap to lose; the rest cost 1
_SUB: dict[frozenset, float] = {}


def _sub(cost: float, *groups: str) -> None:
    for g in groups:
        for i, x in enumerate(g):
            for y in g[i + 1 :]:
                _SUB[frozenset((x, y))] = cost


_sub(0.5, "AEIOU")  # one vowel for another
_sub(0.3, "IJ", "UW")  # vowel and its glide
_sub(0.4, "BW", "TD", "SC")
_sub(0.5, "PB", "KH", "LR", "SD")
_sub(0.6, "MN", "TS", "TC", "KC")


def sub_cost(x: str, y: str) -> float:
    if x == y:
        return 0.0
    return _SUB.get(frozenset((x, y)), 1.0)


def fold(text: str) -> str:
    """Lower-case, no diacritics, letters and digits only (the folding the diagnosis used)."""
    s = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in s if not unicodedata.combining(c) and c.isalnum())


@lru_cache(maxsize=200_000)
def sound_classes(text: str) -> str:
    """Sound-class string of a word. Unknown letters stand for themselves, so two identical
    unknown letters still match; digits, marks and punctuation are dropped. Repeated classes
    (double consonants) are collapsed."""
    s = unicodedata.normalize("NFC", text.lower())
    s = "".join(_PRE.get(c, c) for c in s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(_TRANSLIT.get(c, c) for c in s)
    s = "".join(c for c in s if unicodedata.category(c)[0] == "L")
    for src, dst in _DIGRAPHS:
        s = s.replace(src, dst)
    out: list[str] = []
    for ch in s:
        cls = _CLASS.get(ch)
        if cls is None:
            if not ch.isalpha() or unicodedata.category(ch) == "Lm":
                continue
            cls = ch  # unknown letter
        if not out or out[-1] != cls:
            out.append(cls)
    return "".join(out)


def consonant_skeleton(classes: str) -> str:
    return "".join(c for c in classes if c not in VOWELS)


def _lev_sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1 - prev[-1] / max(len(a), len(b))


def _align_sim(a: str, b: str) -> float:
    """Global alignment of two class strings with class-dependent substitution and gap costs;
    similarity = 1 - distance / length of the longer string (0 when nothing is alike)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    gap = _GAP
    prev = [0.0]
    for cb in b:
        prev.append(prev[-1] + gap.get(cb, 1.0))
    for ca in a:
        ga = gap.get(ca, 1.0)
        cur = [prev[0] + ga]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(
                    prev[j] + ga,
                    cur[j - 1] + gap.get(cb, 1.0),
                    prev[j - 1] + sub_cost(ca, cb),
                )
            )
        prev = cur
    return max(0.0, 1 - prev[-1] / max(len(a), len(b)))


def score_lev(a: str, b: str) -> float:
    return _lev_sim(fold(a), fold(b))


def score_sca(a: str, b: str) -> float:
    return _align_sim(sound_classes(a), sound_classes(b))


def score_sca_c(a: str, b: str) -> float:
    ca, cb = sound_classes(a), sound_classes(b)
    sa, sb = consonant_skeleton(ca), consonant_skeleton(cb)
    if not sa or not sb:  # a word without consonants: fall back to the full classes
        return _align_sim(ca, cb)
    return _align_sim(sa, sb)


def score_blend(a: str, b: str) -> float:
    return (score_lev(a, b) + score_sca(a, b) + score_sca_c(a, b)) / 3


METHODS = {"lev": score_lev, "sca": score_sca, "sca_c": score_sca_c, "blend": score_blend}


def score(method: str, a: str, b: str) -> float:
    return METHODS[method](a, b)


def scoring_text(
    form: str, transliteration: str | None = None, search_key: str | None = None
) -> str:
    """The string a word is scored on: its transliteration if it has one; else the form when every
    letter is one the class table knows; else the romanised search key (native scripts)."""
    if transliteration and transliteration.strip():
        return transliteration
    s = unicodedata.normalize("NFD", form.lower())
    letters = [c for c in s if c.isalpha() and not unicodedata.combining(c)]
    known = all(c in _CLASS or c in _TRANSLIT or c in _PRE for c in letters)
    if not known and search_key:
        return search_key
    return form


# --------------------------------------------------------------------------------------------
# gloss gate
# --------------------------------------------------------------------------------------------

_FORM_OF = re.compile(
    r"^\s*(?:(?:an?\s+)?(?:obsolete|archaic|dated|rare|nonstandard|dialectal|uncommon|informal|"
    r"alternative|alternate|eye|pronunciation|misspelling|romanization|romanisation|"
    r"transliteration|clipping|abbreviation|initialism|acronym|inflection|plural|singular|"
    r"genitive|dative|accusative|nominative|locative|vocative|ablative|instrumental|"
    r"comparative|superlative|diminutive|augmentative|feminine|masculine|neuter|"
    r"past|present|future|passive|active|participle|gerund|supine|imperative|infinitive|"
    r"first|second|third|combining|contraction|short|standard|simplified|traditional|"
    r"variant|form|spelling|synonym|e-form|verbal|ablaut)\b[^;]*?\b(?:of|for)\b)",
    re.I,
)
_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_STOP_TEXT = (
    "the and for with that which having used from into onto not are has have who whom"
    " whose its their his her this these those one any some something someone somebody"
    " anything person people thing things act state quality condition relating"
    " pertaining being type kind sort way manner often usually especially esp also"
    " other another than then thus very more most less such only just can may will"
    " would should could does did was were been form forms word words term terms sense"
    " senses meaning meanings use uses usage alternative spelling variant obsolete"
    " archaic dated rare plural singular tense noun verb adjective adverb pronoun"
    " preposition conjunction participle genitive dative accusative nominative"
    " locative present past future first second third"
)
_STOP = frozenset(_STOP_TEXT.split())


def gloss_tokens(gloss: str | None, max_tokens: int = 8) -> list[str]:
    """Content words of a gloss. 'Form of' glosses (alternative form of X, plural of X, ...) give
    none: they describe a spelling or inflection, not a meaning. Parenthetical text is dropped."""
    if not gloss:
        return []
    g = gloss.strip()[:300].lower()
    if _FORM_OF.match(g):
        return []
    g = _PAREN.sub(" ", g)
    out: list[str] = []
    for w in re.findall(r"[a-z]{3,}", g):
        if w not in _STOP and w not in out:
            out.append(w)
        if len(out) >= max_tokens:
            break
    return out


def concept_tokens(label: str | None) -> list[str]:
    """Content words of a concept label (concept labels are upper-case: 'TO BREAK')."""
    return gloss_tokens(label.lower() if label else None)


def gate_passes(
    gate: str,
    tokens_a: Iterable[str],
    tokens_b: Iterable[str],
    concepts_a: Iterable[str] = (),
    concepts_b: Iterable[str] = (),
) -> str | None:
    """How two words pass a gate: 'concept', 'gloss' or None. The concept gate needs a shared
    concept id; the gloss gate also passes on a shared content word."""
    if set(concepts_a) & set(concepts_b):
        return "concept"
    if gate == "gloss" and set(tokens_a) & set(tokens_b):
        return "gloss"
    return None


def build_gloss_tokens(conn, datasets: Sequence[str] | None = None, batch: int = 200_000) -> dict:
    """(Re)build layers.gloss_token from lexeme.gloss and from the labels of linked concepts.

    Rebuilds the whole table; run it again after an import that changes glosses or concepts.
    Slow on the full database (millions of rows): run it once, in the background."""
    ensure_schema(conn)
    conn.execute("truncate layers.gloss_token")
    conn.execute("drop index if exists layers.ix_gloss_token_token")
    ds_sql = " and l.dataset = any(%(ds)s)" if datasets else ""
    args = {"ds": list(datasets)} if datasets else {}
    total = 0
    with (
        conn.transaction(),
        conn.cursor(name="gloss_tokens") as src,
    ):  # named cursors need a transaction
        src.itersize = batch
        src.execute(
            "select l.id, l.gloss, (select string_agg(c.label, ' ; ') from lexeme_concept lc"
            " join concept c on c.id = lc.concept_id where lc.lexeme_id = l.id)"
            " from lexeme l where (l.gloss is not null or exists (select 1 from lexeme_concept x"
            f" where x.lexeme_id = l.id)){ds_sql}",
            args,
        )
        while True:
            rows = src.fetchmany(batch)  # COPY cannot run while the cursor is fetching: batch it
            if not rows:
                break
            out = []
            for lid, gloss, labels in rows:
                toks = gloss_tokens(gloss)
                for lab in (labels or "").split(" ; "):
                    toks += [t for t in concept_tokens(lab) if t not in toks]
                toks = toks[:10]
                out.extend((t, lid, len(toks)) for t in toks)
            with (
                conn.cursor() as dst,
                dst.copy("copy layers.gloss_token (token, lexeme_id, n_tokens) from stdin") as cp,
            ):
                for row in out:
                    cp.write_row(row)
            total += len(out)
    conn.execute("create index ix_gloss_token_token on layers.gloss_token (token, lexeme_id)")
    conn.execute("analyze layers.gloss_token")
    return {"token_rows": total}


# --------------------------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------------------------


def bin_of(value: float) -> float:
    """Lower edge of the 0.05-wide score bin (1.0 falls in the top bin, 0.95)."""
    b = min(int(value / BIN_WIDTH + 1e-9), int(1 / BIN_WIDTH) - 1)
    return round(b * BIN_WIDTH, 2)


def _pav(values: list[float], weights: list[float]) -> list[float]:
    """Weighted isotonic regression (non-decreasing) by pool-adjacent-violators."""
    blocks: list[list[float]] = []  # [mean, weight, count]
    for v, w in zip(values, weights, strict=True):
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            m2, w2, c2 = blocks.pop()
            m1, w1, c1 = blocks.pop()
            ww = w1 + w2
            blocks.append([(m1 * w1 + m2 * w2) / ww if ww else 0.0, ww, c1 + c2])
    out: list[float] = []
    for m, _w, c in blocks:
        out.extend([m] * int(c))
    return out


def fit_calibration(
    scores: Sequence[float],
    labels: Sequence[int],
    weights: Sequence[float] | None = None,
) -> list[dict]:
    """Precision per score bin, monotone in the score (isotonic), from scored labelled pairs.

    `weights` re-weights pairs (e.g. to the natural mix of positives and negatives). Returns one
    dict per non-empty bin: score_bin, precision (weighted), precision_balanced (unweighted,
    monotone), n, n_pos. Precision here is P(cognate | score in bin or higher-calibrated bin),
    a monotone estimate of P(cognate | score in bin)."""
    w = list(weights) if weights is not None else [1.0] * len(scores)
    bins: dict[float, list] = defaultdict(lambda: [0.0, 0.0, 0, 0, 0])  # wpos, wall, pos, n
    for s, y, wi in zip(scores, labels, w, strict=True):
        b = bins[bin_of(s)]
        b[0] += wi * y
        b[1] += wi
        b[2] += y
        b[3] += 1
    edges = sorted(bins)
    pw = _pav(
        [bins[e][0] / bins[e][1] if bins[e][1] else 0.0 for e in edges], [bins[e][1] for e in edges]
    )
    pb = _pav([bins[e][2] / bins[e][3] for e in edges], [bins[e][3] for e in edges])
    return [
        {
            "score_bin": e,
            "precision": round(pw[i], 4),
            "precision_balanced": round(pb[i], 4),
            "n": bins[e][3],
            "n_pos": bins[e][2],
        }
        for i, e in enumerate(edges)
    ]


def store_calibration(
    conn, method: str, gate: str, rows: Iterable[dict], stratum: str = "all"
) -> int:
    """Replace the calibration of (method, gate, stratum) with fitted rows."""
    ensure_schema(conn)
    conn.execute(
        "delete from layers.candidate_calibration where method=%s and gate=%s and stratum=%s",
        (method, gate, stratum),
    )
    n = 0
    for r in rows:
        conn.execute(
            "insert into layers.candidate_calibration (method, gate, stratum, score_bin,"
            " precision_dev, precision_dev_balanced, n_dev, n_pos_dev, domain)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (method, gate, stratum, r["score_bin"], r["precision"], r["precision_balanced"],
             r["n"], r["n_pos"], CALIBRATION_DOMAIN),
        )  # fmt: skip
        n += 1
    return n


def load_calibration(
    conn, method: str, gate: str, stratum: str = "all"
) -> dict[float, tuple[float | None, int]]:
    """{score_bin: (precision_dev, n_dev)} for a method, gate and stratum (default 'all')."""
    with conn.cursor() as cur:
        cur.execute(
            "select score_bin, precision_dev, n_dev from layers.candidate_calibration"
            " where method=%s and gate=%s and stratum=%s",
            (method, gate, stratum),
        )
        return {round(float(b), 2): (p, n) for b, p, n in cur.fetchall()}


STRATA = ("same_subbranch", "same_branch", "cross_branch")


def clade_stratum(path_a: Sequence[str] | None, path_b: Sequence[str] | None) -> str:
    """How close two languages are in the Glottolog classification path (family, then the
    branch at index 2 and the sub-branch at index 3): same_subbranch, same_branch, cross_branch.
    'unknown' when a path is missing or too short to say."""
    if not path_a or not path_b or len(path_a) < 3 or len(path_b) < 3:
        return "unknown"
    if len(path_a) >= 4 and len(path_b) >= 4 and list(path_a[:4]) == list(path_b[:4]):
        return "same_subbranch"
    if list(path_a[:3]) == list(path_b[:3]):
        return "same_branch"
    return "cross_branch"


def calibrated_precision(
    table: dict, value: float, max_gap: float = 0.1
) -> tuple[float | None, int]:
    """(precision, n) of the bin of a score. A bin with no fitted pairs falls back to the nearest
    LOWER fitted bin within `max_gap` (precision is monotone in the score, so that is
    conservative); otherwise (None, 0): no calibration, no guess."""
    b = bin_of(value)
    for edge in sorted((e for e in table if e <= b + 1e-9), reverse=True):
        if b - edge > max_gap + 1e-9:
            break
        got = table[edge]
        if got[0] is not None:
            return float(got[0]), got[1]
    return None, 0


# --------------------------------------------------------------------------------------------
# retrieval
# --------------------------------------------------------------------------------------------


@dataclass
class Candidate:
    lexeme_id: str
    language_id: str
    form: str
    gloss: str | None
    score: float
    method: str
    gate: str
    gate_via: str  # concept | gloss
    calibrated_precision: float | None
    calibration_n: int = 0
    stratum: str = "unknown"  # clade distance to the query word's language (clade_stratum)
    calibrated: bool = False  # False: the calibration domain (Indo-European) does not apply
    n_sources: int = 1  # lexemes (datasets) with the same language and spelling
    normalized_form: str = ""
    params: dict = field(default_factory=dict)
    evidence_kind: str = "computed"  # always: a candidate is never a documented relationship


_ROW = (
    "l.id, l.language_id, l.form, l.normalized_form, l.transliteration, l.search_key, l.gloss,"
    " g.family_id, g.metadata_json->'classification_path'"
)
_BASE = (
    "from lexeme l join language g on g.id = l.language_id"
    " where l.language_id <> %(lang)s and g.id not like 'conlang-%%'"
    " and l.form_kind in ('word', 'compound', 'root', 'stem')"
)


def _ds_filter(datasets: Sequence[str] | None) -> str:
    return " and l.dataset = any(%(ds)s)" if datasets is not None else ""


def candidates_for(
    conn,
    lexeme_id: str,
    k: int = 20,
    gate: str = "gloss",
    *,
    method: str | None = None,
    datasets: Sequence[str] | None = None,
    min_score: float = 0.0,
    pool_cap: int = POOL_CAP,
) -> list[Candidate]:
    """Same-meaning lexemes of OTHER languages of `lexeme_id`, best score first (at most k).

    One row per (language, spelling): a spelling that occurs in several datasets is returned
    once with `n_sources`. Constructed languages are never candidates (and get none).
    `datasets` restricts the candidate words to those datasets (e.g. the open ones).
    `pool_cap` bounds how many gated words are scored; for a very common gloss the pool is
    ranked by gloss specificity before the cap, so the cap can cost recall (it is not hidden:
    callers that need to know can compare against pool_cap)."""
    if gate not in GATES:
        raise ValueError(f"gate must be one of {GATES}")
    method = method or DEFAULT_METHOD
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}")
    with conn.cursor() as cur:
        cur.execute(
            "select l.language_id, l.form, l.transliteration, l.search_key, l.gloss, g.family_id,"
            " g.id like 'conlang-%%', g.metadata_json->'classification_path'"
            " from lexeme l join language g on g.id = l.language_id"
            " where l.id = %s",
            (lexeme_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"unknown lexeme id {lexeme_id!r}")
        lang, form, translit, skey, gloss, family, is_conlang, path = row
        if is_conlang:
            return []
        cur.execute(
            "select lc.concept_id, c.label from lexeme_concept lc"
            " join concept c on c.id = lc.concept_id where lc.lexeme_id = %s",
            (lexeme_id,),
        )
        concepts = cur.fetchall()
    concept_ids = [c[0] for c in concepts]
    toks = gloss_tokens(gloss)
    for _, label in concepts:
        toks += [t for t in concept_tokens(label) if t not in toks]
    if not concept_ids and (gate == "concept" or not toks):
        return []

    pool: dict[str, str] = {}  # lexeme id -> how it passed the gate
    args = {"lang": lang, "ds": list(datasets) if datasets is not None else None}
    with conn.cursor() as cur:
        if concept_ids:
            cur.execute(
                f"select l.id {_BASE} and l.id in (select lc.lexeme_id from lexeme_concept lc"
                f" where lc.concept_id = any(%(cids)s)){_ds_filter(datasets)} limit %(cap)s",
                {**args, "cids": concept_ids, "cap": pool_cap},
            )
            pool.update({r[0]: "concept" for r in cur.fetchall()})
        if gate == "gloss" and toks and len(pool) < pool_cap:
            cur.execute(
                "select t.lexeme_id, count(*)::float / (max(t.n_tokens) + %(nq)s - count(*)) as jac"
                " from layers.gloss_token t where t.token = any(%(toks)s)"
                " group by t.lexeme_id order by jac desc, t.lexeme_id limit %(cap)s",
                {"toks": toks, "nq": len(toks), "cap": pool_cap * 2},
            )
            ids = [r[0] for r in cur.fetchall() if r[0] not in pool and r[0] != lexeme_id]
            for i in range(0, len(ids), 5000):
                cur.execute(
                    f"select l.id {_BASE} and l.id = any(%(ids)s){_ds_filter(datasets)}",
                    {**args, "ids": ids[i : i + 5000]},
                )
                for (cid,) in cur.fetchall():
                    if len(pool) < pool_cap:
                        pool.setdefault(cid, "gloss")
    if not pool:
        return []

    query_text = scoring_text(form, translit, skey)
    fn = METHODS[method]
    seen: dict[tuple[str, str], Candidate] = {}
    ids = sorted(pool)
    with conn.cursor() as cur:
        for i in range(0, len(ids), 5000):
            cur.execute(
                f"select {_ROW} from lexeme l join language g on g.id = l.language_id"
                " where l.id = any(%s)",
                (ids[i : i + 5000],),
            )
            for cid, clang, cform, cnorm, ctr, csk, cgloss, cfam, cpath in cur.fetchall():
                text_ = scoring_text(cform, ctr, csk)
                sc = fn(query_text, text_)
                if sc < min_score:
                    continue
                key = (clang, cnorm)
                prev = seen.get(key)
                if prev is not None:
                    prev.n_sources += 1
                    if sc > prev.score:
                        prev.score = sc
                    continue
                seen[key] = Candidate(
                    lexeme_id=cid, language_id=clang, form=cform, gloss=cgloss, score=sc,
                    normalized_form=cnorm, method=method, gate=gate, gate_via=pool[cid],
                    calibrated_precision=None,
                    stratum=clade_stratum(path, cpath),
                    calibrated=(cfam == CALIBRATION_FAMILY),
                    params={"gate": gate, "pool_cap": pool_cap},
                )  # fmt: skip
    top = sorted(seen.values(), key=lambda c: (-c.score, c.lexeme_id))[:k]
    tables = {st: load_calibration(conn, method, gate, st) for st in ("all", *STRATA)}
    by_stratum = any(tables[st] for st in STRATA)
    for c in top:
        in_domain = c.calibrated and family == CALIBRATION_FAMILY
        c.calibrated = bool(in_domain)
        if not in_domain:
            continue
        # once strata are fitted only the pair's own stratum counts (cross-branch pairs are far
        # less precise than same-branch ones; an unknown stratum gets no number); 'all' is used
        # only when no strata were fitted
        table = tables.get(c.stratum, {}) if by_stratum else tables["all"]
        c.calibrated_precision, c.calibration_n = calibrated_precision(table, c.score)
    return top


def materialise_candidates(
    conn,
    lexeme_ids: Iterable[str],
    k: int = 20,
    gate: str = "gloss",
    *,
    method: str | None = None,
    datasets: Sequence[str] | None = None,
) -> dict:
    """Store the candidates of the given lexemes in layers.candidate_pair (never in public)."""
    ensure_schema(conn)
    method = method or DEFAULT_METHOD
    counts = {"lexemes": 0, "pairs": 0, "without_candidates": 0}
    for lid in lexeme_ids:
        counts["lexemes"] += 1
        cands = candidates_for(conn, lid, k, gate, method=method, datasets=datasets)
        if not cands:
            counts["without_candidates"] += 1
        for c in cands:
            a, b = sorted((lid, c.lexeme_id))
            conn.execute(
                "insert into layers.candidate_pair (a, b, method, params, score, gate, gate_via,"
                " calibrated_precision) values (%s, %s, %s, %s, %s, %s, %s, %s)"
                " on conflict (a, b, method, gate) do update set params = excluded.params,"
                " score = excluded.score, gate_via = excluded.gate_via,"
                " calibrated_precision = excluded.calibrated_precision, created_at = now()",
                (a, b, method, json.dumps(c.params), c.score, gate, c.gate_via,
                 c.calibrated_precision),
            )  # fmt: skip
            counts["pairs"] += 1
    return counts
