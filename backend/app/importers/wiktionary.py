"""Import Wiktionary entries and their etymologies from wiktextract JSONL (kaikki.org).

Each configured language lists its Wiktionary codes in data/config/languages.csv
(``wiktionary_codes``). For every entry in those languages (or, with ``all_languages``, in every
language) we keep the headword, up to three English glosses and the romanisation, and turn its
etymology templates into documented, typed relationships:

    inh, inh+            -> inherited_form   (entry -> ancestor)
    bor, bor+, lbor, ... -> borrowed_from    (entry -> donor)
    der, der+            -> etymon           (Wiktionary does not say inherited or borrowed;
                                              borrowed_from when the entry's own etymology text
                                              says "Borrowed from <language> <this term>")
    clq, cal, calque, sl -> calque_or_loan_translation
    af, affix, compound, prefix, suffix, confix -> has_component (entry -> part)
    cog                  -> cognate          (undirected; the editors' claim)
    etymon               -> by its :inh / :bor / :der / :af ... markers

The entry's "Descendants" list adds the other direction: each descendant is inherited from
the entry, or borrowed or calqued when Wiktionary marks it so. An unmarked {{desc}} is only a
default: when the descendant's own entry states how it got the word (a bor, der or calque
template), that statement replaces the default "inherited" link.

Terms that templates point to but that have no entry here (e.g. a Sanskrit etymon, an
Arabic donor) are created from the template itself, in their own language. Languages that
are not configured become disabled reference languages ``wkt-<code>``, which
``refresh-languages`` maps to one record per language. Every edge cites the Wiktionary page it
comes from.

Rows are staged in temporary tables and merged in SQL, so memory stays flat even for the
whole dump (every language: about 10 million entries).
"""

import gzip
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import (
    clean_form,
    form_kind,
    is_placeholder_form,
    lexeme_search_key,
    normalize_form,
    plain_text,
)

DATASET = "wiktionary"
SOURCE_ID = "wiktionary"

DIRECTED = {
    "inh": "inherited_form",
    "inh+": "inherited_form",
    "bor": "borrowed_from",
    "bor+": "borrowed_from",
    "lbor": "borrowed_from",
    "slbor": "borrowed_from",
    "obor": "borrowed_from",
    "ubor": "borrowed_from",
    "der": "etymon",
    "der+": "etymon",
    "clq": "calque_or_loan_translation",
    "cal": "calque_or_loan_translation",
    "calque": "calque_or_loan_translation",
    "sl": "calque_or_loan_translation",  # semantic loan
    "psm": "borrowed_from",  # phono-semantic matching
}
# {{etymon}} relation markers (":inh", ":bor", ...); terms before any marker are "from".
ETYMON_MARKERS = {
    "inh": "inherited_form",
    "bor": "borrowed_from",
    "lbor": "borrowed_from",
    "slbor": "borrowed_from",
    "obor": "borrowed_from",
    "ubor": "borrowed_from",
    "psm": "borrowed_from",
    "der": "etymon",
    "from": "etymon",
    "calque": "calque_or_loan_translation",
    "clq": "calque_or_loan_translation",
    "sl": "calque_or_loan_translation",
    "af": "has_component",
    "affix": "has_component",
    "compound": "has_component",
    "blend": "has_component",
    "pre": "has_component",
    "suf": "has_component",
    "deverbal": "etymon",
    "clipping": "etymon",
    "clip": "etymon",
    "uder": "etymon",  # uncertain derivation
    "bf": "etymon",  # back-formation
    "ellipsis": "etymon",
}
COMPONENT = {"af", "affix", "compound", "com", "prefix", "pre", "suffix", "suf", "confix", "con"}
COGNATE = {"cog", "cognate"}

# The first words of an entry's own etymology sentence ("Borrowed from Portuguese câmara"). An
# entry that states how it got its word without a template still tells us, and it outranks the
# parent page's unmarked {{desc}} line, which only defaults to "inherited".
# (After an etymology tree the sentence sits on a later line.)
_BORROWED_TEXT = re.compile(
    r"(?:^|\n)\W*(?:borrowed|learned borrowing|semi-learned borrowing|loan(?:ed)?\b|reborrowed)",
    re.I,
)
_INHERITED_TEXT = re.compile(r"(?:^|\n)\W*inherited\b", re.I)

