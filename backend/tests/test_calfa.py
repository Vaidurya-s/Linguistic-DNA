"""Calfa Armenian importer on small definition files in the repository's layout."""

from app.importers.calfa import clean_title, import_calfa, read_headwords
from app.importers.manifest import load_manifest
from app.pipeline.validate import run_checks

HEADER = "Title\tComplement\tPOS_1\tDefinition_1\tPOS_2\tDefinition_2\n"
COMMON = (
    HEADER
    + "<letter>Ա</letter> (aïp)\tայբի\ts.\tthe first letter\t\t\n"
    + "Աբաս\tու\ts.\tfather; abbot\t\t\n"
    + "Աբաս\t\ts.\tabbot (second sense)\t\t\n"
    + "\t\ts.\tno title\t\t\n"
    + '*աբեղուկ\t\ts.\tlark; cf. <a href="./?s=Աբեղ">Աբեղ առնել</a> &amp; a < b.\t\t\n'
)
PROPER = HEADER + "Արայ\tյիւ\tnp.\tAra.\t\t\n"


def test_clean_title_removes_markup_and_romanisation():
    assert clean_title("<letter>Ա</letter> (aïp)") == "Ա"
    assert clean_title("Աբաս") == "Աբաս"


def test_headwords_lowercase_numbering_and_proper_nouns(tmp_path):
    (tmp_path / "c.tsv").write_text(COMMON, encoding="utf-8")
    (tmp_path / "p.tsv").write_text(PROPER, encoding="utf-8")
    common = read_headwords(tmp_path / "c.tsv", False, "x")
    assert [(h.record_id, h.form) for h in common] == [
        ("c:ա", "ա"),
        ("c:աբաս", "աբաս"),
        ("c:աբաս#2", "աբաս"),  # a homograph is a separate entry
        ("c:*աբեղուկ", "*աբեղուկ"),
    ]
    assert common[1].gloss == "father; abbot" and common[1].tags == ["pos:s."]
    proper = read_headwords(tmp_path / "p.tsv", True, "x")
    assert [h.form for h in proper] == ["Արայ"]  # a proper noun keeps its capital


def test_import(db, tmp_path):
    (tmp_path / "definitions").mkdir()
    (tmp_path / "definitions_proper").mkdir()
    (tmp_path / "definitions" / "en-definitions01.tsv").write_text(COMMON, encoding="utf-8")
    (tmp_path / "definitions_proper" / "en-definitions01.tsv").write_text(PROPER, encoding="utf-8")
    try:
        load_manifest(db)
        db.execute(
            "INSERT INTO language (id, name, iso_code, role, is_proto, is_enabled, metadata_json)"
            " VALUES ('gl-clas1249', 'Classical-Middle Armenian', 'xcl', 'other', false, true,"
            " '{}') ON CONFLICT (id) DO NOTHING"
        )
        stats = import_calfa(db, tmp_path, "fixture")
        assert stats["lexemes"] == 5
        # a starred headword is a hypothetical form; markup is removed from glosses, not "< b"
        assert db.execute(
            "SELECT reconstruction_status::text, gloss FROM lexeme"
            " WHERE dataset = 'calfa-armenian' AND form = '*աբեղուկ'"
        ).fetchone() == ("reconstructed", "lark; cf. Աբեղ առնել & a < b.")
        row = db.execute(
            "SELECT language_id, gloss, source_id FROM lexeme WHERE dataset = 'calfa-armenian'"
            " AND form = 'աբաս' ORDER BY source_record_id LIMIT 1"
        ).fetchone()
        assert row == ("gl-clas1249", "father; abbot", "calfa-armenian")
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
