from pathlib import Path

from app.importers.cdsl import import_cdsl_mw, slp1_to_iast
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id

FIXTURE = Path(__file__).parent / "fixtures" / "cdsl_mini" / "mw.txt"


def test_slp1_to_iast():
    assert slp1_to_iast("kfzRa") == "kṛṣṇa"
    assert slp1_to_iast("aMSa/") == "aṃśa"


def test_monier_williams_headwords_glosses_and_compounds(db):
    try:
        stats = import_cdsl_mw(db, FIXTURE, "fixture")
        assert stats["headwords"] == 3 and stats["relationships"] == 2
        row = db.execute(
            "SELECT form, gloss, form_kind::text, source_citation FROM lexeme WHERE id = %s",
            (lexeme_id("cdsl-mw", "kAra"),),
        ).fetchone()
        assert row == (
            "kāra",
            "m. making, doing; an act",
            "word",
            "Monier-Williams 1899, p. 2, col. 3",
        )
        parts = {
            r[0]
            for r in db.execute(
                "SELECT t.form FROM relationship r JOIN lexeme t ON t.id = r.target_lexeme_id"
                " WHERE r.source_lexeme_id = %s AND r.type_id = 'has_component'",
                (lexeme_id("cdsl-mw", "akAra"),),
            )
        }
        assert parts == {"a", "kāra"}
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
