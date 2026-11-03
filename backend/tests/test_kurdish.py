"""Kurdish lexicon importer on small Ontolex-Lemon Turtle files in the two layouts used."""

from app.importers.kurdish import gloss_of, import_kurdish, parse_ttl
from app.importers.manifest import load_manifest
from app.pipeline.validate import run_checks

SORANI = """@prefix : <https://example.org/> .

:ckb_1_entry a lexicog:Entry ;
\trdfs:member :ckb_1_comp .

:lex_ckb_1 a ontolex:LexicalEntry, ontolex:Word ;
  ontolex:canonicalForm :form_ckb_1 ;
  rdfs:label "edeb"@ckb-latn .

:form_ckb_1 a ontolex:Form ;
  dct:language <http://www.lexvo.org/page/iso639-3/ckb> ;
  ontolex:writtenRep "edeb"@ckb-latn ;
  lexinfo:partOfSpeech lexinfo:noun ;
  ontolex:sense :ckb_9_sense .

:en_5 a ontolex:LexicalEntry ;
  dct:language <http://id.loc.gov/vocabulary/iso639-2/en> ;
  rdfs:label "literature, culture"@en ;
  ontolex:sense :en_5_sense .

:trans_ckb_9_sense a vartrans:Translation ;
  vartrans:source :ckb_9_sense ;
  vartrans:target :en_5_sense .

:lex_ckb_2 a ontolex:LexicalEntry, ontolex:Word ;
  rdfs:label "bê"@ckb-latn .
"""
SOUTHERN = """@prefix : <https://example.org/> .

:lex_sdh_7 a ontolex:LexicalEntry, ontolex:Word ;
  rdfs:label "ئا"@sdh-arab , "a"@sdh-latn;
  ontolex:sense :sdh_7_sense_1 .

:ku_3 a ontolex:LexicalEntry ;
  rdfs:label "ئەرێ"@ku-arab ;
  ontolex:sense :ku_3_sense .

:trans_sdh_7_sense_1_sense a vartrans:Translation ;
  vartrans:source :sdh_7_sense_1_sense ;
  vartrans:target :ku_3_sense .

:fa_4 a ontolex:LexicalEntry ;
  rdfs:label "بلی"@fa ;
  ontolex:sense :fa_4_sense .

:trans_sdh_7_sense_1_sense a vartrans:Translation ;
  vartrans:source :sdh_7_sense_1_sense ;
  vartrans:target :fa_4_sense .
"""


def test_parse_both_layouts(tmp_path):
    (tmp_path / "Sorani.ttl").write_text(SORANI, encoding="utf-8")
    (tmp_path / "Southern_Kurdish.ttl").write_text(SOUTHERN, encoding="utf-8")
    sorani = {e["id"]: e for e in parse_ttl(tmp_path / "Sorani.ttl", "ckb")}
    assert sorani["ckb_1"]["pos"] == "noun"
    assert gloss_of(sorani["ckb_1"]["glosses"]) == "literature, culture"
    assert sorani["ckb_2"]["glosses"] == []  # a headword without a translation is still a word
    south = parse_ttl(tmp_path / "Southern_Kurdish.ttl", "sdh")[0]
    assert {t for t, _ in south["labels"]} == {"ئا", "a"}
    assert gloss_of(south["glosses"]) == "ku: ئەرێ; fa: بلی"  # no English: tagged translations


def test_import(db, tmp_path):
    (tmp_path / "Sorani.ttl").write_text(SORANI, encoding="utf-8")
    (tmp_path / "Southern_Kurdish.ttl").write_text(SOUTHERN, encoding="utf-8")
    try:
        load_manifest(db)
        for iso, gid, name in (
            ("ckb", "gl-cent1972", "Central Kurdish"),
            ("sdh", "gl-sout2640", "Southern Kurdish"),
        ):
            db.execute(
                "INSERT INTO language (id, name, iso_code, role, is_proto, is_enabled,"
                " metadata_json) VALUES (%s, %s, %s, 'other', false, true, '{}')"
                " ON CONFLICT (id) DO NOTHING",
                (gid, name, iso),
            )
        stats = import_kurdish(db, tmp_path, "fixture")
        assert stats["lexemes"] == 3
        rows = dict(
            db.execute(
                "SELECT l.form, l.language_id || '|' || coalesce(l.gloss, '') || '|'"
                " || array_to_string(l.tags, ',') FROM lexeme l"
                " WHERE l.dataset = 'kurdish-lexicography'"
            ).fetchall()
        )
        assert rows["edeb"] == "gl-cent1972|literature, culture|dialect:Sorani,pos:noun"
        assert rows["ئا"].startswith("gl-sout2640|ku: ئەرێ; fa: بلی|") and "latin:a" in rows["ئا"]
        assert db.execute(
            "SELECT count(*) FROM relationship WHERE dataset = 'kurdish-lexicography'"
        ).fetchone() == (0,)
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
