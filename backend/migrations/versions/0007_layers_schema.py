"""layers schema: derived tables (inferred, candidate, keys, hub, lineage, sound key)

Revision ID: 0007
Revises: 0006

The derived layers live in their own schema and never feed the documented layer. The tables come
from the idempotent files in app/layers/ listed below (the same files `python -m app.cli
init-layers` applies, app.layers.SHIPPED_SQL), so this migration and that command can never
disagree; a SQL file that is not listed creates nothing here. Every statement is
`create ... if not exists`: running it on a database that already has the tables keeps their rows.
The tables are filled by the layer builders, not by this migration.
"""

from pathlib import Path

from alembic import context, op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

LAYERS_DIR = Path(__file__).resolve().parents[2] / "app" / "layers"
# Frozen with this revision: a later layer gets its own migration.
SQL_FILES = ("candidate.sql", "hub.sql", "inferred.sql", "keys.sql", "lineage.sql", "sound_key.sql")


def upgrade() -> None:
    files = [LAYERS_DIR / name for name in SQL_FILES]
    missing = [p.name for p in files if not p.exists()]
    if missing:
        raise RuntimeError(f"layer SQL files not found in {LAYERS_DIR}: {missing}")
    if context.is_offline_mode():  # `alembic upgrade --sql`: write the statements out
        for path in files:
            op.execute(path.read_text(encoding="utf-8"))
        return
    # The raw driver connection, in the migration's own transaction: a file may hold a literal %
    # in a comment, which SQLAlchemy's execute would read as a parameter marker.
    raw = op.get_bind().connection.driver_connection
    for path in files:
        raw.execute(path.read_text(encoding="utf-8"))


def downgrade() -> None:
    # Only the layers schema is dropped; nothing in `public` is touched. The layers hold computed
    # rows only, so they can be rebuilt (see docs/DATA_PIPELINE.md).
    op.execute("DROP SCHEMA IF EXISTS layers CASCADE")
