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


def run_fixture_import(url: str, all_languages: bool = False) -> dict:
    with connect(url) as conn:
        load_manifest(conn)
        stats = JambuImporter(
            conn, FIXTURES / "jambu_mini", version="fixture", all_languages=all_languages
        ).run()
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


@pytest.fixture(scope="session")
def client(imported_db):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine

    from app.db.deps import get_conn
    from app.main import app

    engine = create_engine(imported_db)

    def conn_override():
        with engine.begin() as conn:
            yield conn

    app.dependency_overrides[get_conn] = conn_override
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture(scope="session")
def lsi_imported(imported_db: str) -> str:
    """The CC-BY LSI fixture, which also covers the Tier 1 languages."""
    from app.importers.cldf_wordlist import import_cldf_wordlist

    with connect(imported_db) as conn:
        import_cldf_wordlist(conn, FIXTURES / "lsi_mini", "lsi", "fixture")
    return imported_db
