"""verify-link for the non-CLDF datasets: Wiktionary, Wikidata Lexemes, CDSL, DPD.

Synthetic mini sources only. Each test imports a mini source into the test database, builds the
index (or lets the checker re-derive the file), checks that every stored link passes, and then
damages the database or the source on purpose to see that the check notices.
"""

import gzip
import json
import shutil
import sqlite3
import tarfile
from pathlib import Path

import pytest

from app.cli import main
from app.importers.cdsl import import_cdsl_mw
from app.importers.dpd import import_dpd
from app.importers.wikidata_lexemes import import_wikidata_lexemes
from app.importers.wiktionary import import_wiktionary
from app.layers import verify_sources as vs
from app.layers.verify import verify_link, verify_links

CDSL = Path(__file__).parent / "fixtures" / "cdsl_mini" / "mw.txt"


@pytest.fixture(autouse=True)
def scratch(tmp_path, monkeypatch):
    """Indexes and caches go to a temporary folder, never the project's logs."""
    monkeypatch.setenv(vs.SCRATCH_ENV, str(tmp_path / "scratch"))
    return tmp_path / "scratch"


def rel_ids(db, dataset: str) -> list[str]:
    rows = db.execute("SELECT id FROM relationship WHERE dataset = %s ORDER BY id", (dataset,))
    return [r[0] for r in rows]


# ------------------------------------------------------------------------------- Wiktionary


def entry(word, code, lang, text="", templates=(), descendants=()):
    return {
        "word": word,
        "lang": lang,
        "lang_code": code,
        "senses": [{"glosses": ["x"]}],
        "etymology_text": text,
        "etymology_templates": [{"name": n, "args": a} for n, a in templates],
        "descendants": list(descendants),
    }


DUMP = [
    entry("bicycle", "en", "English"),
    entry(
        "bajs",
        "sh",
        "Serbo-Croatian",
        "Borrowed and shortened from English bicycle.",
        [("der", {"1": "sh", "2": "en", "3": "bicycle"})],
    ),
    entry("fiets", "nl", "Dutch", templates=[("inh", {"1": "nl", "2": "gem-pro", "3": "*fiet"})]),
    entry("vader", "nl", "Dutch", templates=[("cog", {"1": "de", "2": "Vater"})]),
    entry("Vater", "de", "German"),
    entry(
        "biljardbord",
        "nn",
        "Norwegian Nynorsk",
        "From biljard + bord.",
        [("af", {"1": "nn", "2": "biljard", "3": "bord"})],
    ),
    entry(
        "camera",
        "la",
        "Latin",
        descendants=[
            {"lang_code": "it", "word": "camera", "tags": []},
            {"lang_code": "fr", "word": "chambre", "tags": ["borrowed"]},
            {"lang_code": "sv", "word": "kamera", "tags": []},
        ],
    ),
    entry("camera", "it", "Italian", "Inherited from Latin camera."),
    entry("kamera", "sv", "Swedish", "Borrowed from Latin camera."),
    entry("chambre", "fr", "French"),
]


@pytest.fixture
def wkt(db, tmp_path, scratch):
    """The mini dump imported as 'wiktionary' and indexed; yields (db, raw root)."""
    raw = tmp_path / "raw"
    (raw / "wiktionary").mkdir(parents=True)
    dump = raw / "wiktionary" / vs.DUMP_NAME
    with gzip.open(dump, "wt", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(e, ensure_ascii=False) for e in DUMP) + "\n")
    import_wiktionary(db, [dump], "fixture", {}, all_languages=True)
    vs.build_wiktionary_index(dump, vs.wiktionary_index_dir(scratch), workers=2)
    yield db, raw
    db.rollback()


def link(db, record: str) -> str:
    return db.execute(
        "SELECT id FROM relationship WHERE dataset = 'wiktionary' AND source_record_id = %s"
        " ORDER BY id LIMIT 1",
        (record,),
    ).fetchone()[0]


def test_index_lookup_is_a_seek_to_the_reduced_entry(wkt, scratch):
    idx = vs.WiktionaryIndex(vs.wiktionary_index_dir(scratch))
    try:
        rec = idx.by_key("sh:bajs")
        assert len(rec) == 1 and rec[0]["t"].startswith("Borrowed and shortened")
        assert [t["name"] for t in rec[0]["e"]] == ["der"]
        assert idx.by_key("sh:nothing") == []
        assert idx.by_title("camera") and {r["c"] for r in idx.by_title("camera")} == {"la", "it"}
        assert idx.names["nn"] == "Norwegian Nynorsk"
        assert idx.meta["lines"] == str(len(DUMP))
    finally:
        idx.close()


