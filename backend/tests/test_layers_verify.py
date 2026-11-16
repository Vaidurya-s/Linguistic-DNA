"""verify-link: re-reads the CLDF source and checks the stored link. Synthetic fixtures."""

import shutil
from pathlib import Path

import pytest

from app.cli import main
from app.importers.cldf_wordlist import import_cldf_wordlist
from app.layers.verify import cldf_dir, verify_link, verify_links

FIXTURE = Path(__file__).parent / "fixtures" / "cognate_mini"


@pytest.fixture
def world(db, tmp_path):
    """The cognate fixture imported as dataset 'lsi' (all languages) and a copy of its CLDF
    files under <raw>/lsi/cldf that tests may damage."""
    raw = tmp_path / "raw"
    shutil.copytree(FIXTURE, raw / "lsi" / "cldf")
    (raw / "lsi" / "cldf" / "borrowings.csv").write_text(
        "ID,Target_Form_ID,Source_Form_ID,Source_word,Source_languoid_glottocode,Source_certain\n"
        "b1,Bengali-tooth,Hindi-tooth,,,true\n"
        "b2,Hindi-tooth,,dantaḥ,sans1269,false\n",
        encoding="utf-8",
    )
    import_cldf_wordlist(db, raw / "lsi" / "cldf", "lsi", "fixture", all_languages=True)
    yield db, raw
    db.rollback()


def ids(db, type_id):
    return [
        r[0]
        for r in db.execute(
            "SELECT id FROM relationship WHERE dataset = 'lsi' AND type_id = %s ORDER BY id",
            (type_id,),
        )
    ]


def edit(raw: Path, name: str, old: str, new: str) -> None:
    p = raw / "lsi" / "cldf" / name
    text = p.read_text(encoding="utf-8")
    assert old in text
    p.write_text(text.replace(old, new), encoding="utf-8")


def test_every_imported_link_verifies_against_its_source(world):
    db, raw = world
    rels = ids(db, "cognate") + ids(db, "borrowed_from")
    assert len(rels) == 5
    results = verify_links(db, rels, raw)
    assert {r.status for r in results.values()} == {"pass"}, [r.reasons for r in results.values()]
    assert all(r.dataset == "lsi" for r in results.values())


def test_changed_form_text_is_detected(world):
    db, raw = world
    edit(raw, "forms.csv", "dā̃t,dā̃t,fixture", "XXX,XXX,fixture")
    res = verify_links(db, ids(db, "cognate"), raw)
    reasons = {x for r in res.values() for x in r.reasons}
    assert any(x.endswith("_form_text_differs") for x in reasons)
    assert any(r.status == "pass" for r in res.values())  # the link between the other two forms


def test_form_removed_from_cognate_set_or_moved_to_another_set(world):
    db, raw = world
    edit(raw, "cognates.csv", "c3,English-tooth,tooth-1", "c3,English-tooth,tooth-2")
    res = verify_links(db, ids(db, "cognate"), raw)
    assert any("not_in_cited_cognate_set" in x for r in res.values() for x in r.reasons)
    edit(raw, "cognates.csv", "c1,Hindi-tooth,tooth-1\n", "")
    res = verify_links(db, ids(db, "cognate"), raw)
    assert sum(r.status == "fail" for r in res.values()) >= 2


def test_missing_source_form_and_missing_table(world):
    db, raw = world
    edit(raw, "forms.csv", "English-tooth,English,tooth,tooth,tooth,fixture,\n", "")
    res = verify_links(db, ids(db, "cognate"), raw)
    assert any("form_missing_in_source" in x for r in res.values() for x in r.reasons)
    (raw / "lsi" / "cldf" / "cognates.csv").unlink()
    res = verify_links(db, ids(db, "cognate"), raw)
    assert any("source_has_no_cognates_table" in x for r in res.values() for x in r.reasons)


def test_borrowing_checks_borrowed_word_donor_and_row(world):
    db, raw = world
    ok = verify_links(db, ids(db, "borrowed_from"), raw)
    assert {r.status for r in ok.values()} == {"pass"}
    edit(raw, "borrowings.csv", "b1,Bengali-tooth,Hindi-tooth", "b1,Hindi-tooth,Hindi-tooth")
    edit(raw, "borrowings.csv", "dantaḥ", "danta")
    bad = verify_links(db, ids(db, "borrowed_from"), raw)
    reasons = {x for r in bad.values() for x in r.reasons}
    assert "borrowed_word_differs_from_source_target_form" in reasons
    assert "donor_word_differs_from_source" in reasons
    edit(raw, "borrowings.csv", "b2,", "b9,")
    assert any(
        "borrowing_row_missing_in_source" in r.reasons
        for r in verify_links(db, ids(db, "borrowed_from"), raw).values()
    )


def test_evidence_locator_must_match_the_link(world):
    db, raw = world
    (rid,) = [i for i in ids(db, "cognate")][:1]
    db.execute("UPDATE evidence SET locator = 'other-set' WHERE relationship_id = %s", (rid,))
    assert "evidence_locator_differs_from_link_record" in verify_link(db, rid, raw).reasons
    db.execute("DELETE FROM evidence WHERE relationship_id = %s", (rid,))
    assert "no_evidence_row" in verify_link(db, rid, raw).reasons


def test_unsupported_datasets_and_unknown_links(world):
    db, raw = world
    jambu = db.execute("SELECT id FROM relationship WHERE dataset = 'jambu' LIMIT 1").fetchone()[0]
    res = verify_link(db, jambu, raw)
    assert res.status == "unsupported" and res.line().startswith("unsupported: ")
    missing = verify_link(db, "rel_does_not_exist", raw)
    assert missing.status == "fail" and missing.reasons == ["relationship_not_found"]
    shutil.rmtree(raw / "lsi")
    gone = verify_link(db, ids(db, "cognate")[0], raw)
    assert gone.status == "unsupported" and "no CLDF source table" in gone.reasons[0]
    assert cldf_dir("lsi", raw) is None


def test_cli_exit_codes(imported_db, capsys):
    from app.importers.common import connect

    with connect(imported_db) as c:
        jambu = c.execute("SELECT id FROM relationship WHERE dataset = 'jambu' LIMIT 1").fetchone()[
            0
        ]
    assert main(["--database-url", imported_db, "verify-link", jambu]) == 0
    assert capsys.readouterr().out.startswith("unsupported:")
    assert main(["--database-url", imported_db, "verify-link", "rel_nope"]) == 1
    assert capsys.readouterr().out.startswith("fail:")
