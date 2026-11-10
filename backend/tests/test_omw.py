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


def test_markup_entities_and_placeholders_are_cleaned(db, tmp_path):
    d = tmp_path / "glottolog"
    d.mkdir()
    (d / "languages.csv").write_text(
        "ID,Name,Level,ISO639P3code,Language_ID\nstan1293,English,language,eng,\n",
        encoding="utf-8",
    )
    (d / "values.csv").write_text("ID,Language_ID,Parameter_ID,Value\n", encoding="utf-8")
    xml = tmp_path / "en.xml"
    xml.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><LexicalResource>'
        '<Lexicon id="omw-en" label="Fixture" language="en" license="x" version="1">'
        '<LexicalEntry id="e1"><Lemma writtenForm="S&amp;amp;P500" partOfSpeech="n"/>'
        '<Sense id="s1" synset="ss1"/></LexicalEntry>'
        '<LexicalEntry id="e2"><Lemma writtenForm="c&amp;amp;#339;lacanthe" partOfSpeech="n"/>'
        "</LexicalEntry>"
        '<LexicalEntry id="e3"><Lemma writtenForm="&amp;lt;big&amp;gt;" partOfSpeech="n"/>'
        "</LexicalEntry>"
        '<LexicalEntry id="e4"><Lemma writtenForm="bad�form" partOfSpeech="n"/>'
        "</LexicalEntry>"
        '<LexicalEntry id="e5"><Lemma writtenForm="-" partOfSpeech="n"/>'
        '<Sense id="s5" synset="ss1"/></LexicalEntry>'
        '<Synset id="ss1" ili="i1" partOfSpeech="n"><Definition>a &lt;b&gt;bold&lt;/b&gt; '
        "def</Definition></Synset></Lexicon></LexicalResource>",
        encoding="utf-8",
    )
    glottolog = Glottolog(d)
    try:
        import_glottolog_languages(db, glottolog)
        stats = import_omw(db, [xml], glottolog, {"en": "eng"}, "fixture")
        assert stats["skipped_placeholder_form"] == 2 and stats["lexemes"] == 3
        forms = {
            r[0]: r[1]
            for r in db.execute("SELECT source_record_id, form FROM lexeme WHERE dataset = 'omw'")
        }
        assert forms["e1"] == "S&P500"
        assert forms["e2"] == "cœlacanthe"
        assert "e3" not in forms  # a lone <big> tag is markup, nothing is left of the form
        assert "�" not in forms["e4"]
        assert "e5" not in forms
        assert db.execute("SELECT definition FROM concept WHERE id = 'ili:i1'").fetchone()[0] == (
            "a bold def"
        )
    finally:
        db.rollback()
