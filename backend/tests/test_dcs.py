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


def test_markup_control_characters_and_placeholders_are_cleaned(db, tmp_path):
    f = tmp_path / "dictionary.csv"
    f.write_text(
        "id\tword\tgrammar\tpreverbs\tmeanings\n"
        "1\tak\x07āra\tm\t\tH<sub>2</sub>O; [[name of a prince]]\n"
        "2\tdharma\tm\t\t?\n"
        "3\tkarman\tn\t\t???\n"
        "4\t-\tn\t\tnothing\n"
        "5\t?\tn\t\tnothing\n"
        "6\tbala\tn\t\t&amp;lt;i&amp;gt;strength&amp;lt;/i&amp;gt;\n",
        encoding="utf-8",
    )
    try:
        stats = import_dcs(db, f, "fixture")
        assert stats["lexemes"] == 4 and stats["skipped_placeholder_form"] == 2
        rows = {
            r[0]: r[1:]
            for r in db.execute(
                "SELECT source_record_id, form, gloss, transliteration FROM lexeme"
                " WHERE dataset = 'dcs'"
            )
        }
        assert rows["1"] == ("akāra", "H2O; name of a prince", "akāra")
        assert rows["2"][1] is None and rows["3"][1] is None
        assert rows["6"][1] == "strength"
        assert "4" not in rows and "5" not in rows
        assert (
            db.execute(
                "SELECT count(*) FROM lexeme WHERE id = %s", (lexeme_id("dcs", "1"),)
            ).fetchone()[0]
            == 1
        )
    finally:
        db.rollback()
