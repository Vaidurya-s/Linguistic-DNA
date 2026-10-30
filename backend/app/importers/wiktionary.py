"""Import Wiktionary entries and their etymologies from wiktextract JSONL (kaikki.org).

Each configured language lists its Wiktionary codes in data/config/languages.csv
(``wiktionary_codes``). For every entry in those languages we keep the headword, up to three
English glosses and the romanisation, and turn its etymology templates into documented,
typed relationships:

    inh, inh+            -> inherited_form   (entry -> ancestor)
    bor, bor+, lbor, ... -> borrowed_from    (entry -> donor)
    der, der+            -> etymon           (Wiktionary does not say inherited or borrowed)
    clq, cal, calque     -> calque_or_loan_translation
    af, affix, compound, prefix, suffix, confix -> has_component (entry -> part)
    cog                  -> cognate          (undirected; the editors' claim)

Terms that templates point to but that have no entry here (e.g. a Sanskrit etymon, an
Arabic donor) are created from the template itself, in their own language. Languages that
are not configured become disabled reference languages ``wkt-<code>``, ready to be enabled
by adding the code to the config later. Every edge cites the Wiktionary page it comes from.
"""

import gzip
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.models.enums import Direction, ReconstructionStatus, RelationshipStatus
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

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
}
COMPONENT = {"af", "affix", "compound", "com", "prefix", "pre", "suffix", "suf", "confix", "con"}
COGNATE = {"cog", "cognate"}

LEXEME_COLS = (
    "id",
    "language_id",
    "form",
    "normalized_form",
    "search_key",
    "native_form",
    "native_form_origin",
    "transliteration",
    "gloss",
    "form_kind",
    "reconstruction_status",
    "dataset",
    "source_id",
    "source_record_id",
    "source_citation",
    "import_batch_id",
)
REL_COLS = (
    "id",
    "source_lexeme_id",
    "target_lexeme_id",
    "type_id",
    "direction",
    "status",
    "source_id",
    "source_record_id",
    "original_label",
    "rank",
    "notes",
    "dataset",
    "import_batch_id",
)
EVIDENCE_COLS = ("relationship_id", "source_id", "citation", "locator", "evidence_note")


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


def template_edges(entry: dict, child_key: str, code: str) -> Iterator[tuple[Edge, Term]]:
    """(edge, other term) pairs from one entry's etymology templates."""
    for rank, t in enumerate(entry.get("etymology_templates") or [], start=1):
        name, args = t.get("name", ""), t.get("args") or {}
        if name in DIRECTED and args.get("1") == code:
            raw_src, term = args.get("2", ""), args.get("3", "")
            src = ETYMOLOGY_ONLY.get(raw_src, raw_src)
            gloss = args.get("t") or args.get("gloss") or args.get("5")
            if src and term and term != "-":
                yield (
                    Edge(
                        child_key,
                        term_key(src, term),
                        DIRECTED[name],
                        name,
                        entry["word"],
                        rank,
                        variety=raw_src if raw_src != src else "",
                    ),
                    Term(src, term, gloss or None, args.get("tr") or None),
                )
        elif name in COMPONENT and args.get("1") == code:
            parts = [args[k] for k in sorted((k for k in args if k.isdigit()), key=int)][1:]
            for part in parts:
                if not part or part == "-":
                    continue
                src, _, term = part.rpartition(":") if ":" in part[:12] else ("", "", part)
                src = src or code
                yield (
                    Edge(
                        child_key, term_key(src, term), "has_component", name, entry["word"], rank
                    ),
                    Term(src, term),
                )
        elif name in COGNATE:
            src = ETYMOLOGY_ONLY.get(args.get("1", ""), args.get("1", ""))
            term = args.get("2", "")
            if src and term and term != "-":
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
                    Term(src, term, args.get("t") or args.get("4") or None, args.get("tr") or None),
                )


def romanization(entry: dict) -> str | None:
    for f in entry.get("forms") or []:
        if "romanization" in (f.get("tags") or []):
            return f.get("form")
    return None


def entry_glosses(entry: dict) -> list[str]:
    out = []
    for s in entry.get("senses") or []:
        out.extend(g for g in s.get("glosses") or [] if g)
    return out


def wiktionary_code_map() -> dict[str, str]:
    """Wiktionary language code -> configured language id, from data/config/languages.csv."""
    from app.importers.jambu import load_languages

    return {code: t.id for t in load_languages() for code in t.wiktionary_codes.split(";") if code}


