"""MonWN importer on a synthetic TSV in the Open Multilingual Wordnet's tab format."""

from pathlib import Path

from app.importers.manifest import load_manifest
from app.importers.monwn import ili_by_offset, import_monwn, read_lemmas
from app.pipeline.validate import run_checks

OMW_EN = Path(__file__).parent / "fixtures" / "omw_mini" / "en.xml"
TSV = (
    "# Mongolian Wordnet (MonWN)\tmon\thttps://github.com/num-milab/monwn\tCC BY 4.0\n"
    "02084071-n\tmon:lemma\tнохой\n"
    "02084071-n\tmon:def 0\ta domesticated mammal\n"
    "02084071-n\tmon:lemma\tгэрийн нохой\n"
    "14845743-n\tmon:lemma\tус\n"
    "99999999-n\tmon:lemma\tсанамсаргүй\n"  # a synset the English wordnet does not have
    "14845743-n\tmon:lemma\tнохой\n"  # the same word in a second synset: one word, two meanings
)


def test_reads_lemmas_and_maps_offsets_to_concepts(tmp_path):
    tsv = tmp_path / "wn-data-mon.tsv"
    tsv.write_text(TSV, encoding="utf-8")
    assert [w for _, w in read_lemmas(tsv)] == [
        "нохой",
        "гэрийн нохой",
        "ус",
        "санамсаргүй",
        "нохой",
    ]
    assert ili_by_offset(OMW_EN) == {"02084071-n": "i46360", "14845743-n": "i97225"}


def test_import(db, tmp_path):
    tsv = tmp_path / "wn-data-mon.tsv"
    tsv.write_text(TSV, encoding="utf-8")
    try:
        load_manifest(db)
        db.execute(
            "INSERT INTO language (id, name, iso_code, glottocode, role, is_proto, is_enabled,"
            " metadata_json) VALUES ('gl-halh1238', 'Halh Mongolian', 'khk', 'halh1238',"
            " 'other', false, true, '{}')"
            " ON CONFLICT (id) DO NOTHING"
        )
        stats = import_monwn(db, tsv, OMW_EN, "fixture")
        assert stats["lexemes"] == 4 and stats["unmapped_synsets"] == 1
        # "нохой" is one word with two concepts; all words cite MonWN and are Halh Mongolian
        links = db.execute(
            "SELECT l.language_id, l.source_id, lc.concept_id FROM lexeme l"
            " JOIN lexeme_concept lc ON lc.lexeme_id = l.id WHERE l.form = 'нохой'"
            " ORDER BY lc.concept_id"
        ).fetchall()
        assert links == [
            ("gl-halh1238", "monwn", "ili:i46360"),
            ("gl-halh1238", "monwn", "ili:i97225"),
        ]
        # no word-to-word relationships are invented
        assert db.execute(
            "SELECT count(*) FROM relationship WHERE dataset = 'monwn'"
        ).fetchone() == (0,)
        assert run_checks(db)["passed"]
        # a second import replaces the first
        again = import_monwn(db, tsv, OMW_EN, "fixture")
        assert again["lexemes"] == 4
        assert db.execute("SELECT count(*) FROM lexeme WHERE dataset = 'monwn'").fetchone() == (4,)
    finally:
        db.rollback()
