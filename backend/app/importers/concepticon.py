"""Load Concepticon concept sets. Concepts align meanings; they never imply shared origin."""

from pathlib import Path

import psycopg

SOURCE_ID = "concepticon"


def concept_id(concepticon_id: str) -> str:
    return f"concepticon:{concepticon_id}"


def import_concepticon(conn: psycopg.Connection, data_dir: Path) -> dict:
    path = data_dir / "concepticondata" / "concepticon.tsv"
    with path.open(encoding="utf-8", newline="") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        missing = {"ID", "GLOSS", "SEMANTICFIELD", "DEFINITION"} - set(header)
        if missing:
            raise ValueError(f"concepticon.tsv: missing columns {sorted(missing)}")
        rows = []
        for line in fh:
            r = dict(zip(header, line.rstrip("\n").split("\t"), strict=False))
            rows.append(
                (
                    concept_id(r["ID"]),
                    r["GLOSS"],
                    r["SEMANTICFIELD"] or None,
                    r["DEFINITION"] or None,
                    SOURCE_ID,
                )
            )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO concept (id, label, category, definition, source_id)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET"
            " label = EXCLUDED.label, category = EXCLUDED.category,"
            " definition = EXCLUDED.definition, source_id = EXCLUDED.source_id",
            rows,
        )
    return {"concepts": len(rows)}


def ensure_concept(cur, concepticon_id: str, gloss: str) -> str:
    """Create a minimal concept row if Concepticon itself has not been imported yet."""
    cid = concept_id(concepticon_id)
    cur.execute(
        "INSERT INTO concept (id, label, source_id) VALUES (%s, %s, %s)"
        " ON CONFLICT (id) DO NOTHING",
        (cid, gloss, SOURCE_ID),
    )
    return cid
