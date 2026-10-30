"""Import the Sanskrit lexicon of the Digital Corpus of Sanskrit (DCS, CC BY 4.0).

``dcs/data/conllu/lookup/dictionary.csv`` (tab-separated: id, word, grammar, preverbs,
meanings) lists every lemma annotated in the corpus, in IAST, with English meanings. Each
lemma becomes a Sanskrit lexeme citing its permanent DCS lexicon ID. The file states no
word-to-word relationships, so none are created.
"""

import csv
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.models.enums import ReconstructionStatus
from app.services.ids import lexeme_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "dcs"
LANGUAGE = "san"
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
    "tags",
    "dataset",
    "source_id",
    "source_record_id",
    "source_citation",
    "import_batch_id",
)


def import_dcs(conn: psycopg.Connection, dictionary: Path, version: str) -> dict:
    stats = {"lexemes": 0, "skipped_empty": 0}
    rows = []
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({dictionary.name: sha256_file(dictionary)}),
                psycopg.types.json.Jsonb(
                    [
                        "lookup/dictionary.csv: one Sanskrit lexeme per DCS lemma (IAST)",
                        "Gloss: the DCS 'meanings' field; grammar kept as a tag",
                        "No relationships (none are stated in the file)",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))
        with dictionary.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                word = (r.get("word") or "").strip()
                if not word:
                    stats["skipped_empty"] += 1
                    continue
                grammar = (r.get("grammar") or "").strip()
                rows.append(
                    (
                        lexeme_id(DATASET, r["id"]),
                        LANGUAGE,
                        word,
                        normalize_form(word),
                        lexeme_search_key(word, LANGUAGE),
                        word,
                        (r.get("meanings") or "").strip() or None,
                        form_kind(word).value,
                        ReconstructionStatus.attested.value,
                        [f"pos:{grammar}"] if grammar else None,
                        DATASET,
                        DATASET,
                        r["id"],
                        f"DCS lexicon {r['id']}",
                        batch,
                    )
                )
        copy_rows(cur, "lexeme", LEXEME_COLS, rows)
        stats["lexemes"] = len(rows)
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