# A {{der}} link is typed only "derived". When the entry's own etymology text opens with a
# borrowing sentence that names the same term as its donor ("Borrowed from French jus"), the
# text states what the template leaves open. The donor is the words between "from" and the next
# comma, bracket, "from", "via", "or" or "and".
_DONOR_OPEN = re.compile(
    r"(?:^|\n)\W*(?:learned borrowing|semi-learned borrowing|unadapted borrowing|borrowed|"
    r"reborrowed|loan(?:ed|word)?\b)(?P<mid>[^.,;()\n]{0,30}?)\bfrom\s+",
    re.I,
)
_DONOR_END = re.compile(r"[,;(\n]|\.(?:\s|$)|\s(?:from|via|or|and|whence|ultimately|derived)\s")
_DONOR_FILLER = {
    "either",
    "directly",
    "indirectly",
    "probably",
    "possibly",
    "also",
    "a",
    "an",
    "the",
}
# generic links whose type is only "etymon" and that sit on the entry's own page
GENERIC_ETYMON = {"der", "der+", "ety", "etymon"}


def fold_text(s: str) -> str:
    """Accent-, case- and asterisk-insensitive form for comparing a term with prose."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().replace("*", "").strip()


def borrowed_donor(text: str) -> str | None:
    """The words after "from" in an entry's opening borrowing sentence ("French jus" in
    "Borrowed from French jus, from Latin ..."), or None when the text does not open with a
    borrowing, also says "Inherited", or describes a calque."""
    m = _DONOR_OPEN.search(text)
    if not m or _INHERITED_TEXT.search(text):
        return None
    if re.search(r"translation|calque|semantic", m.group("mid"), re.I):
        return None
    rest = text[m.end() :]
    end = _DONOR_END.search(rest)
    return (rest[: end.start()] if end else rest).strip() or None


def donor_prefix(donor: str, shown: Iterable[str]) -> str | None:
    """The language words before the term in ``donor`` when the donor ends with one of the
    ``shown`` spellings of the link's target; None when none does."""
    folded = fold_text(donor)
    for form in shown:
        f = fold_text(form)
        if f and folded.endswith(" " + f):
            return folded[: -len(f)].strip()
    return None


def donor_language_matches(prefix: str, names: dict[str, str], code: str, variety: bool) -> bool:
    """Does the language named in the text ("Old French") fit the link target's language code?
    A variety (a code like la-lat, or one merged into its parent) may add words before its
    parent's name ("Late Latin"); otherwise the words must equal the language's name."""
    words = [w for w in prefix.split() if w not in _DONOR_FILLER]
    got = " ".join(words)
    if code in names:
        return got == fold_text(names[code])
    base = names.get(code.split("-")[0])
    return bool(base and (variety or "-" in code) and got.endswith(fold_text(base)))


def is_proto_code(code: str, names: dict[str, str]) -> bool:
    """Proto-languages: Wiktionary names them "Proto-X" and mostly codes them "...-pro". The code
    alone misleads (oc-pro is Provençal, not a reconstruction), so a known name wins."""
    name = names.get(code)
    if name:
        return name.startswith("Proto-")
    return code.endswith("-pro")


def load_iso_names(path: Path) -> dict[str, str]:
    """ISO 639-3 and 639-1 code -> reference name, from SIL's iso-639-3.tab, to name languages
    Wiktionary only mentions by code."""
    import csv

    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            out[r["Id"]] = r["Ref_Name"]
            if r["Part1"]:
                out[r["Part1"]] = r["Ref_Name"]
    return out


_LANG_CODE = re.compile(r'"lang_code": ?"([^"]+)"')
_LANG_PAIR = re.compile(r'"lang": ?"([^"]+)", ?"lang_code": ?"([^"]+)"')

# Wiktionary's etymology-only varieties, merged into the language they belong to (the
# variety stays in the relationship's original label).
ETYMOLOGY_ONLY = {
    "pra-sau": "pra",
    "pra-mah": "pra",
    "pra-mag": "pra",
    "pra-pai": "pra",
    "pra-ard": "pra",
    "sa-cls": "sa",
    "sa-ved": "sa",
    "sa-bra": "sa",
    "sa-epi": "sa",
}


