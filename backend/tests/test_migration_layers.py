"""The layers schema comes from the migration; init-layers stays a harmless re-run.

Only the layers that ship are created: a SQL file next to them that is not listed in
`app.layers.SHIPPED_SQL` (for example the file of an experiment) creates no table."""

import importlib.util
import re
from pathlib import Path

from app.cli import init_layers
from app.importers.common import connect
from app.layers import SHIPPED_SQL

LAYERS = Path(__file__).resolve().parents[1] / "app" / "layers"
MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0007_layers_schema.py"
)
CREATES = r"create table if not exists (layers\.\w+)"


def declared_tables(names=SHIPPED_SQL) -> set[str]:
    found = set()
    for name in names:
        found |= set(re.findall(CREATES, (LAYERS / name).read_text()))
    return found


def migration_module():
    spec = importlib.util.spec_from_file_location("migration_0007", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_and_init_layers_use_the_same_shipped_files():
    assert tuple(migration_module().SQL_FILES) == tuple(sorted(SHIPPED_SQL))
    assert all((LAYERS / name).exists() for name in SHIPPED_SQL)


def test_shipped_tables_are_exactly_the_documented_layer_tables():
    # inferred, candidate (pairs, calibration, gloss tokens), word keys, sound key, hub, lineage
    assert declared_tables() == {
        "layers.inferred_pair",
        "layers.candidate_pair",
        "layers.candidate_calibration",
        "layers.gloss_token",
        "layers.word_key",
        "layers.word_key_build",
        "layers.sound_key",
        "layers.sound_key_build",
        "layers.cognate_component",
        "layers.edge_hub_flag",
        "layers.cognate_component_build",
        "layers.source_lineage",
    }
    # a SQL file that is not shipped adds nothing to that set
    others = {p.name for p in LAYERS.glob("*.sql")} - set(SHIPPED_SQL)
    assert not declared_tables(others) & declared_tables()


def test_migration_creates_every_shipped_layer_table(migrated_db):
    with connect(migrated_db) as conn:
        have = {
            f"{s}.{t}"
            for s, t in conn.execute(
                "select table_schema, table_name from information_schema.tables"
                " where table_schema = 'layers'"
            )
        }
        assert declared_tables() <= have
        version = conn.execute("select version_num from alembic_version").fetchone()[0]
        assert version >= "0007"


def test_init_layers_after_the_migration_changes_nothing(migrated_db):
    with connect(migrated_db) as conn:
        before = conn.execute("select count(*) from pg_indexes where schemaname = 'layers'")
        n = before.fetchone()[0]
        assert init_layers(conn)["applied"] == list(SHIPPED_SQL)
        after = conn.execute("select count(*) from pg_indexes where schemaname = 'layers'")
        assert after.fetchone()[0] == n