def test_every_imported_wiktionary_link_verifies_against_the_dump(wkt):
    db, raw = wkt
    ids = rel_ids(db, "wiktionary")
    types = {r[0] for r in db.execute("SELECT DISTINCT type_id FROM relationship")}
    assert {"borrowed_from", "inherited_form", "cognate", "has_component"} <= types
    results = verify_links(db, ids, raw)
    assert len(ids) >= 8
    assert {r.status for r in results.values()} == {"pass"}, [
        (i, r.reasons) for i, r in results.items() if r.reasons
    ]


def test_retyped_links_are_checked_against_the_entry_text(wkt):
    db, raw = wkt
    der = link(db, "bajs#der")
    desc = link(db, "camera#desc")
    labels = {
        r[0]
        for r in db.execute(
            "SELECT original_label FROM relationship WHERE dataset = 'wiktionary'"
            " AND original_label LIKE '%% + entry etymology text'"
        )
    }
    assert labels == {"{{der}} + entry etymology text", "{{desc}} + entry etymology text"}
    assert verify_link(db, der, raw).status == "pass"
    assert verify_link(db, desc, raw).status == "pass"
    # a retype the text does not support: the entry's own text says it was inherited
    db.execute("UPDATE relationship SET type_id = 'inherited_form' WHERE id = %s", (der,))
    res = verify_link(db, der, raw)
    assert res.status == "fail" and any(w.startswith("type_differs") for w in res.reasons)
    db.execute("UPDATE relationship SET type_id = 'borrowed_from' WHERE id = %s", (der,))
    db.execute("UPDATE relationship SET original_label = '{{der}}' WHERE id = %s", (der,))
    res = verify_link(db, der, raw)
    assert res.status == "fail" and any(w.startswith("type_differs") for w in res.reasons)


def test_wiktionary_damage_by_savepoint(wkt):
    db, raw = wkt
    rid = link(db, "fiets#inh")
    other = link(db, "vader#cog")
    target = db.execute("SELECT target_lexeme_id FROM relationship WHERE id = %s", (other,))
    other_target = target.fetchone()[0]

    def damage(sql: str, *args) -> object:
        with db.transaction(force_rollback=True):
            db.execute(sql, args)
            return verify_link(db, rid, raw)

    res = damage("UPDATE relationship SET type_id = 'borrowed_from' WHERE id = %s", rid)
    assert res.status == "fail" and any(w.startswith("type_differs") for w in res.reasons)
    res = damage("UPDATE relationship SET target_lexeme_id = %s WHERE id = %s", other_target, rid)
    assert res.status == "fail" and "tgt_lexeme_is_not_the_word_in_the_dump" not in res.reasons
    assert any(w.startswith("tgt_") for w in res.reasons)
    res = damage("UPDATE relationship SET rank = 9 WHERE id = %s", rid)
    assert res.reasons == ["rank_differs"]
    res = damage("DELETE FROM evidence WHERE relationship_id = %s", rid)
    assert res.reasons == ["no_evidence_row"]
    res = damage(
        "UPDATE evidence SET locator = 'https://en.wiktionary.org/wiki/x'"
        " WHERE relationship_id = %s",
        rid,
    )
    assert "evidence_locator_is_not_the_page" in res.reasons
    res = damage("UPDATE relationship SET source_record_id = 'zzz#inh' WHERE id = %s", rid)
    assert res.status == "fail"
    res = damage("UPDATE relationship SET source_record_id = 'fiets#der' WHERE id = %s", rid)
    assert res.reasons == ["template_differs_from_the_one_in_the_dump"] or res.status == "fail"
    assert verify_link(db, rid, raw).status == "pass"  # the damage was rolled back


def test_target_word_not_in_the_entry_and_missing_entry(wkt):
    db, raw = wkt
    rid = link(db, "fiets#inh")
    stranger = db.execute(
        "SELECT id, source_record_id FROM lexeme WHERE dataset = 'wiktionary'"
        " AND source_record_id = 'it:camera'"
    ).fetchone()
    with db.transaction(force_rollback=True):
        db.execute(
            "UPDATE relationship SET target_lexeme_id = %s WHERE id = %s", (stranger[0], rid)
        )
        res = verify_link(db, rid, raw)
    assert res.status == "fail" and any(w.startswith("tgt_") for w in res.reasons)
    with db.transaction(force_rollback=True):
        db.execute("UPDATE relationship SET source_record_id = 'zzz#inh' WHERE id = %s", (rid,))
        db.execute(
            "UPDATE lexeme SET source_record_id = 'nl:zzz' WHERE id ="
            " (SELECT source_lexeme_id FROM relationship WHERE id = %s)",
            (rid,),
        )
        assert verify_link(db, rid, raw).reasons == ["entry_not_in_dump"]


