"""Import the Digital Pāḷi Dictionary (DPD, CC BY-NC-SA 4.0: RESEARCH USE).

From the ``dpd_headwords`` table of the release's SQLite database:

- one Pali lexeme per headword (homonym numbers such as "dhamma 1.01" are dropped and the
  senses of homonyms combined), glossed with ``meaning_1`` or ``meaning_2``;
- ``sanskrit``: the Sanskrit equivalent DPD gives, as ``related_form`` (DPD does not say
  whether the Pali word was inherited from it, so no stronger type is claimed);
- ``derived_from``: the Pali word it is derived from, as ``derived_form``;
- ``compound_construction``: the parts of a compound, as ``has_component``.

Every record cites the DPD headword (its permanent ID) and the release version.
"""

import re
import sqlite3
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.models.enums import Direction, ReconstructionStatus, RelationshipStatus
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "dpd"
PALI, SANSKRIT = "pli", "san"
LEXEME_COLS = (
    "id",
    "language_id",
    "form",
    "normalized_form",
    "search_key",
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
    "dataset",
    "import_batch_id",
)
EVIDENCE_COLS = ("relationship_id", "source_id", "citation", "locator", "evidence_note")

_HOMONYM = re.compile(r"\s+\d+(\.\d+)*$")


def clean_lemma(lemma: str) -> str:
    return _HOMONYM.sub("", lemma.strip())


def sanskrit_equivalent(field: str) -> str | None:
    """'dharma [dhṛ]' -> 'dharma'; 'akarkaśa (na + karkaśa)' -> 'akarkaśa'. Analyses such as
    'na + (kaścid, kiṃcid)' and lists are not single equivalents and are skipped."""
    head = re.split(r"\s*[\[(]", field.strip(), maxsplit=1)[0].strip()
    if not head or "+" in head or "," in head or " " in head:
        return None
    return head


def compound_parts(field: str) -> list[str]:
    first = field.strip().splitlines()[0] if field.strip() else ""
    return [p.strip() for p in first.split("+") if p.strip() and not p.strip().startswith("√")]


def import_dpd(conn: psycopg.Connection, db_path: Path, archive: Path | None, version: str) -> dict:
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = src.execute(
        "SELECT id, lemma_1, meaning_1, meaning_2, sanskrit, derived_from, compound_construction"
        " FROM dpd_headwords ORDER BY id"
    ).fetchall()
    src.close()

    pali: dict[str, dict] = {}  # clean lemma -> {ids, glosses}
    for hid, lemma, m1, m2, *_ in rows:
        key = clean_lemma(lemma)
        if not key:
            continue
        rec = pali.setdefault(key, {"ids": [], "glosses": []})
        rec["ids"].append(hid)
        if m1 or m2:
            rec["glosses"].append(m1 or m2)

    sanskrit: set[str] = set()
    links: dict[str, tuple] = {}
    stats: dict[str, int] = {}

    def bump(k: str) -> None:
        stats[k] = stats.get(k, 0) + 1

    def pali_id(key: str) -> str:
        return lexeme_id(DATASET, f"pli:{key}")

    for hid, lemma, _m1, _m2, skt, derived, compound in rows:
        key = clean_lemma(lemma)
        child = pali_id(key)
        eq = sanskrit_equivalent(skt or "")
        if eq:
            sanskrit.add(eq)
            rid = relationship_id(DATASET, "sanskrit", key, eq)
            links.setdefault(
                rid, (rid, child, lexeme_id(DATASET, f"san:{eq}"), "related_form", hid, "sanskrit")
            )
        if derived and clean_lemma(derived) in pali and clean_lemma(derived) != key:
            parent = clean_lemma(derived)
            rid = relationship_id(DATASET, "derived", key, parent)
            links.setdefault(
                rid, (rid, child, pali_id(parent), "derived_form", hid, "derived_from")
            )
        elif derived:
            bump("derived_from_unmatched")
        for part in compound_parts(compound or ""):
            p = clean_lemma(part)
            if p in pali and p != key:
                rid = relationship_id(DATASET, "component", key, p)
                links.setdefault(
                    rid, (rid, child, pali_id(p), "has_component", hid, "compound_construction")
                )
            else:
                bump("compound_part_unmatched")

    with conn.cursor() as cur:
        checksums = {db_path.name: f"in {archive.name}" if archive else "unpacked"}
        if archive and archive.exists():
            checksums[archive.name] = sha256_file(archive)
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb(checksums),
                psycopg.types.json.Jsonb(
                    [
                        "dpd_headwords: one Pali lexeme per headword, homonyms combined",
                        "sanskrit -> related_form (Sanskrit equivalent; no direction claimed)",
                        "derived_from -> derived_form; compound_construction -> has_component",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))

        lexemes = []
        for key, rec in pali.items():
            gloss = "; ".join(dict.fromkeys(rec["glosses"][:3])) or None
            lexemes.append(
                (
                    pali_id(key),
                    PALI,
                    key,
                    normalize_form(key),
                    lexeme_search_key(key, PALI),
                    key,
                    gloss,
                    form_kind(key).value,
                    ReconstructionStatus.attested.value,
                    DATASET,
                    DATASET,
                    str(rec["ids"][0]),
                    f"DPD headword {rec['ids'][0]}",
                    batch,
                )
            )
        for eq in sorted(sanskrit):
            lexemes.append(
                (
                    lexeme_id(DATASET, f"san:{eq}"),
                    SANSKRIT,
                    eq,
                    normalize_form(eq),
                    lexeme_search_key(eq, SANSKRIT),
                    eq,
                    None,
                    form_kind(eq).value,
                    ReconstructionStatus.attested.value,
                    DATASET,
                    DATASET,
                    f"san:{eq}",
                    "DPD (Sanskrit equivalent)",
                    batch,
                )
            )
        copy_rows(cur, "lexeme", LEXEME_COLS, lexemes)
        rels, evidence = [], []
        for rid, a, b, type_id, hid, field in links.values():
            rels.append(
                (
                    rid,
                    a,
                    b,
                    type_id,
                    Direction.directed.value,
                    RelationshipStatus.documented.value,
                    DATASET,
                    f"headword:{hid}",
                    f"DPD {field}",
                    DATASET,
                    batch,
                )
            )
            evidence.append(
                (rid, DATASET, f"DPD headword {hid} ({field})", f"headword {hid}", None)
            )
            bump(type_id)
        copy_rows(cur, "relationship", REL_COLS, rels)
        copy_rows(cur, "evidence", EVIDENCE_COLS, evidence)
        stats.update(
            pali_lexemes=len(pali), sanskrit_lexemes=len(sanskrit), relationships=len(rels)
        )
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
