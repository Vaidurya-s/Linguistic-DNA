"""Sindhi Open Lexicon importer on a small CSV in the dataset's layout."""

from app.importers.manifest import load_manifest
from app.importers.sindhi import headwords, import_sindhi, read_rows
from app.pipeline.validate import run_checks

COLS = (
    "﻿lexical_id,entry_id,word,word_with_airab_or_variant,part_of_speech,domain,"
    "definition,language_direction,source_dictionary,normalized_word,normalized_definition,"
    "extra,publisher,publisher_url,prepared_by\n"
)
J = "جامع سنڌي لغات"
D = "Devanagari/Sindhi → English"
ROWS = (
    COLS
    + f"slx_1,1,پاڻي,پاڻِي:,masculine noun,,ذ. ماءُ,sindhi,{J},,,,,,\n"
    + f"slx_2,2,پاڻي,,adjective,,صفت. هڪڙو,sindhi,{J},,,,,,\n"
    + f"slx_3,3,پاڻي,,,,Water,sindhi,{D},,,,,,\n"
    + f"slx_4,4,گهر,,,,گهر جي معنيٰ,sindhi,{J},,,,,,\n"
    + "slx_5,5,Water,,,,پاڻي,english,English → Sindhi,,,,,,\n"
    + "slx_6,6,ماء,,,,mother,hindi,Hindi → Sindhi,,,,,,\n"
    + "slx_7,7,آبدار,,,,Brilliant; of a good water,sindhi-english,Mewaram لغت,,,,,,\n"
)


def test_only_sindhi_headwords_one_word_each(tmp_path):
    f = tmp_path / "lex.csv"
    f.write_text(ROWS, encoding="utf-8")
    words = {h.form: h for h in headwords(read_rows(f), "gl-sind1272")}
    assert set(words) == {
        "پاڻي",
        "گهر",
        "آبدار",
    }  # English and Hindi headwords are not Sindhi words
    water = words["پاڻي"]
    assert water.gloss == "Water" and water.native_form == "پاڻِي"  # the English definition wins
    assert "pos:masculine noun" in water.tags and "pos:adjective" in water.tags
    assert f"source:{J}" in water.tags and f"source:{D}" in water.tags
    assert "gloss:sd" in words["گهر"].tags  # only a Sindhi definition exists
    assert words["آبدار"].gloss == "Brilliant; of a good water"  # Mewaram: Sindhi-English
    assert "SindhiLanguage.org" in water.citation


def test_import(db, tmp_path):
    f = tmp_path / "lex.csv"
    f.write_text(ROWS, encoding="utf-8")
    try:
        load_manifest(db)
        db.execute(
            "INSERT INTO language (id, name, iso_code, role, is_proto, is_enabled, metadata_json)"
            " VALUES ('gl-sind1272', 'Sindhi', 'snd', 'other', false, true, '{}')"
            " ON CONFLICT (id) DO NOTHING"
        )
        stats = import_sindhi(db, f, "fixture")
        assert stats["lexemes"] == 3
        assert db.execute(
            "SELECT count(*) FROM lexeme WHERE dataset = 'sindhi-lexicon'"
            " AND language_id = 'gl-sind1272'"
        ).fetchone() == (3,)
        assert db.execute(
            "SELECT count(*) FROM relationship WHERE dataset = 'sindhi-lexicon'"
        ).fetchone() == (0,)
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
