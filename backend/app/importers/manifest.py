"""Load data/manifests/source_manifest.csv into the ``source`` table."""

from pathlib import Path

import psycopg

from app.config import REPO_ROOT
from app.importers.audit import load_audit
from app.importers.common import read_csv
from app.models.enums import ReuseStatus

MANIFEST = REPO_ROOT / "data" / "manifests" / "source_manifest.csv"
COLUMNS = (
    "source_id",
    "title",
    "author_or_editor",
    "url",
    "version",
    "access_date",
    "licence_name",
    "licence_url",
    "attribution_text",
    "redistribution_allowed",
    "commercial_use_allowed",
    "derivatives_allowed",
    "share_alike_required",
    "permission_status",
    "notes",
    "dataset_id",
)


def load_manifest(conn: psycopg.Connection, path: Path = MANIFEST) -> int:
    """Load the dataset audit, then the per-source manifest that points into it."""
    load_audit(conn)
    ensure_languages(conn)
    n = 0
    with conn.cursor() as cur:
        for row in read_csv(path, COLUMNS):
            status = ReuseStatus(row["permission_status"])  # rejects unknown values
            cur.execute(
                """
                INSERT INTO source (id, title, author_or_editor, url, version_or_release,
                    licence_name, licence_url, reuse_status, attribution_text, notes, dataset_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title,
                    author_or_editor = EXCLUDED.author_or_editor, url = EXCLUDED.url,
                    version_or_release = EXCLUDED.version_or_release,
                    licence_name = EXCLUDED.licence_name, licence_url = EXCLUDED.licence_url,
                    reuse_status = EXCLUDED.reuse_status,
                    attribution_text = EXCLUDED.attribution_text, notes = EXCLUDED.notes,
                    dataset_id = EXCLUDED.dataset_id
                """,
                (
                    row["source_id"],
                    row["title"],
                    row["author_or_editor"] or None,
                    row["url"] or None,
                    row["version"] or None,
                    row["licence_name"] or None,
                    row["licence_url"] or None,
                    status.value,
                    row["attribution_text"] or None,
                    row["notes"] or None,
                    row["dataset_id"] or None,
                ),
            )
            n += 1
    return n


ORPHAN_SQL = """
DELETE FROM source s
WHERE (s.dataset_id IS NULL OR s.id LIKE 'jambu-ref:%%')
  AND NOT EXISTS (SELECT 1 FROM lexeme WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM relationship WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM evidence WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM concept WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM lexeme_concept WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM variety WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM language_script WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM language_family WHERE source_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM source c WHERE c.parent_source_id = s.id)
"""


def prune_orphan_sources(conn: psycopg.Connection) -> int:
    """Drop auto-created or unlinked sources that no row references any more."""
    with conn.cursor() as cur:
        cur.execute(ORPHAN_SQL)
        return cur.rowcount


def ensure_languages(conn: psycopg.Connection) -> int:
    """Register the configured target languages so any importer can run first."""
    from app.importers.jambu import load_language_config  # local import: avoids a cycle

    with conn.cursor() as cur:
        langs = load_language_config().values()
        for t in langs:
            cur.execute(
                "INSERT INTO language (id, name, glottocode, role, is_proto, is_enabled,"
                " metadata_json) VALUES (%s, %s, %s, %s, false, true, %s)"
                " ON CONFLICT (id) DO UPDATE SET is_enabled = true,"
                " metadata_json = language.metadata_json || EXCLUDED.metadata_json",
                (
                    t.id,
                    t.name,
                    t.glottocode or None,
                    t.role,
                    psycopg.types.json.Jsonb({"group": t.group}),
                ),
            )
            cur.execute(
                "INSERT INTO language_script (language_id, script_id, is_primary)"
                " VALUES (%s, %s, true) ON CONFLICT DO NOTHING",
                (t.id, t.primary_script),
            )
        return len(langs)
