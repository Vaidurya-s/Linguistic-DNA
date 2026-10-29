from pathlib import Path

from app.importers.cldf_wordlist import import_cldf_wordlist
from app.pipeline.validate import run_checks

FIXTURE = Path(__file__).parent / "fixtures" / "lsi_mini"


def test_lsi_import_maps_doculects_and_concepts(db):
    stats = import_cldf_wordlist(db, FIXTURE, "lsi", "fixture")
    assert stats["doculects"] == 9  # 2 + 7 Tier 1 languages; Japanese is not configured
    rows = db.execute(
        """SELECT l.language_id, l.variety_id, l.form, c.label FROM lexeme l
           JOIN lexeme_concept lc ON lc.lexeme_id = l.id JOIN concept c ON c.id = lc.concept_id
           WHERE l.dataset = 'lsi' AND l.language_id = 'tam' ORDER BY c.label, l.form"""
    ).fetchall()
    assert ("tam", "lsi:TAMIL", "eindu", "FIVE") in rows
    assert (
        db.execute("SELECT count(*) FROM relationship WHERE dataset = 'lsi'").fetchone()[0] == 0
    )  # no cognate judgments in LSI: no invented links
    source = db.execute("SELECT reuse_status, dataset_id FROM source WHERE id = 'lsi'").fetchone()
    assert source == ("attribution_required", "lsi")


def test_lsi_rows_pass_public_seed_checks_on_their_own(db):
    import_cldf_wordlist(db, FIXTURE, "lsi", "fixture")
    blocked = db.execute(
        """SELECT count(*) FROM lexeme l JOIN dataset_audit d ON d.id = l.dataset
           WHERE l.dataset = 'lsi' AND d.decision = 'BLOCKED'"""
    ).fetchone()[0]
    assert blocked == 0
    assert run_checks(db)["passed"]
