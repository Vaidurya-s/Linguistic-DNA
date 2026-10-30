from pathlib import Path

from app.importers.omw import import_omw
from app.pipeline.languages import Glottolog, import_glottolog_languages

FIXTURE = Path(__file__).parent / "fixtures" / "omw_mini"


def test_wordnets_meet_through_shared_concepts(db, tmp_path):
    d = tmp_path / "glottolog"
    d.mkdir()
    (d / "languages.csv").write_text(
        "ID,Name,Level,ISO639P3code,Language_ID\n"
        "stan1293,English,language,eng,\nfinn1318,Finnish,language,fin,\n",
        encoding="utf-8",
    )
    (d / "values.csv").write_text("ID,Language_ID,Parameter_ID,Value\n", encoding="utf-8")
    glottolog = Glottolog(d)
    try:
        import_glottolog_languages(db, glottolog)
        stats = import_omw(
            db, sorted(FIXTURE.glob("*.xml")), glottolog, {"en": "eng", "fi": "fin"}, "fixture"
        )
        assert stats["lexicons"] == 2 and stats["lexemes"] == 4 and stats["concepts"] == 2
        # Finnish "vesi" shares the English concept "water" and is glossed by it
        row = db.execute(
            "SELECT l.language_id, l.gloss, c.label, c.definition, l.source_id"
            " FROM lexeme l JOIN lexeme_concept lc ON lc.lexeme_id = l.id"
            " JOIN concept c ON c.id = lc.concept_id WHERE l.form = 'vesi'"
        ).fetchone()
        assert row[:3] == ("gl-finn1318", "water", "water")
        assert row[3].startswith("binary compound") and row[4] == "omw-omw-fi"
        same = db.execute(
            "SELECT count(DISTINCT l.language_id) FROM lexeme_concept lc"
            " JOIN lexeme l ON l.id = lc.lexeme_id WHERE lc.concept_id = 'ili:i97225'"
        ).fetchone()[0]
        assert same == 2
    finally:
        db.rollback()
