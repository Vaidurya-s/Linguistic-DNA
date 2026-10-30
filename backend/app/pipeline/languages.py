"""One language, one record, for every language in the world.

Sources name languages their own way: Jambu IDs (``jb-``), Wiktionary codes (``wkt-``),
Wikidata items (``wd-``), CLDF glottocodes (``gl-``). After the imports:

1. ``import_glottolog_languages`` creates a ``gl-<glottocode>`` row for every Glottolog
   language (about 8,600), classified into Glottolog's families, unless a configured
   language already has that glottocode.
2. ``canonicalize_languages`` maps each source-specific row to its glottocode: its own
   ``glottocode`` (Glottolog dialects resolve to their language), or its Wiktionary/ISO code
   via ISO 639-1 -> 639-3 -> glottocode. The row's words move to the configured language with
   that glottocode, or to ``gl-<glottocode>``; the old row survives as a *variety*, so dialect
   and source detail is kept. A glottocode that several configured languages share (Sanskrit
   and the CDIAL headword layer) is ambiguous and never merged.
3. ``refresh_language_stats`` computes word counts once, and ``enable_searchable`` makes a
   language searchable when it has enough attested words.
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import psycopg

from app.importers.common import read_csv
from app.importers.jambu import load_languages

# Rows that may stand for another language's record. "gl-" rows created by a CLDF import
# for a *dialect* glottocode merge into their language's record; language-level gl- rows
# map to themselves and are left alone.
SOURCE_PREFIXES = ("jb-", "wkt-", "wd-", "gl-")
# A historical stage (Old Hindi, Middle Bengali) often carries its modern language's
# glottocode; it may only merge into a language that is itself historical (Glottolog's
# "Old Marathi"), never into the modern language.
_HISTORICAL = re.compile(
    r"^(old|middle|early|late|classical|ancient|archaic|epic|vedic|medieval|proto)\b|prakrit|apabhra",
    re.IGNORECASE,
)


def is_historical(name: str) -> bool:
    return bool(_HISTORICAL.search(name or ""))


# Macrolanguage codes that Wiktionary uses for one main member language.
MACROLANGUAGE_MEMBER = {
    "ara": "arb",  # Arabic -> Standard Arabic
    "fas": "pes",  # Persian -> Iranian Persian
    "zho": "cmn",  # Chinese -> Mandarin
    "msa": "zsm",  # Malay -> Standard Malay
    "swa": "swh",  # Swahili
    "est": "ekk",  # Estonian -> Standard Estonian
    "lav": "lvs",  # Latvian -> Standard Latvian
    "nor": "nob",  # Norwegian -> Bokmål
    "uzb": "uzn",  # Uzbek -> Northern Uzbek
    "pus": "pbu",  # Pashto -> Northern Pashto
    "aze": "azj",  # Azerbaijani -> North Azerbaijani
    "mon": "khk",  # Mongolian -> Halh Mongolian
    "sqi": "als",  # Albanian -> Tosk Albanian
    "kur": "kmr",  # Kurdish -> Northern Kurdish
    "fas-cls": "pes",
    "nep": "npi",  # Nepali (macro) -> Nepali
    "ori": "ory",
    "kok": "gom",  # Konkani -> Goan Konkani
    "raj": "mwr",
}


def iso_tables(tab: Path) -> tuple[dict[str, str], set[str]]:
    """(ISO 639-1 -> 639-3, set of 639-3 codes) from SIL's iso-639-3.tab."""
    part1, codes = {}, set()
    with tab.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            codes.add(r["Id"])
            if r["Part1"]:
                part1[r["Part1"]] = r["Id"]
    return part1, codes


class Glottolog:
    def __init__(self, cldf_dir: Path):
        self.languoids = {
            r["ID"]: r
            for r in read_csv(cldf_dir / "languages.csv", ("ID", "Name", "Level", "ISO639P3code"))
        }
        self.by_iso = {
            r["ISO639P3code"]: gc for gc, r in self.languoids.items() if r["ISO639P3code"]
        }
        self.paths: dict[str, list[str]] = {}
        for r in read_csv(cldf_dir / "values.csv", ("Language_ID", "Parameter_ID", "Value")):
            if r["Parameter_ID"] == "classification" and r["Value"]:
                self.paths[r["Language_ID"]] = r["Value"].split("/")

    def language_of(self, glottocode: str | None) -> str | None:
        """The language-level glottocode for a language or dialect glottocode."""
        row = self.languoids.get(glottocode or "")
        if not row:
            return None
        if row["Level"] == "language":
            return glottocode
        if row["Level"] == "dialect" and row.get("Language_ID"):
            return row["Language_ID"]
        return None  # families are not languages


