"""Load data/manifests/dataset_audit.csv, the authority on what may be published."""

from pathlib import Path

import psycopg

from app.config import REPO_ROOT
from app.importers.common import read_csv
from app.models.enums import AuditDecision

AUDIT = REPO_ROOT / "data" / "manifests" / "dataset_audit.csv"
COLUMNS = (
    "dataset_id",
    "name",
    "component",
    "version",
    "licence_name",
    "licence_url",
    "attribution_text",
    "share_alike",
    "decision",
    "decision_reason",
)


def load_audit(conn: psycopg.Connection, path: Path = AUDIT) -> int:
    n = 0
    with conn.cursor() as cur:
        for row in read_csv(path, COLUMNS):
            decision = AuditDecision(row["decision"])  # rejects unknown decisions
            cur.execute(
                """
                INSERT INTO dataset_audit (id, name, component, version, licence_name,
                    licence_url, attribution_text, share_alike, decision, decision_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name,
                    component = EXCLUDED.component, version = EXCLUDED.version,
                    licence_name = EXCLUDED.licence_name, licence_url = EXCLUDED.licence_url,
                    attribution_text = EXCLUDED.attribution_text,
                    share_alike = EXCLUDED.share_alike, decision = EXCLUDED.decision,
                    decision_reason = EXCLUDED.decision_reason
                """,
                (
                    row["dataset_id"],
                    row["name"],
                    row["component"] or None,
                    row["version"] or None,
                    row["licence_name"] or None,
                    row["licence_url"] or None,
                    row["attribution_text"] or None,
                    row["share_alike"] or None,
                    decision.value,
                    row["decision_reason"] or None,
                ),
            )
            n += 1
    return n