def test_wiktionary_unsupported_when_index_or_file_cannot_be_trusted(wkt, scratch):
    db, raw = wkt
    rid = link(db, "fiets#inh")
    dump = raw / "wiktionary" / vs.DUMP_NAME
    original = dump.read_bytes()
    # the raw file is no longer the file that was imported
    with gzip.open(dump, "at", encoding="utf-8") as fh:
        fh.write(json.dumps(entry("zzz", "en", "English")) + "\n")
    res = verify_link(db, rid, raw)
    assert res.status == "unsupported" and "sha256" in res.reasons[0]
    # no index
    shutil.rmtree(vs.wiktionary_index_dir(scratch))
    dump.write_bytes(original)  # the very bytes that were imported (a gzip header holds a time)
    res = verify_link(db, rid, raw)
    assert res.status == "unsupported" and "no Wiktionary index" in res.reasons[0]
    # no raw file at all
    dump.unlink()
    res = verify_link(db, rid, raw)
    assert res.status == "unsupported" and "not found" in res.reasons[0]


def test_cli_verifies_a_wiktionary_link(wkt, tmp_path, capsys, imported_db):
    db, raw = wkt
    rid = link(db, "fiets#inh")
    # the CLI opens its own connection, so the fixture's rows must be committed first
    db.commit()
    try:
        code = main(["--database-url", imported_db, "verify-link", rid, "--raw", str(raw)])
        assert code == 0
        assert capsys.readouterr().out.startswith("pass:")
    finally:
        db.execute("DELETE FROM relationship WHERE dataset = 'wiktionary'")
        db.execute("DELETE FROM lexeme WHERE dataset = 'wiktionary'")
        db.commit()


# ------------------------------------------------------------------------------- Wikidata


def wd_lexeme(lid, lang, code, lemma, derived=(), combines=()):
    claims = {}
    for prop, targets in (("P5191", derived), ("P5238", combines)):
        if targets:
            claims[prop] = [
                {
                    "id": f"{lid}${prop}-{n}",
                    "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": t}}},
                    "references": [{"snaks": {"P248": [{"datavalue": {"value": {"id": "Q1"}}}]}}]
                    if n == 1
                    else [],
                }
                for n, t in enumerate(targets, start=1)
            ]
    return {
        "id": lid,
        "language": lang,
        "lemmas": {code: {"value": lemma}},
        "senses": [{"glosses": {"en": {"value": "g"}}}],
        "claims": claims,
    }


@pytest.fixture
def wd(db, tmp_path, scratch):
    raw = tmp_path / "raw"
    (raw / "wikidata").mkdir(parents=True)
    dump = raw / "wikidata" / "wikidata-test-lexemes.json"
    lexemes = [
        wd_lexeme("L1", "Q1860", "en", "fuck", derived=["L2"]),
        wd_lexeme("L2", "Q42365", "ang", "fuccian"),
        wd_lexeme("L3", "Q1860", "en", "bookcase", combines=["L4", "L5"]),
        wd_lexeme("L4", "Q1860", "en", "book"),
        wd_lexeme("L5", "Q1860", "en", "case"),
    ]
    dump.write_text("[\n" + ",\n".join(json.dumps(x) for x in lexemes) + "\n]\n", encoding="utf-8")
    import_wikidata_lexemes(db, dump, "fixture", all_languages=True)
    vs.build_wikidata_index(dump, vs.wikidata_index_dir(scratch), workers=2)
    yield db, raw
    db.rollback()


def test_wikidata_links_verify_and_damage_is_detected(wd):
    db, raw = wd
    ids = rel_ids(db, "wikidata-lexemes")
    assert len(ids) == 3
    assert {r.status for r in verify_links(db, ids, raw).values()} == {"pass"}
    rid = db.execute(
        "SELECT id FROM relationship WHERE source_record_id LIKE 'L3$P5238-2'"
    ).fetchone()[0]

    def damage(sql: str, *args):
        with db.transaction(force_rollback=True):
            db.execute(sql, args)
            return verify_link(db, rid, raw)

    res = damage("UPDATE relationship SET type_id = 'etymon' WHERE id = %s", rid)
    assert res.status == "fail" and any(w.startswith("type_differs") for w in res.reasons)
    res = damage("UPDATE relationship SET rank = 7 WHERE id = %s", rid)
    assert res.reasons == ["rank_differs"]
    res = damage("UPDATE evidence SET citation = 'Wikidata L9$x' WHERE relationship_id = %s", rid)
    assert res.reasons == ["evidence_citation_differs"]
    res = damage("UPDATE lexeme SET form = 'bok' WHERE source_record_id = 'L5'")
    assert res.reasons == ["tgt_form_is_not_a_lemma_of_the_lexeme"]
    res = damage(
        "UPDATE relationship SET target_lexeme_id = (SELECT id FROM lexeme WHERE"
        " source_record_id = 'L4') WHERE id = %s",
        rid,
    )
    assert res.status == "fail"


