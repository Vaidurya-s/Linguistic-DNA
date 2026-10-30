from pathlib import Path

from app.importers.dcs import import_dcs
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id

FIXTURE = Path(__file__).parent / "fixtures" / "dcs_mini" / "dictionary.csv"


def test_dcs_lemmas_become_cited_sanskrit_lexemes(db):
    try:
        stats = import_dcs(db, FIXTURE, "fixture")
        assert stats["lexemes"] == 2 and stats["skipped_empty"] == 1
        row = db.execute(
            "SELECT language_id, form, gloss, tags, source_citation FROM lexeme WHERE id = %s",
            (lexeme_id("dcs", "1"),),
        ).fetchone()
        assert row == ("san", "akāra", "the letter or sound a", ["pos:m"], "DCS lexicon 1")
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