def import_glottolog_languages(conn: psycopg.Connection, glottolog: Glottolog) -> dict:
    configured = {c for t in load_languages() for c in t.glottocodes}
    families: dict[str, tuple[str, str | None]] = {}
    for code, row in glottolog.languoids.items():
        if row["Level"] != "language":
            continue
        parent = None
        for node in glottolog.paths.get(code, []):
            info = glottolog.languoids.get(node, {"Name": node, "Level": "family"})
            families.setdefault(node, (info["Name"], parent))
            parent = node
    created = 0
    with conn.cursor() as cur:
        # parents before children: insert in path order
        for node, (name, parent) in families.items():
            cur.execute(
                "INSERT INTO language_family (id, name, level, parent_id, source_id)"
                " VALUES (%s, %s, 'family', %s, 'glottolog') ON CONFLICT (id) DO NOTHING",
                (node, name, parent),
            )
        for code, row in glottolog.languoids.items():
            if row["Level"] != "language" or code in configured:
                continue
            path = glottolog.paths.get(code, [])
            top = glottolog.languoids.get(path[0], {}).get("Name") if path else None
            cur.execute(
                """INSERT INTO language (id, name, iso_code, glottocode, family_id,
                       classification_parent_id, role, is_proto, is_enabled, metadata_json)
                   VALUES (%s, %s, %s, %s, %s, %s, 'other', false, false, %s)
                   ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name,
                       iso_code = EXCLUDED.iso_code, family_id = EXCLUDED.family_id,
                       classification_parent_id = EXCLUDED.classification_parent_id,
                       metadata_json = language.metadata_json || EXCLUDED.metadata_json""",
                (
                    f"gl-{code}",
                    row["Name"],
                    row["ISO639P3code"] or None,
                    code,
                    path[0] if path else None,
                    path[-1] if path else None,
                    json.dumps(
                        {"group": top or "Isolate or unclassified", "classification_path": path}
                    ),
                ),
            )
            created += cur.rowcount
    return {"families": len(families), "glottolog_languages": created}


def canonical_targets(conn: psycopg.Connection) -> dict[str, str]:
    """language-level glottocode -> the one language row that represents it."""
    by_code: dict[str, list[str]] = defaultdict(list)
    for t in load_languages():
        for c in t.glottocodes:
            by_code[c].append(t.id)
    out = {c: ids[0] for c, ids in by_code.items() if len(ids) == 1}
    ambiguous = {c for c, ids in by_code.items() if len(ids) > 1}
    with conn.cursor() as cur:
        cur.execute("SELECT id, glottocode FROM language WHERE id LIKE 'gl-%%'")
        for lid, code in cur.fetchall():
            if code not in out and code not in ambiguous:
                out[code] = lid
    return out


def resolve_glottocode(
    row_glottocode: str | None,
    aliases: list[tuple[str, str]],
    glottolog: Glottolog,
    part1: dict[str, str],
) -> str | None:
    code = glottolog.language_of(row_glottocode)
    if code:
        return code
    for scheme, value in aliases:
        if scheme not in ("wiktionary", "iso639-3"):
            continue
        iso = part1.get(value, value)
        iso = MACROLANGUAGE_MEMBER.get(iso, iso)
        if iso in glottolog.by_iso:
            return glottolog.language_of(glottolog.by_iso[iso])
    return None