def test_wikidata_unsupported_without_index(wd, scratch):
    db, raw = wd
    shutil.rmtree(vs.wikidata_index_dir(scratch))
    rid = rel_ids(db, "wikidata-lexemes")[0]
    assert verify_link(db, rid, raw).status == "unsupported"


# ----------------------------------------------------------------- re-derived datasets (CDSL, DPD)


def test_cdsl_links_rederive_from_the_raw_file(db, tmp_path):
    raw = tmp_path / "raw"
    (raw / "cdsl").mkdir(parents=True)
    shutil.copy(CDSL, raw / "cdsl" / "mw.txt")
    try:
        import_cdsl_mw(db, raw / "cdsl" / "mw.txt", "fixture")
        ids = rel_ids(db, "cdsl-mw")
        assert ids
        results = verify_links(db, ids, raw)
        assert {r.status for r in results.values()} == {"pass"}, [
            r.reasons for r in results.values()
        ]
        rid = ids[0]
        for sql, reason in (
            ("UPDATE relationship SET type_id = 'etymon' WHERE id = %s", "type_differs"),
            (
                "UPDATE relationship SET source_record_id = 'L999' WHERE id = %s",
                "source_record_differs",
            ),
            (
                "UPDATE evidence SET locator = 'p. 9, col. 9' WHERE relationship_id = %s",
                "evidence_differs",
            ),
        ):
            with db.transaction(force_rollback=True):
                db.execute(sql, (rid,))
                res = verify_link(db, rid, raw)
            assert res.status == "fail" and reason in [w.split(":")[0] for w in res.reasons]
        # a link that is not in the source at all
        with db.transaction(force_rollback=True):
            db.execute(
                "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id,"
                " direction, status, source_id, source_record_id, original_label, dataset)"
                " SELECT 'rel_made_up', source_lexeme_id, target_lexeme_id, type_id, direction,"
                " status, source_id, source_record_id, original_label, dataset"
                " FROM relationship WHERE id = %s",
                (rid,),
            )
            res = verify_link(db, "rel_made_up", raw)
        assert res.reasons == ["link_not_produced_from_the_raw_file"]
        # the raw file changed after the import: no claim
        (raw / "cdsl" / "mw.txt").write_text("<L>1<pc>1,1<k1>a<k2>a\nx\n<LEND>\n")
        res = verify_link(db, rid, raw)
        assert res.status == "unsupported" and "differs from the imported file" in res.reasons[0]
    finally:
        db.rollback()


def test_dpd_links_rederive_from_the_unpacked_database(db, tmp_path):
    raw = tmp_path / "raw"
    (raw / "dpd" / "x").mkdir(parents=True)
    path = raw / "dpd" / "x" / "dpd.db"
    src = sqlite3.connect(path)
    src.execute(
        "CREATE TABLE dpd_headwords (id INTEGER, lemma_1 TEXT, meaning_1 TEXT, meaning_2 TEXT,"
        " sanskrit TEXT, derived_from TEXT, compound_construction TEXT)"
    )
    src.executemany(
        "INSERT INTO dpd_headwords VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (3, "dharati", "holds", "", "dharati [dhṛ]", "", ""),
            (4, "na", "not", "", "na", "", ""),
            (5, "kakkasa", "harsh", "", "karkaśa", "", ""),
            (6, "akakkasa", "", "smooth", "akarkaśa (na + karkaśa)", "kakkasa", "na + kakkasa"),
        ],
    )
    src.commit()
    src.close()
    archive = raw / "dpd" / "dpd.db.tar.xz"
    with tarfile.open(archive, "w:xz") as tar:
        tar.add(path, arcname="dpd.db")
    try:
        import_dpd(db, path, archive, "fixture")
        ids = rel_ids(db, "dpd")
        assert len(ids) == 7  # sanskrit, derived and component links
        assert {r.status for r in verify_links(db, ids, raw).values()} == {"pass"}
        with db.transaction(force_rollback=True):
            db.execute("UPDATE lexeme SET form = 'kakkasa2' WHERE source_record_id = '5'")
            bad = verify_links(db, ids, raw)
        assert any("tgt_form_differs" in r.reasons for r in bad.values())
        path.unlink()  # the unpacked database is gone: no claim
        assert {r.status for r in verify_links(db, ids, raw).values()} == {"unsupported"}
    finally:
        db.rollback()


def test_dataset_import_from_another_file_is_unsupported_not_failed(imported_db, capsys):
    """The Jambu fixture was imported from files that are not the real Jambu data."""
    from app.importers.common import connect

    with connect(imported_db) as c:
        rid = c.execute("SELECT id FROM relationship WHERE dataset = 'jambu' LIMIT 1").fetchone()[0]
        res = verify_link(c, rid)
    assert res.status == "unsupported"