def iter_jsonl(
    path: Path, codes: set[str] | None = None, names: dict[str, str] | None = None
) -> Iterator[dict]:
    """Entries from a wiktextract JSONL file, optionally only those in ``codes``.

    The full dump is about 25 GB, so a line is parsed only if one of its language codes is
    wanted (nested translations and descendants carry codes too, so callers must still check
    the entry's own code). ``names`` collects code -> language name from adjacent "lang" /
    "lang_code" pairs on every line, which also names languages only seen as sources."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith("{"):
                continue
            if names is not None:
                for lang, code in _LANG_PAIR.findall(line):
                    if not lang.endswith(" script"):
                        names.setdefault(code, lang)
            if codes is None or any(c in codes for c in _LANG_CODE.findall(line)):
                yield json.loads(line)


def page_url(word: str) -> str:
    return "https://en.wiktionary.org/wiki/" + word.replace(" ", "_")


def term_key(code: str, term: str) -> str:
    """Record key shared by an entry and every template that names the same term."""
    return f"{code}:{normalize_form(term.lstrip('*'))}"


@dataclass
class Term:
    code: str
    form: str
    gloss: str | None = None
    roman: str | None = None
    is_entry: bool = False
    glosses: list[str] = field(default_factory=list)
    borrowed_text: bool = False  # the entry's own etymology sentence says "Borrowed"
    inherited_text: bool = False  # ... or says "Inherited" (an entry with both is ambiguous)


@dataclass
class Edge:
    child: str
    parent: str
    type_id: str
    template: str
    word: str  # the page the template is on
    rank: int
    directed: bool = True
    variety: str = ""  # etymology-only variety merged into the parent code, e.g. pra-sau
    shown: tuple[str, ...] = ()  # spellings of the target a text may show (lemma, display form)


_CODE = re.compile(r"[a-z]{2,3}(-[a-z]{2,4}){0,2}")


def language_codes(arg: str) -> list[str]:
    """Wiktionary language codes in a template argument: one code, or a comma-separated
    list (``{{cog|hi,mr|...}}``). Anything that is not a well-formed code is dropped."""
    out = []
    for raw in arg.split(","):
        code = raw.strip()
        if _CODE.fullmatch(code):
            out.append(ETYMOLOGY_ONLY.get(code, code))
    return out


_MODIFIER = re.compile(r"<(\w+):([^>]*)>")


def strip_html(text: str) -> str:
    """A gloss as plain text: HTML, wiki links, templates and entities removed."""
    return plain_text(text)


def parse_terms(raw: str) -> list[tuple[str, str | None, str | None]]:
    """(term, gloss, transliteration) triples from a template term argument.

    Wiktionary allows several comma-separated terms in one argument and inline modifiers
    such as ``term<t:gloss>``, ``<alt:...>``, ``<tr:...>`` and ``<ts:...>``. Arguments that
    carry rendered HTML are not terms and are skipped."""
    if not raw or raw == "-" or re.search(r"</?(i|b|span|a)\b", raw):
        return []
    pieces, depth, cur = [], 0, ""
    for ch in raw:  # split on commas outside <...>; a stray ">" must not break later splits
        depth += ch == "<"
        depth = max(0, depth - (ch == ">"))
        if ch == "," and depth == 0:
            pieces.append(cur)
            cur = ""
        else:
            cur += ch
    pieces.append(cur)
    out = []
    for piece in pieces:
        mods = dict(_MODIFIER.findall(piece))
        term = clean_form(re.sub(r"<[^>]*>", "", piece))
        term = re.sub(r"[\s<>]+$", "", term)  # residue of an unbalanced tag, e.g. "adārum>>"
        if term and term != "-" and ">>" not in term and not is_placeholder_form(term):
            out.append((term, mods.get("t") or mods.get("gloss"), mods.get("tr") or mods.get("ts")))
    return out


def template_edges(entry: dict, child_key: str, code: str) -> Iterator[tuple[Edge, Term]]:
    """(edge, other term) pairs from one entry's etymology templates."""
    for rank, t in enumerate(entry.get("etymology_templates") or [], start=1):
        name, args = t.get("name", ""), t.get("args") or {}
        if name in DIRECTED and args.get("1") == code:
            raw_src = args.get("2", "").strip()
            src = ETYMOLOGY_ONLY.get(raw_src, raw_src)
            gloss = args.get("t") or args.get("gloss") or args.get("5")
            if not _CODE.fullmatch(raw_src):
                continue
            for term, t_gloss, tr in parse_terms(args.get("3", "")):
                yield (
                    Edge(
                        child_key,
                        term_key(src, term),
                        DIRECTED[name],
                        name,
                        entry["word"],
                        rank,
                        variety=raw_src if raw_src != src else "",
                        shown=(term, args.get("4", "")),
                    ),
                    Term(src, term, t_gloss or gloss or None, tr or args.get("tr") or None),
                )
        elif name in COMPONENT and args.get("1") == code:
            parts = [args[k] for k in sorted((k for k in args if k.isdigit()), key=int)][1:]
            for part in parts:
                src, _, rest = part.rpartition(":") if ":" in part[:12] else ("", "", part)
                if src and not _CODE.fullmatch(src):
                    src, rest = "", part  # a colon inside the term, not a language prefix
                src = ETYMOLOGY_ONLY.get(src, src) or code
                for term, t_gloss, tr in parse_terms(rest)[:1]:
                    yield (
                        Edge(
                            child_key,
                            term_key(src, term),
                            "has_component",
                            name,
                            entry["word"],
                            rank,
                        ),
                        Term(src, term, t_gloss, tr),
                    )
        elif name in ("etymon", "ety") and args.get("1") == code:
            # {{ety}} is the etymology-tree form of {{etymon}}: the same markers and terms
            relation = "etymon"
            for k in sorted((k for k in args if k.isdigit() and k != "1"), key=int):
                arg = args[k].strip()
                if arg.startswith(":"):
                    # markers may carry modifiers: ":af<surf>", ":bor<unc>", ":der<conj:and>"
                    relation = ETYMON_MARKERS.get(re.sub(r"<.*$", "", arg[1:]).strip())
                    continue
                if not relation:  # a marker we do not map (e.g. :doublet): skip its terms
                    continue
                src, sep, rest = arg.partition(":")
                if not sep or not _CODE.fullmatch(src):
                    src, rest = code, arg
                src = ETYMOLOGY_ONLY.get(src, src)
                for term, t_gloss, tr in parse_terms(rest)[:1]:
                    yield (
                        Edge(
                            child_key,
                            term_key(src, term),
                            relation,
                            name,
                            entry["word"],
                            rank,
                            shown=(term,),
                        ),
                        Term(src, term, t_gloss, tr),
                    )
        elif name in COGNATE:
            gloss = args.get("t") or args.get("4")
            for src, (term, t_gloss, tr) in (
                (c, t)
                for c in language_codes(args.get("1", ""))
                for t in parse_terms(args.get("2", ""))
            ):
                yield (
                    Edge(
                        child_key,
                        term_key(src, term),
                        "cognate",
                        name,
                        entry["word"],
                        rank,
                        directed=False,
                    ),
                    Term(src, term, t_gloss or gloss or None, tr or args.get("tr") or None),
                )


