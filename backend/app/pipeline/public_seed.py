"""Build and load the public seed: only rows whose dataset and source the audit approves.

The seed is a set of CSV files plus ATTRIBUTION.md and manifest.json. It is the only data a
public deployment may load (docs/DATASET_LICENCE_AUDIT.md).
"""

import hashlib
import json
from pathlib import Path

import psycopg

from app.config import REPO_ROOT

SEED_DIR = REPO_ROOT / "data" / "public_seed"
OK = "('APPROVED', 'APPROVED WITH CONDITIONS')"

# Scratch tables of exported keys are built first so every export is consistent.
SELECTION = f"""
CREATE TEMP TABLE ok_dataset ON COMMIT DROP AS
    SELECT id FROM dataset_audit WHERE decision IN {OK};
CREATE TEMP TABLE ok_source ON COMMIT DROP AS
    SELECT s.id FROM source s JOIN ok_dataset d ON d.id = s.dataset_id;
CREATE TEMP TABLE ok_lexeme ON COMMIT DROP AS
    SELECT l.id FROM lexeme l
    JOIN ok_dataset d ON d.id = l.dataset JOIN ok_source s ON s.id = l.source_id;
CREATE TEMP TABLE ok_relationship ON COMMIT DROP AS
    SELECT r.id FROM relationship r
    JOIN ok_dataset d ON d.id = r.dataset JOIN ok_source s ON s.id = r.source_id
    WHERE r.source_lexeme_id IN (SELECT id FROM ok_lexeme)
      AND r.target_lexeme_id IN (SELECT id FROM ok_lexeme)
      AND NOT EXISTS (SELECT 1 FROM evidence e WHERE e.relationship_id = r.id
                      AND e.source_id NOT IN (SELECT id FROM ok_source));
CREATE TEMP TABLE ok_language ON COMMIT DROP AS
    SELECT id FROM language WHERE is_enabled
    UNION SELECT DISTINCT language_id FROM lexeme WHERE id IN (SELECT id FROM ok_lexeme);
"""

USED_DATASETS = """
SELECT d.id, d.name, d.component, d.version, d.licence_name, d.licence_url,
       d.attribution_text, d.share_alike
FROM dataset_audit d
WHERE d.id IN (SELECT id FROM ok_dataset) AND d.id IN (
    SELECT dataset FROM lexeme WHERE id IN (SELECT id FROM ok_lexeme)
    UNION SELECT s.dataset_id FROM source s WHERE s.id IN (
        SELECT source_id FROM concept UNION SELECT source_id FROM language_family))
ORDER BY d.id
"""

