from pathlib import Path

from app.importers.cdsl import clean_body, import_cdsl_mw, pointer_target, slp1_to_iast
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id

FIXTURE = Path(__file__).parent / "fixtures" / "cdsl_mini" / "mw.txt"


def test_slp1_to_iast():
    assert slp1_to_iast("kfzRa") == "kṛṣṇa"
    assert slp1_to_iast("aMSa/") == "aṃśa"


def test_clean_body_drops_leftover_markup():
    assert clean_body("<s>kAra</s> ¦ a {{unknown=1}} thing [[x|link]] &amp; more") == (
        "a thing link & more"
    )
    assert "{{" not in clean_body("{{Lbody=12}}")


def test_pointer_target_only_for_a_whole_pointer_body():
    assert pointer_target("{{Lbody=123}}") == "123"
    assert pointer_target(" {{Lbody=7}} ") == "7"
    assert pointer_target("see {{Lbody=7}}") is None


def test_lbody_pointer_takes_the_referenced_gloss(db):
    try:
        import_cdsl_mw(db, FIXTURE, "fixture")
        gloss = {
            k: db.execute(
                "SELECT gloss FROM lexeme WHERE id = %s", (lexeme_id("cdsl-mw", k),)
            ).fetchone()[0]
            for k in ("kArya", "kArin")
        }
        assert gloss["kArya"] == "m. making, doing"  # the body of L3
        assert gloss["kArin"] is None  # unknown target: empty, never the literal pointer
        leaked = db.execute("SELECT count(*) FROM lexeme WHERE gloss LIKE '%%Lbody%%'").fetchone()
        assert leaked[0] == 0
    finally:
        db.rollback()


def test_monier_williams_headwords_glosses_and_compounds(db):
    try:
        stats = import_cdsl_mw(db, FIXTURE, "fixture")
        assert stats["headwords"] == 5 and stats["relationships"] == 2
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