def descendant_type(item: dict) -> str:
    """Relationship from a "Descendants" item to its ancestor. Wiktionary's {{desc}} means
    inherited unless it is marked borrowed, calqued or only derived."""
    tags = " ".join((item.get("tags") or []) + (item.get("raw_tags") or [])).lower()
    if "calque" in tags or "semantic loan" in tags:
        return "calque_or_loan_translation"
    if "borrow" in tags or "learned" in tags:
        return "borrowed_from"
    if "derived" in tags or "uncertain" in tags:
        return "etymon"
    return "inherited_form"


def descendant_edges(
    items: list[dict], parent_key: str, word: str, depth: int = 0
) -> Iterator[tuple[Edge, Term]]:
    """(edge, descendant) pairs from an entry's Descendants tree; a nested item descends
    from the item above it."""
    for rank, item in enumerate(items or [], start=1):
        raw = item.get("lang_code") or ""
        code = ETYMOLOGY_ONLY.get(raw, raw)
        key = parent_key
        if _CODE.fullmatch(raw) and item.get("word"):
            for term, _gloss, _tr in parse_terms(item["word"])[:1]:
                key = term_key(code, term)
                if key != parent_key:
                    yield (
                        Edge(
                            key,
                            parent_key,
                            descendant_type(item),
                            "desc",
                            word,
                            rank,
                            variety=raw if raw != code else "",
                        ),
                        Term(code, term, None, item.get("roman")),
                    )
        if depth < 8 and item.get("descendants"):
            yield from descendant_edges(item["descendants"], key, word, depth + 1)


def is_form_of(entry: dict) -> bool:
    """An entry whose every sense only points to another form (inflections, spellings)."""
    senses = entry.get("senses") or []
    return bool(senses) and all(
        s.get("form_of") or "form-of" in (s.get("tags") or []) for s in senses
    )


def romanization(entry: dict) -> str | None:
    for f in entry.get("forms") or []:
        if "romanization" in (f.get("tags") or []):
            return f.get("form")
    return None


def entry_glosses(entry: dict) -> list[str]:
    out = []
    for s in entry.get("senses") or []:
        out.extend(strip_html(g) for g in s.get("glosses") or [] if g)
    return out


def wiktionary_code_map() -> dict[str, str]:
    """Wiktionary language code -> configured language id, from data/config/languages.csv."""
    from app.importers.jambu import load_languages

    return {code: t.id for t in load_languages() for code in t.wiktionary_codes.split(";") if code}


FLUSH = 100_000  # staged rows per COPY