def import_wiktionary(
    conn: psycopg.Connection,
    files: Iterable[Path],
    version: str,
    code_map: dict[str, str],
    language_names: dict[str, str] | None = None,
    reference_codes: Iterable[str] = (),
) -> dict:
    """code_map: Wiktionary code -> configured language id (the entry languages).

    reference_codes: further languages (e.g. Prakrit, Proto-Indo-Aryan) whose own entries
    are imported too, as disabled reference languages, so etymology chains continue."""
    files = list(files)
    names = dict(language_names or {})
    stats: dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        stats[k] = stats.get(k, 0) + n

    wanted = set(code_map) | set(reference_codes)
    terms: dict[str, Term] = {}
    edges: list[Edge] = []
    for path in files:
        for e in iter_jsonl(path, wanted, names):
            code, word = e.get("lang_code"), e.get("word")
            if not word or code not in wanted:
                continue
            names.setdefault(code, e.get("lang") or code)
            key = term_key(code, word)
            t = terms.get(key)
            if not t or not t.is_entry:
                t = terms[key] = Term(code, word, is_entry=True)
            t.glosses.extend(entry_glosses(e))
            t.roman = t.roman or romanization(e)
            for edge, other in template_edges(e, key, code):
                if edge.parent == key:
                    continue
                edges.append(edge)
                known = terms.get(edge.parent)
                if not known:
                    terms[edge.parent] = other
                elif not known.is_entry:
                    known.gloss = known.gloss or other.gloss
                    known.roman = known.roman or other.roman
                bump(f"template:{edge.template}")

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({p.name: sha256_file(p) for p in files}),
                psycopg.types.json.Jsonb(
                    [
                        "wiktextract JSONL entries for the configured languages' Wiktionary codes",
                        "Entries in reference (ancestor) languages imported as disabled languages",
                        "One record per language and headword; up to three English glosses",
                        "Etymology templates -> typed relationships (see module docstring)",
                        "Template targets without an entry created from the template",
                        "Unconfigured languages filed as disabled reference languages wkt-<code>",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))

        def language_of(code: str) -> str:
            return code_map.get(code) or f"wkt-{code.lower()}"

        for code in sorted({t.code for t in terms.values()} - set(code_map)):
            name = names.get(code, code)
            cur.execute(
                "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
                " VALUES (%s, %s, 'other', %s, false, %s) ON CONFLICT (id) DO UPDATE SET"
                " name = EXCLUDED.name, is_proto = EXCLUDED.is_proto",
                (
                    language_of(code),
                    name,
                    code.endswith("-pro") or name.startswith("Proto-"),
                    psycopg.types.json.Jsonb({"wiktionary": code}),
                ),
            )
            cur.execute(
                "INSERT INTO language_alias (language_id, scheme, value) VALUES (%s, 'wiktionary',"
                " %s) ON CONFLICT DO NOTHING",
                (language_of(code), code),
            )

        lexemes = []
        for key, t in terms.items():
            form = t.form.strip()
            if not form:
                continue
            lang = language_of(t.code)
            gloss = "; ".join(dict.fromkeys(t.glosses[:3])) if t.glosses else t.gloss
            reconstructed = form.startswith("*") or t.code.endswith("-pro")
            status = (
                ReconstructionStatus.reconstructed
                if reconstructed
                else ReconstructionStatus.attested
                if t.is_entry
                else ReconstructionStatus.unknown
            )
            lexemes.append(
                (
                    lexeme_id(DATASET, key),
                    lang,
                    form,
                    normalize_form(form),
                    lexeme_search_key(form, lang),
                    form,
                    "source",
                    t.roman,
                    gloss,
                    form_kind(form, False).value,
                    status.value,
                    DATASET,
                    SOURCE_ID,
                    key,
                    f"Wiktionary, “{form}”" if t.is_entry else None,
                    batch,
                )
            )
            bump("entries" if t.is_entry else "template_terms")
        copy_rows(cur, "lexeme", LEXEME_COLS, lexemes)

        rels, evidence = {}, []
        for edge in edges:
            if edge.type_id == "cognate":
                a, b = sorted((edge.child, edge.parent))
                rid = relationship_id(DATASET, "cognate", a, b)
            else:
                a, b = edge.child, edge.parent
                rid = relationship_id(DATASET, edge.type_id, a, b)
            if rid in rels:
                continue
            rels[rid] = (
                rid,
                lexeme_id(DATASET, a),
                lexeme_id(DATASET, b),
                edge.type_id,
                (Direction.directed if edge.directed else Direction.undirected).value,
                RelationshipStatus.documented.value,
                SOURCE_ID,
                f"{edge.word}#{edge.template}",
                f"{{{{{edge.template}}}}}" + (f" ({edge.variety})" if edge.variety else ""),
                edge.rank,
                None,
                DATASET,
                batch,
            )
            evidence.append(
                (
                    rid,
                    SOURCE_ID,
                    f"Wiktionary, “{edge.word}”, etymology ({{{{{edge.template}}}}})",
                    page_url(edge.word),
                    None,
                )
            )
            bump(edge.type_id)
        copy_rows(cur, "relationship", REL_COLS, rels.values())
        copy_rows(cur, "evidence", EVIDENCE_COLS, evidence)
        stats.update(lexemes=len(lexemes), relationships=len(rels))
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
