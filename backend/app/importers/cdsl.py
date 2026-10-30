"""Import Monier-Williams' Sanskrit-English Dictionary (1899) from the Cologne Digital Sanskrit
Dictionaries (csl-orig ``v02/mw/mw.txt``).

The digitisation's TEI header states CC BY-NC-SA 3.0, so the dataset is RESEARCH USE. Each
record (``<L>id<pc>page,col<k1>key<k2>key-with-compound-marks...`` up to ``<LEND>``) is
grouped by headword: one Sanskrit lexeme per ``k1`` (SLP1, converted to IAST), glossed
with its first senses, and citing the page and column of the 1899 edition. Compounds that
Monier-Williams marks in ``k2`` (``agni—hotra``) are linked to their parts as
``has_component`` when each part is itself a headword.
"""

import re
from collections import defaultdict
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.models.enums import Direction, ReconstructionStatus, RelationshipStatus
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "cdsl-mw"
LANGUAGE = "san"
CITATION = "Monier-Williams 1899"

_SLP1 = {
    "A": "ā", "I": "ī", "U": "ū", "f": "ṛ", "F": "ṝ", "x": "ḷ", "X": "ḹ", "E": "ai", "O": "au",
    "M": "ṃ", "H": "ḥ", "~": "m̐", "K": "kh", "G": "gh", "N": "ṅ", "C": "ch", "J": "jh",
    "Y": "ñ", "w": "ṭ", "W": "ṭh", "q": "ḍ", "Q": "ḍh", "R": "ṇ", "T": "th", "D": "dh",
    "P": "ph", "B": "bh", "S": "ś", "z": "ṣ", "L": "ḻ", "'": "’",
}  # fmt: skip


def slp1_to_iast(text: str) -> str:
    return "".join(_SLP1.get(ch, ch) for ch in text if ch not in "/\\^")


_HEADER = re.compile(
    r"<L>(?P<L>[^<]+)<pc>(?P<pc>[^<]+)<k1>(?P<k1>[^<]+)<k2>(?P<k2>[^<]+)(?:<h>(?P<h>[^<]+))?"
)


def clean_body(body: str) -> str:
    """Readable gloss text: Sanskrit in IAST, literature references and markup dropped."""
    text = body.split("¦", 1)[-1]
    text = re.sub(r"<s>(.*?)</s>", lambda m: slp1_to_iast(m.group(1)), text)
    text = re.sub(r"<ls[^>]*>.*?</ls>", "", text)
    text = re.sub(r"<info[^>]*/>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    text = re.sub(r"\s+([,.;)])", r"\1", text)
    return re.sub(r"[,;]+([);])", r"\1", text)[:200]


def iter_records(path: Path):
    """(L id, page, column, k1, k2, body) per record."""
    with path.open(encoding="utf-8") as fh:
        header, body = None, []
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("<L>"):
                header, body = _HEADER.match(line), []
            elif line.startswith("<LEND>"):
                if header:
                    page, _, col = header["pc"].partition(",")
                    yield header["L"], page, col, header["k1"], header["k2"], " ".join(body)
                header = None
            elif header:
                body.append(line)


def import_cdsl_mw(conn: psycopg.Connection, path: Path, version: str) -> dict:
    heads: dict[str, dict] = {}
    compounds: dict[str, list[str]] = defaultdict(list)
    for lid, page, col, k1, k2, body in iter_records(path):
        rec = heads.setdefault(k1, {"L": lid, "page": page, "col": col, "glosses": []})
        gloss = clean_body(body)
        if gloss and len(rec["glosses"]) < 3:
            rec["glosses"].append(gloss)
        if "—" in k2 and k1 not in compounds:
            parts = [re.sub(r"[/\\^]", "", p) for p in k2.split("—")]
            if all(parts):
                compounds[k1] = parts

    def lid_of(k1: str) -> str:
        return lexeme_id(DATASET, k1)

    stats: dict[str, int] = {"headwords": len(heads)}
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({path.name: sha256_file(path)}),
                psycopg.types.json.Jsonb(
                    [
                        "One Sanskrit lexeme per k1 headword (SLP1 -> IAST), first 3 senses",
                        "Gloss: markup and literature references stripped, 200 characters",
                        "k2 compound marks -> has_component to parts that are headwords",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))
        lexemes = []
        for k1, rec in heads.items():
            form = slp1_to_iast(k1)
            lexemes.append(
                (
                    lid_of(k1),
                    LANGUAGE,
                    form,
                    normalize_form(form),
                    lexeme_search_key(form, LANGUAGE),
                    form,
                    "; ".join(rec["glosses"]) or None,
                    form_kind(form, k1 in compounds).value,
                    ReconstructionStatus.attested.value,
                    DATASET,
                    DATASET,
                    rec["L"],
                    f"{CITATION}, p. {rec['page']}, col. {rec['col']}",
                    batch,
                )
            )
        copy_rows(
            cur,
            "lexeme",
            (
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
            ),
            lexemes,
        )
        rels, evidence = [], []
        for k1, parts in compounds.items():
            rec = heads[k1]
            for part in dict.fromkeys(parts):
                if part not in heads or part == k1:
                    stats["compound_part_not_headword"] = (
                        stats.get("compound_part_not_headword", 0) + 1
                    )
                    continue
                rid = relationship_id(DATASET, "component", k1, part)
                rels.append(
                    (
                        rid,
                        lid_of(k1),
                        lid_of(part),
                        "has_component",
                        Direction.directed.value,
                        RelationshipStatus.documented.value,
                        DATASET,
                        f"L{rec['L']}",
                        "compound (k2)",
                        DATASET,
                        batch,
                    )
                )
                evidence.append(
                    (
                        rid,
                        DATASET,
                        f"{CITATION}, s.v. {slp1_to_iast(k1)}",
                        f"p. {rec['page']}, col. {rec['col']}",
                        None,
                    )
                )
        copy_rows(
            cur,
            "relationship",
            (
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
            ),
            rels,
        )
        copy_rows(
            cur,
            "evidence",
            ("relationship_id", "source_id", "citation", "locator", "evidence_note"),
            evidence,
        )
        stats.update(lexemes=len(lexemes), relationships=len(rels))
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
