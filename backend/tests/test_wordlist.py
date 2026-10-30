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


def test_cognate_sets_link_forms_across_languages(db):
    cognate = Path(__file__).parent / "fixtures" / "cognate_mini"
    try:
        configured_only = import_cldf_wordlist(db, cognate, "lsi", "fixture")
        assert configured_only["lexemes"] == 2 and configured_only["cognate_relationships"] == 1
        full = import_cldf_wordlist(db, cognate, "lsi", "fixture", all_languages=True)
        assert full["lexemes"] == 3 and full["cognate_relationships"] == 3
        english = db.execute(
            "SELECT g.id, g.is_enabled FROM lexeme l JOIN language g ON g.id = l.language_id"
            " WHERE l.form = 'tooth' AND l.dataset = 'lsi'"
        ).fetchone()
        assert english == ("gl-stan1293", False)
        cite = db.execute(
            "SELECT r.direction::text, e.citation FROM relationship r JOIN evidence e"
            " ON e.relationship_id = r.id WHERE r.dataset = 'lsi' LIMIT 1"
        ).fetchone()
        assert cite == ("undirected", "lsi, cognate set tooth-1")
    finally:
        db.rollback()


def test_spellings_from_each_cldf_layout():
    from app.importers.cldf_wordlist import spellings

    # NorthEuraLex: Value is the native spelling, Form is IPA
    assert spellings({"Value": "आँख", "Form": "ãːkʰ"}, None) == ("आँख", "आँख", "ãːkʰ")
    # IE-CoR: romanised Form with native_script and phon_form columns
    row = {"Value": "chāi", "Form": "chāi", "native_script": "ছাই", "phon_form": "tʃʰai"}
    assert spellings(row, None) == ("chāi", "ছাই", "tʃʰai")
    # LSI: romanised only; ASJP: a phonetic code kept as the form
    assert spellings({"Value": "pani", "Form": "pani"}, None) == ("pani", None, None)
    assert spellings({"Value": "pani", "Form": "p a n i"}, "ASJPcode") == ("pani", None, None)
