"""Load data/manifests/source_manifest.csv into the ``source`` table."""

from pathlib import Path

import psycopg

from app.config import REPO_ROOT
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
)


def load_manifest(conn: psycopg.Connection, path: Path = MANIFEST) -> int:
    n = 0
    with conn.cursor() as cur:
        for row in read_csv(path, COLUMNS):
            status = ReuseStatus(row["permission_status"])  # rejects unknown values
            cur.execute(
                """
                INSERT INTO source (id, title, author_or_editor, url, version_or_release,
                    licence_name, licence_url, reuse_status, attribution_text, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title,
                    author_or_editor = EXCLUDED.author_or_editor, url = EXCLUDED.url,
                    version_or_release = EXCLUDED.version_or_release,
                    licence_name = EXCLUDED.licence_name, licence_url = EXCLUDED.licence_url,
                    reuse_status = EXCLUDED.reuse_status,
                    attribution_text = EXCLUDED.attribution_text, notes = EXCLUDED.notes
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
                ),
            )
            n += 1
    return n