# (table, query) in load order. Columns are listed so the seed's shape is explicit.
TABLES = [
    ("dataset_audit", "SELECT * FROM dataset_audit WHERE id IN (SELECT id FROM ok_dataset)"),
    (
        "source",
        "SELECT id, title, author_or_editor, url, publication_year, version_or_release,"
        " licence_name, licence_url, reuse_status, attribution_text, transliteration_scheme,"
        " NULL AS parent_source_id, notes, dataset_id FROM source"
        " WHERE id IN (SELECT id FROM ok_source)",
    ),
    ("language_family", "SELECT id, name, level, parent_id, source_id FROM language_family"),
    ("language", "SELECT * FROM language WHERE id IN (SELECT id FROM ok_language)"),
    (
        "language_alias",
        "SELECT language_id, scheme, value FROM language_alias"
        " WHERE language_id IN (SELECT id FROM ok_language) AND scheme <> 'jambu'",
    ),
    (
        "language_script",
        "SELECT language_id, script_id, is_primary, NULL AS source_id"
        " FROM language_script WHERE language_id IN (SELECT id FROM ok_language)",
    ),
    ("variety", "SELECT * FROM variety WHERE source_id IN (SELECT id FROM ok_source)"),
    (
        "lexeme",
        "SELECT id, language_id, variety_id, form, normalized_form, search_key, lemma,"
        " native_form, native_form_origin, transliteration, phonemic, ipa, gloss, form_kind,"
        " reconstruction_status, source_status, tags, dataset, source_id, source_record_id,"
        " source_citation, NULL AS import_batch_id FROM lexeme"
        " WHERE id IN (SELECT id FROM ok_lexeme)",
    ),
    (
        "concept",
        "SELECT * FROM concept WHERE id IN (SELECT concept_id FROM lexeme_concept"
        " WHERE lexeme_id IN (SELECT id FROM ok_lexeme))"
        " AND source_id IN (SELECT id FROM ok_source)",
    ),
    (
        "lexeme_concept",
        "SELECT * FROM lexeme_concept WHERE lexeme_id IN (SELECT id FROM ok_lexeme)"
        " AND source_id IN (SELECT id FROM ok_source)",
    ),
    (
        "relationship",
        "SELECT id, source_lexeme_id, target_lexeme_id, type_id, direction, status,"
        " source_id, source_record_id, original_label, source_confidence, method, score, rank,"
        " notes, dataset, NULL AS import_batch_id FROM relationship"
        " WHERE id IN (SELECT id FROM ok_relationship)",
    ),
    (
        "evidence",
        "SELECT relationship_id, source_id, citation, locator, evidence_note"
        " FROM evidence WHERE relationship_id IN (SELECT id FROM ok_relationship)",
    ),
]


def build_public_seed(conn: psycopg.Connection, out: Path = SEED_DIR) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(SELECTION)
        for table, query in TABLES:
            path = out / f"{table}.csv"
            with (
                path.open("wb") as fh,
                cur.copy(
                    f"COPY ({query} ORDER BY 1) TO STDOUT WITH (FORMAT csv, HEADER true)"
                ) as copy,
            ):
                for chunk in copy:
                    fh.write(chunk)
            counts[table] = sum(1 for _ in path.open(encoding="utf-8")) - 1
        cur.execute(USED_DATASETS)
        used = cur.fetchall()
    (out / "ATTRIBUTION.md").write_text(attribution(used), encoding="utf-8")
    manifest = {
        "tables": counts,
        "sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.csv"))
        },
        "datasets": [u[0] for u in used],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def attribution(rows: list[tuple]) -> str:
    lines = [
        "# Data attribution",
        "",
        "This public seed contains only records from datasets that",
        "`data/manifests/dataset_audit.csv` marks APPROVED or APPROVED WITH CONDITIONS.",
        "Generated by `python -m app.cli build-public-seed`; do not edit by hand.",
        "",
    ]
    for did, name, component, version, lic, lic_url, attr, share_alike in rows:
        title = name + (f" ({component})" if component else "")
        lines += [
            f"## {title}",
            "",
            f"- Dataset ID: `{did}`",
            f"- Version: {version or 'n/a'}",
            f"- Licence: [{lic}]({lic_url})" if lic_url else f"- Licence: {lic}",
        ]
        if attr:
            lines.append(f"- Attribution: {attr}")
        if share_alike == "yes":
            lines.append(
                "- **ShareAlike:** material adapted from this dataset must be shared "
                "under the same licence."
            )
        lines.append("")
    return "\n".join(lines)


def load_public_seed(conn: psycopg.Connection, seed: Path = SEED_DIR) -> dict:
    """Load a seed into a freshly migrated database (relationship types come from migrations)."""
    counts = {}
    with conn.transaction(), conn.cursor() as cur:
        for table, _ in TABLES:
            path = seed / f"{table}.csv"
            with path.open(encoding="utf-8") as fh:
                cols = fh.readline().strip()
            with (
                path.open("rb") as fh,
                cur.copy(
                    f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)"
                ) as copy,
            ):
                while chunk := fh.read(1 << 20):
                    copy.write(chunk)
            counts[table] = cur.rowcount
    return counts