def split_historical_stages(conn: psycopg.Connection) -> int:
    """Undo merges of a historical stage into a modern language (idempotent repair)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT v.id, v.name, g.name FROM variety v JOIN language g ON g.id = v.language_id
               WHERE v.region_description LIKE 'as named by its source%%'"""
        )
        wrong = [
            (vid, name)
            for vid, name, target in cur.fetchall()
            if is_historical(name) and not is_historical(target)
        ]
        for vid, name in wrong:
            cur.execute(
                "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
                " VALUES (%s, %s, 'other', false, false, %s) ON CONFLICT (id) DO NOTHING",
                (vid, name, json.dumps({"split_from_modern_language": True})),
            )
            cur.execute(
                "UPDATE lexeme SET language_id = %s, variety_id = NULL WHERE variety_id = %s",
                (vid, vid),
            )
            cur.execute("DELETE FROM variety WHERE id = %s", (vid,))
    return len(wrong)


def canonicalize_languages(
    conn: psycopg.Connection, glottolog: Glottolog, part1: dict[str, str]
) -> dict:
    targets = canonical_targets(conn)
    stats = {"merged_languages": 0, "moved_lexemes": 0, "unresolved": 0, "kept_historical": 0}
    stats["historical_stages_split"] = split_historical_stages(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM language")
        names = dict(cur.fetchall())
        cur.execute(
            "SELECT id, name, glottocode FROM language WHERE "
            + " OR ".join("id LIKE %s" for _ in SOURCE_PREFIXES),
            [p + "%" for p in SOURCE_PREFIXES],
        )
        rows = cur.fetchall()
        cur.execute("SELECT language_id, scheme, value FROM language_alias")
        aliases: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for lid, scheme, value in cur.fetchall():
            aliases[lid].append((scheme, value))
        for lid, name, glottocode in rows:
            code = resolve_glottocode(glottocode, aliases[lid], glottolog, part1)
            target = targets.get(code or "")
            if not target or target == lid:
                stats["unresolved"] += 1
                continue
            if is_historical(name) and not is_historical(names.get(target, "")):
                stats["kept_historical"] += 1
                continue
            variety = f"{lid}"
            cur.execute(
                "INSERT INTO variety (id, language_id, name, region_description)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET"
                " language_id = EXCLUDED.language_id, name = EXCLUDED.name",
                (variety, target, name, f"as named by its source ({lid})"),
            )
            cur.execute(
                "UPDATE lexeme SET language_id = %s, variety_id = coalesce(variety_id, %s)"
                " WHERE language_id = %s",
                (target, variety, lid),
            )
            stats["moved_lexemes"] += cur.rowcount
            cur.execute(
                "UPDATE transliteration_alias SET language_id = %s WHERE language_id = %s",
                (target, lid),
            )
            cur.execute("UPDATE variety SET language_id = %s WHERE language_id = %s", (target, lid))
            cur.execute(
                "INSERT INTO language_alias (language_id, scheme, value)"
                " SELECT %s, scheme, value FROM language_alias WHERE language_id = %s"
                " ON CONFLICT DO NOTHING",
                (target, lid),
            )
            cur.execute("DELETE FROM language WHERE id = %s", (lid,))
            stats["merged_languages"] += 1
    return stats


def refresh_language_stats(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM language_stats")
        cur.execute("""
            WITH open AS (
                SELECT id FROM dataset_audit
                WHERE decision IN ('APPROVED', 'APPROVED WITH CONDITIONS')
            ), linked AS (
                SELECT source_lexeme_id AS id FROM relationship
                UNION SELECT target_lexeme_id FROM relationship
            )
            INSERT INTO language_stats (language_id, lexeme_count, linked_count,
                                        open_lexeme_count, open_linked_count)
            SELECT l.language_id, count(*), count(k.id),
                   count(*) FILTER (WHERE l.dataset IN (SELECT id FROM open)),
                   count(k.id) FILTER (WHERE l.dataset IN (SELECT id FROM open))
            FROM lexeme l LEFT JOIN linked k ON k.id = l.id
            GROUP BY l.language_id""")
        return cur.rowcount


def enable_searchable(conn: psycopg.Connection, min_words: int = 200) -> int:
    """Glottolog languages with enough words become searchable; configured languages always
    are; source-specific leftovers and proto-languages never are."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE language g SET is_enabled = (s.lexeme_count >= %s)
               FROM language_stats s
               WHERE s.language_id = g.id AND g.id LIKE 'gl-%%' AND NOT g.is_proto""",
            (min_words,),
        )
        cur.execute("SELECT count(*) FROM language WHERE id LIKE 'gl-%%' AND is_enabled")
        return cur.fetchone()[0]
