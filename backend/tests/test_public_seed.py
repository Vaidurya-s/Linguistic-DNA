import csv
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.importers.cldf_wordlist import import_cldf_wordlist
from app.importers.common import connect
from app.pipeline.public_seed import build_public_seed, load_public_seed
from app.pipeline.validate import run_checks
from tests.conftest import BACKEND, TEST_DB

LSI = Path(__file__).parent / "fixtures" / "lsi_mini"


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_seed_contains_only_approved_datasets_and_reloads_cleanly(db, tmp_path):
    import_cldf_wordlist(db, LSI, "lsi", "fixture")  # approved, alongside blocked Jambu rows
    db.commit()
    manifest = build_public_seed(db, tmp_path)

    lexemes = rows(tmp_path / "lexeme.csv")
    assert lexemes and {r["dataset"] for r in lexemes} == {"lsi"}
    assert not any(
        r["dataset_id"] in ("jambu", "cdial", "dedr") for r in rows(tmp_path / "source.csv")
    )
    attribution = (tmp_path / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert "Linguistic Survey of India" in attribution and "Jambu" not in attribution
    assert set(manifest["sha256"]) >= {"lexeme.csv", "relationship.csv", "evidence.csv"}

    seed_db = TEST_DB.rsplit("/", 1)[0] + "/lsg_seed_test"
    with connect(TEST_DB) as admin:
        admin.autocommit = True
        admin.execute("DROP DATABASE IF EXISTS lsg_seed_test")
        admin.execute("CREATE DATABASE lsg_seed_test")
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", seed_db)
    command.upgrade(cfg, "head")
    with connect(seed_db) as fresh:
        counts = load_public_seed(fresh, tmp_path)
        assert counts["lexeme"] == len(lexemes)
        result = run_checks(fresh, public_seed=True)
        assert result["passed"], [c for c in result["checks"] if not c["passed"]]
