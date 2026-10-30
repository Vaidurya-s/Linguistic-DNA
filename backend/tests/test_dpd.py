import sqlite3

from app.importers.dpd import compound_parts, import_dpd, sanskrit_equivalent
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id


def test_sanskrit_field_and_compound_parsing():
    assert sanskrit_equivalent("dharma [dhṛ]") == "dharma"
    assert sanskrit_equivalent("akarkaśa (na + karkaśa)") == "akarkaśa"
    assert sanskrit_equivalent("na + (kaścid, kiṃcid)") is None
    assert compound_parts("na + kakkasa") == ["na", "kakkasa"]
    assert compound_parts("√kaṅkh + a") == ["a"]


def test_dpd_words_and_links(db, tmp_path):
    path = tmp_path / "dpd.db"
    src = sqlite3.connect(path)
    src.execute(
        "CREATE TABLE dpd_headwords (id INTEGER, lemma_1 TEXT, meaning_1 TEXT, meaning_2 TEXT,"
        " sanskrit TEXT, derived_from TEXT, compound_construction TEXT)"
    )
    src.executemany(
        "INSERT INTO dpd_headwords VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "dhamma 1.01", "nature", "", "dharma [dhṛ]", "dharati", ""),
            (2, "dhamma 1.02", "quality", "", "dharma [dhṛ]", "dharati", ""),
            (3, "dharati", "holds", "", "dharati [dhṛ]", "", ""),
            (4, "na", "not", "", "na", "", ""),
            (5, "kakkasa", "harsh", "", "karkaśa", "", ""),
            (6, "akakkasa", "", "smooth", "akarkaśa (na + karkaśa)", "kakkasa", "na + kakkasa"),
        ],
    )
    src.commit()
    src.close()
    try:
        stats = import_dpd(db, path, None, "fixture")
        assert stats["pali_lexemes"] == 5  # the two dhamma homonyms are one record
        dhamma = lexeme_id("dpd", "pli:dhamma")
        gloss = db.execute("SELECT gloss FROM lexeme WHERE id = %s", (dhamma,)).fetchone()[0]
        assert gloss == "nature; quality"
        links = set(
            db.execute(
                "SELECT t.form, r.type_id FROM relationship r JOIN lexeme t"
                " ON t.id = r.target_lexeme_id WHERE r.source_lexeme_id = %s",
                (lexeme_id("dpd", "pli:akakkasa"),),
            ).fetchall()
        )
        assert links == {
            ("akarkaśa", "related_form"),
            ("kakkasa", "derived_form"),
            ("kakkasa", "has_component"),
            ("na", "has_component"),
        }
        lang = db.execute(
            "SELECT language_id FROM lexeme WHERE id = %s", (lexeme_id("dpd", "san:dharma"),)
        ).fetchone()
        assert lang == ("san",)
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