STAGING = """
CREATE TEMP TABLE wkt_term (
    seq bigint, key text, lid text, language_id text, form text, normalized_form text,
    search_key text, roman text, gloss text, form_kind text, reconstructed boolean,
    is_entry boolean, borrowed_text boolean) ON COMMIT DROP;
CREATE TEMP TABLE wkt_textcand (seq bigint) ON COMMIT DROP;
CREATE TEMP TABLE wkt_edge (
    seq bigint, rid text, child_lid text, parent_lid text, type_id text, directed boolean,
    record text, label text, rank integer, word text, template text) ON COMMIT DROP;
"""
TERM_COLS = (
    "seq",
    "key",
    "lid",
    "language_id",
    "form",
    "normalized_form",
    "search_key",
    "roman",
    "gloss",
    "form_kind",
    "reconstructed",
    "is_entry",
    "borrowed_text",
)
EDGE_COLS = (
    "seq",
    "rid",
    "child_lid",
    "parent_lid",
    "type_id",
    "directed",
    "record",
    "label",
    "rank",
    "word",
    "template",
)


def import_wiktionary(
    conn: psycopg.Connection,
    files: Iterable[Path],
    version: str,
    code_map: dict[str, str],
    language_names: dict[str, str] | None = None,
    reference_codes: Iterable[str] = (),
    etymology_only_codes: Iterable[str] = (),
    all_languages: bool = False,
    fallback_names: dict[str, str] | None = None,
) -> dict:
    """code_map: Wiktionary code -> configured language id (the entry languages).

    reference_codes: further languages (e.g. Russian, Proto-Indo-Aryan) whose own entries are
    imported too, so etymology chains continue; ``refresh-languages`` then maps them to one
    record per language. etymology_only_codes: languages whose entries are imported only
    when they carry etymology (templates or descendants), to keep large languages within a
    disk budget. all_languages: entries in every language. Outside the configured
    languages, inflected-form entries ("form of ...") are skipped."""
    files = list(files)
    names = dict(language_names or {})
    stats: dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        stats[k] = stats.get(k, 0) + n

    def language_of(code: str) -> str:
        return code_map.get(code) or f"wkt-{code.lower()}"

    etymology_only = set(etymology_only_codes)
    wanted = None if all_languages else set(code_map) | set(reference_codes) | etymology_only
    codes: set[str] = set()
    term_rows: list[tuple] = []
    edge_rows: list[tuple] = []
    seq = 0
    # {{der}} links whose entry text names the target as its donor, to be checked against the
    # language names once the whole dump has been read: (entry no., rank, edge seq, target
    # language code, variety merged, words before the term in the text)
    donor_candidates: list[tuple[int, int, int, str, bool, str]] = []
    entry_no = 0

    with conn.cursor() as cur:
        cur.execute(STAGING)

        def flush(force: bool = False) -> None:
            if term_rows and (force or len(term_rows) >= FLUSH):
                copy_rows(cur, "wkt_term", TERM_COLS, term_rows)
                term_rows.clear()
            if edge_rows and (force or len(edge_rows) >= FLUSH):
                copy_rows(cur, "wkt_edge", EDGE_COLS, edge_rows)
                edge_rows.clear()

        def stage_term(key: str, t: Term, gloss: str | None) -> None:
            nonlocal seq
            form = clean_form(t.form)
            proto = is_proto_code(t.code, names)
            if proto and not form.startswith("*"):
                form = "*" + form  # reconstruction pages are titled without the asterisk
            lang = language_of(t.code)
            codes.add(t.code)
            seq += 1
            term_rows.append(
                (
                    seq,
                    key,
                    lexeme_id(DATASET, key),
                    lang,
                    form,
                    normalize_form(form),
                    lexeme_search_key(form, lang),
                    t.roman,
                    gloss,
                    form_kind(form, False).value,
                    form.startswith("*") or proto,
                    t.is_entry,
                    t.borrowed_text and not t.inherited_text,
                )
            )

        def stage_edge(edge: Edge) -> None:
            nonlocal seq
            if edge.type_id == "cognate":
                a, b = sorted((edge.child, edge.parent))
                rid = relationship_id(DATASET, "cognate", a, b)
            else:
                a, b = edge.child, edge.parent
                rid = relationship_id(DATASET, edge.type_id, a, b)
            seq += 1
            edge_rows.append(
                (
                    seq,
                    rid,
                    lexeme_id(DATASET, a),
                    lexeme_id(DATASET, b),
                    edge.type_id,
                    edge.directed,
                    f"{edge.word}#{edge.template}",
                    f"{{{{{edge.template}}}}}" + (f" ({edge.variety})" if edge.variety else ""),
                    edge.rank,
                    edge.word,
                    edge.template,
                )
            )
            bump(f"template:{edge.template}")

        # Homograph entries (one page, several parts of speech) are adjacent in the dump;
        # their glosses are merged before staging.
        pending: Term | None = None
        pending_key = ""

        def stage_pending() -> None:
            if pending is not None and pending.form.strip():
                gloss = "; ".join(dict.fromkeys(pending.glosses[:3])) or None
                stage_term(pending_key, pending, gloss)

        for path in files:
            for e in iter_jsonl(path, wanted, names):
                code, raw_word = e.get("lang_code"), e.get("word")
                word = clean_form(raw_word) if raw_word else ""
                if not word or not code or (wanted is not None and code not in wanted):
                    continue
                if is_placeholder_form(word):
                    bump("skipped_placeholder_form")
                    continue
                if not _CODE.fullmatch(code):
                    continue
                if e.get("lang"):
                    names[code] = e["lang"]  # an entry's own language name beats mentions
                if code not in code_map and is_form_of(e):
                    bump("skipped_form_of")
                    continue
                if (
                    code in etymology_only
                    and not e.get("etymology_templates")
                    and not e.get("descendants")
                ):
                    bump("skipped_without_etymology")
                    continue
                key = term_key(code, word)
                # citations name the page: reconstructions live at "Reconstruction:<lang>/<word>"
                page = e.get("original_title") or raw_word
                if page != word:
                    e = {**e, "word": page}
                if key != pending_key:
                    stage_pending()
                    pending, pending_key = Term(code, word, is_entry=True), key
                text = e.get("etymology_text") or ""
                pending.borrowed_text = pending.borrowed_text or bool(_BORROWED_TEXT.search(text))
                pending.inherited_text = pending.inherited_text or bool(
                    _INHERITED_TEXT.search(text)
                )
                pending.glosses.extend(entry_glosses(e))
                pending.roman = pending.roman or romanization(e)
                pairs = [
                    *template_edges(e, key, code),
                    *descendant_edges(e.get("descendants"), key, page),
                ]
                entry_no += 1
                # the text only decides a generic link when the entry's templates say nothing
                # firmer (a bor, inh or calque template makes later {{der}} lines deeper steps)
                donor = None
                if not any(
                    ed.type_id in ("borrowed_from", "inherited_form", "calque_or_loan_translation")
                    for ed, _ in pairs
                    if ed.template != "desc"
                ):
                    donor = borrowed_donor(text)
                for edge, other in pairs:
                    if edge.parent == edge.child:
                        continue
                    other_key = edge.child if edge.template == "desc" else edge.parent
                    stage_term(other_key, other, strip_html(other.gloss) if other.gloss else None)
                    stage_edge(edge)
                    if (
                        donor
                        and edge.template in GENERIC_ETYMON
                        and edge.type_id == "etymon"
                        and (prefix := donor_prefix(donor, edge.shown)) is not None
                    ):
                        donor_candidates.append(
                            (entry_no, edge.rank, seq, other.code, bool(edge.variety), prefix)
                        )
                flush()
        stage_pending()
        flush(force=True)

        # One donor per entry: the first {{der}} link whose language fits the text.
        retype_der: dict[int, tuple[int, int]] = {}
        known_names = {**(fallback_names or {}), **names}
        for entry_no_, rank_, seq_, tcode, has_variety, prefix in sorted(donor_candidates):
            if entry_no_ not in retype_der and donor_language_matches(
                prefix, known_names, tcode, has_variety
            ):
                retype_der[entry_no_] = (seq_, rank_)
        copy_rows(cur, "wkt_textcand", ("seq",), [(v[0],) for v in retype_der.values()])

        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({p.name: sha256_file(p) for p in files}),
                psycopg.types.json.Jsonb(
                    [
                        "wiktextract JSONL entries: every language"
                        if all_languages
                        else "wiktextract JSONL entries for the configured languages' codes",
                        "Entries in reference (ancestor) languages imported as disabled languages",
                        "One record per language and headword; up to three English glosses",
                        "Etymology templates -> typed relationships (see module docstring)",
                        "Descendants lists -> inherited / borrowed / calque relationships",
                        "Template targets without an entry created from the template",
                        "Unconfigured languages filed as disabled reference languages wkt-<code>",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))

        for code in sorted(codes - set(code_map)):
            name = names.get(code) or (fallback_names or {}).get(code) or code
            cur.execute(
                "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
                " VALUES (%s, %s, 'other', %s, false, %s) ON CONFLICT (id) DO UPDATE SET"
                " name = EXCLUDED.name, is_proto = EXCLUDED.is_proto",
                (
                    language_of(code),
                    name,
                    is_proto_code(code, names),
                    psycopg.types.json.Jsonb({"wiktionary": code}),
                ),
            )
            cur.execute(
                "INSERT INTO language_alias (language_id, scheme, value) VALUES (%s, 'wiktionary',"
                " %s) ON CONFLICT DO NOTHING",
                (language_of(code), code),
            )

        # One lexeme per key: the first entry if there is one, else the first template term.
        # An entry keeps its own gloss; a template term takes the first gloss any template gives.
        cur.execute(
            """
            INSERT INTO lexeme (id, language_id, form, normalized_form, search_key, native_form,
                native_form_origin, transliteration, gloss, form_kind, reconstruction_status,
                dataset, source_id, source_record_id, source_citation, import_batch_id)
            SELECT DISTINCT ON (t.key) t.lid, t.language_id, t.form, t.normalized_form,
                t.search_key, t.form, 'source', coalesce(t.roman, f.roman),
                coalesce(t.gloss, f.gloss), t.form_kind::form_kind,
                (CASE WHEN t.reconstructed THEN 'reconstructed'
                      WHEN t.is_entry THEN 'attested' ELSE 'unknown' END)::reconstruction_status,
                %(ds)s, %(src)s, t.key,
                CASE WHEN t.is_entry THEN 'Wiktionary, “' || t.form || '”' END, %(batch)s
            FROM wkt_term t
            JOIN (SELECT key, is_entry,
                         (array_agg(gloss ORDER BY seq) FILTER (WHERE gloss IS NOT NULL))[1]
                             AS gloss,
                         (array_agg(roman ORDER BY seq) FILTER (WHERE roman IS NOT NULL))[1]
                             AS roman
                  FROM wkt_term GROUP BY key, is_entry) f
              ON f.key = t.key AND f.is_entry = t.is_entry
            ORDER BY t.key, t.is_entry DESC, t.seq
            """,
            {"ds": DATASET, "src": SOURCE_ID, "batch": batch},
        )
        cur.execute(
            "SELECT count(*) FILTER (WHERE source_citation IS NOT NULL), count(*)"
            " FROM lexeme WHERE dataset = %s",
            (DATASET,),
        )
        entries, total = cur.fetchone()
        stats.update(entries=entries, template_terms=total - entries)
        # languages left over from earlier imports (e.g. codes now mapped to the config)
        cur.execute(
            """DELETE FROM language_alias a WHERE a.language_id LIKE 'wkt-%%'
               AND NOT EXISTS (SELECT 1 FROM lexeme l WHERE l.language_id = a.language_id)"""
        )
        cur.execute(
            """DELETE FROM language g WHERE g.id LIKE 'wkt-%%'
               AND NOT EXISTS (SELECT 1 FROM lexeme l WHERE l.language_id = g.id)"""
        )

        # An unmarked {{desc}} line on the parent's page only defaults to "inherited". Where the
        # descendant's own entry says more, that wins; where two statements contradict, no link
        # is better than a wrong one. Pairs are aggregated first so no step is a nested loop.
        cur.execute(
            """
            CREATE TEMP TABLE wkt_pair ON COMMIT DROP AS
            SELECT child_lid, parent_lid,
                bool_or(type_id IN ('borrowed_from', 'etymon', 'calque_or_loan_translation'))
                    AS other_type,
                bool_or(template <> 'desc' AND type_id = 'inherited_form') AS own_inherited,
                bool_or(type_id = 'borrowed_from') AS borrowed
            FROM wkt_edge
            WHERE type_id IN ('inherited_form', 'borrowed_from', 'etymon',
                              'calque_or_loan_translation')
            GROUP BY child_lid, parent_lid
            """
        )
        cur.execute(
            """
            CREATE TEMP TABLE wkt_drop ON COMMIT DROP AS
            -- the default "inherited" yields to any other statement about the same pair
            SELECT e.seq, 'default_inherited' AS why
            FROM wkt_edge e JOIN wkt_pair p USING (child_lid, parent_lid)
            WHERE e.template = 'desc' AND e.type_id = 'inherited_form' AND p.other_type
            UNION
            -- the parent's marked-borrowed line yields to the child's own "inherited" template
            SELECT e.seq, 'marked_vs_own_inherited'
            FROM wkt_edge e JOIN wkt_pair p USING (child_lid, parent_lid)
            WHERE e.template = 'desc'
              AND e.type_id IN ('borrowed_from', 'calque_or_loan_translation')
              AND p.own_inherited
            UNION
            -- mutual "inherited" pairs: each page lists the other as its descendant
            SELECT a.seq, 'mutual'
            FROM wkt_edge a JOIN wkt_edge b
              ON a.child_lid = b.parent_lid AND a.parent_lid = b.child_lid
            WHERE a.type_id = 'inherited_form' AND b.type_id = 'inherited_form'
              AND a.template = 'desc'
            """
        )
        cur.execute(
            """
            CREATE TEMP TABLE wkt_retype ON COMMIT DROP AS
            SELECT DISTINCT e.seq, 'desc' AS kind
            FROM wkt_edge e
            JOIN wkt_term t ON t.lid = e.child_lid AND t.is_entry AND t.borrowed_text
            LEFT JOIN wkt_drop d ON d.seq = e.seq
            WHERE e.template = 'desc' AND e.type_id = 'inherited_form' AND d.seq IS NULL
            UNION
            -- a {{der}} link whose entry text names its target as the donor; skipped when
            -- another statement already types the same pair as borrowed
            -- (every copy of the link, e.g. the same pair in {{der}} and {{ety}}, is retyped)
            SELECT e.seq, 'der'
            FROM wkt_edge e
            JOIN wkt_edge f ON f.rid = e.rid
            JOIN wkt_textcand c ON c.seq = f.seq
            JOIN wkt_pair p ON p.child_lid = e.child_lid AND p.parent_lid = e.parent_lid
            WHERE e.type_id = 'etymon' AND NOT p.borrowed
            """
        )
        cur.execute("SELECT why, count(*) FROM wkt_drop GROUP BY why")
        for why, n in cur.fetchall():
            stats[f"links_dropped:{why}"] = n
        cur.execute("SELECT kind, count(*) FROM wkt_retype GROUP BY kind")
        kinds = dict(cur.fetchall())
        stats["links_retyped_borrowed_by_etymology_text"] = kinds.get("desc", 0)
        stats["links_retyped_der_by_etymology_text"] = kinds.get("der", 0)
        cur.execute(
            """
            CREATE TEMP TABLE wkt_rel ON COMMIT DROP AS
            SELECT DISTINCT ON (e.rid) e.seq, e.rid, e.child_lid, e.parent_lid,
                CASE WHEN r.seq IS NOT NULL THEN 'borrowed_from' ELSE e.type_id END AS type_id,
                e.directed, e.record,
                CASE WHEN r.seq IS NOT NULL
                     THEN '{{' || e.template || '}} + entry etymology text'
                     ELSE e.label END AS label,
                e.rank, e.word,
                CASE WHEN r.seq IS NOT NULL THEN 'etymtext' ELSE e.template END AS template
            FROM wkt_edge e
            LEFT JOIN wkt_drop d ON d.seq = e.seq
            LEFT JOIN wkt_retype r ON r.seq = e.seq
            WHERE d.seq IS NULL
            ORDER BY e.rid, (e.template = 'desc'), e.seq
            """
        )
        cur.execute(
            """
            INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,
                status, source_id, source_record_id, original_label, rank, dataset,
                import_batch_id)
            SELECT rid, child_lid, parent_lid, type_id,
                (CASE WHEN directed THEN 'directed' ELSE 'undirected' END)::direction,
                'documented', %(src)s, record, label, rank, %(ds)s, %(batch)s
            FROM wkt_rel
            """,
            {"ds": DATASET, "src": SOURCE_ID, "batch": batch},
        )
        cur.execute(
            """
            INSERT INTO evidence (relationship_id, source_id, citation, locator)
            SELECT rid, %(src)s, 'Wiktionary, “' || word || '”, ' || CASE
                    WHEN template = 'desc' THEN 'descendants'
                    WHEN template = 'etymtext' THEN 'etymology text (borrowing)'
                    ELSE 'etymology (' || CASE type_id
                        WHEN 'inherited_form' THEN 'inherited'
                        WHEN 'borrowed_from' THEN 'borrowed'
                        WHEN 'calque_or_loan_translation' THEN 'calque'
                        WHEN 'cognate' THEN 'cognate'
                        WHEN 'has_component' THEN 'word formation'
                        ELSE 'derived' END || ')'
                    END,
                'https://en.wiktionary.org/wiki/' || replace(word, ' ', '_')
            FROM wkt_rel
            """,
            {"src": SOURCE_ID},
        )
        cur.execute("SELECT type_id, count(*) FROM wkt_rel GROUP BY 1")
        for type_id, n in cur.fetchall():
            stats[type_id] = n
        stats.update(lexemes=total, relationships=sum(stats.get(t, 0) for t in TYPE_IDS))
        cur.execute(
            "DROP TABLE wkt_rel, wkt_retype, wkt_drop, wkt_pair, wkt_edge, wkt_textcand, wkt_term"
        )
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}


TYPE_IDS = (
    "inherited_form",
    "borrowed_from",
    "etymon",
    "calque_or_loan_translation",
    "has_component",
    "cognate",
)
