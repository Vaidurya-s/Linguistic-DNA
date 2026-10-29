import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.importers.common import connect
from app.importers.glottolog import import_glottolog
from app.importers.jambu import JambuImporter
from app.importers.manifest import load_manifest

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/lsg_test"
)


@pytest.fixture(scope="session")
def migrated_db() -> str:
    with connect(TEST_DB) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB)
    command.upgrade(cfg, "head")
    return TEST_DB


def run_fixture_import(url: str) -> dict:
    with connect(url) as conn:
        load_manifest(conn)
        stats = JambuImporter(conn, FIXTURES / "jambu_mini", version="fixture").run()
        import_glottolog(conn, FIXTURES / "glottolog_mini")
    return stats


@pytest.fixture(scope="session")
def imported_db(migrated_db: str) -> str:
    run_fixture_import(migrated_db)
    return migrated_db


@pytest.fixture
def db(imported_db: str):
    with connect(imported_db) as conn:
        yield conn
