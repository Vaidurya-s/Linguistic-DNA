"""Calibration of the candidate layer from expert cognate judgements, on a synthetic CLDF set.

Everything runs inside the test transaction (rolled back), so nothing is kept."""

import csv
import json

import pytest

from app.layers import calibrate as cal
from app.layers import candidate as cand
from app.layers.candidate import ensure_schema, load_calibration

WORDS = ["apple", "bridge", "candle", "dragon", "engine", "forest", "garden", "hammer"]
LANGS = {  # IE-CoR language id -> (database language id, Glottolog classification path)
    "L1": ("cal-a", ["fam", "x", "br1", "sub1"]),
    "L2": ("cal-b", ["fam", "x", "br1", "sub1"]),
    "L3": ("cal-c", ["fam", "x", "br2"]),
}
VARIANT = {"a": "e", "p": "b", "c": "g", "d": "t", "f": "v", "h": "k"}  # voicing-like changes


def write_cldf(path, concepts):
    """Per concept: L1 and L2 hold cognate forms (second one a voicing variant), L3 an unrelated
    form in its own cognate set."""
    forms, cognates = [], []
    for c in concepts:
        w = WORDS[int(c[2:]) % len(WORDS)]
        for lang, form, sset in (
            ("L1", w, f"{c}-s1"),
            ("L2", VARIANT.get(w[0], w[0]) + w[1:], f"{c}-s1"),
            ("L3", "mubo", f"{c}-s2"),
        ):
            fid = f"{c}-{lang}"
            forms.append(
                {"ID": fid, "Language_ID": lang, "Parameter_ID": c, "Form": form, "Loan": ""}
            )
            cognates.append({"Form_ID": fid, "Cognateset_ID": sset})
    cldf = path / "iecor" / "cldf"
    cldf.mkdir(parents=True)
    for name, rows in (("forms.csv", forms), ("cognates.csv", cognates)):
        with open(cldf / name, "w", newline="", encoding="utf-8") as fh:
            w_ = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w_.writeheader()
            w_.writerows(rows)
    return forms


@pytest.fixture
def world(db, tmp_path):
    concepts = [f"ct{i}" for i in range(24)]
    assert sum(cal.half_of(c) == "dev" for c in concepts) >= 6
    forms = write_cldf(tmp_path, concepts)
    for lid, path in LANGS.values():
        db.execute(
            "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
            " VALUES (%s, %s, 'modern', false, true, %s::jsonb)",
            (lid, lid, json.dumps({"classification_path": path})),
        )
    ensure_schema(db)
    for f in forms:
        lid = LANGS[f["Language_ID"]][0]
        word = f["Form"]
        c = f["Parameter_ID"]
        gloss = WORDS[int(c[2:]) % len(WORDS)]
        n = f["ID"]
        # the held-out source itself (never scored against), and an open dataset to score on
        for ds, suffix in (("iecor", "ie"), ("wiktionary", "wk")):
            db.execute(
                "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key, gloss,"
                " reconstruction_status, dataset, source_id, source_record_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, 'attested', %s, 'jambu', %s)",
                (
                    f"{suffix}_{n}",
                    lid,
                    word,
                    word,
                    word,
                    gloss,
                    ds,
                    n if ds == "iecor" else f"w{n}",
                ),
            )
    yield db, tmp_path
    db.rollback()


def test_half_is_the_md5_parity_of_the_concept():
    halves = {cal.half_of(f"ct{i}") for i in range(24)}
    assert halves == {"dev", "test"}
    assert cal.half_of("ct3") == cal.half_of("ct3")


def test_gold_pairs_are_seeded_cross_language_and_balanced_by_construction(world):
    db, tmp = world
    forms, sets_of, members, _all = cal.read_cldf(tmp / "iecor" / "cldf")
    key = cal._word_keys(db, sorted(forms))
    a = cal.gold_pairs(forms, sets_of, members, key, n_pos=100, n_neg=100, seed=1)
    b = cal.gold_pairs(forms, sets_of, members, key, n_pos=100, n_neg=100, seed=1)
    assert a == b  # seeded
    pos = [r for r in a if r["label"]]
    neg = [r for r in a if not r["label"]]
    assert len(pos) == 24  # one cross-language cognate pair per concept
    assert neg and all(sets_of[r["id_a"]].isdisjoint(sets_of[r["id_b"]]) for r in neg)
    assert all(key[r["id_a"]][0] != key[r["id_b"]][0] for r in a)


def test_calibrate_stores_a_monotone_table_fitted_on_the_dev_half(world):
    db, tmp = world
    out = cal.calibrate(db, tmp)
    assert out["pairs"]["dev"] > 0 and out["pairs"]["test"] > 0
    assert out["pass_gate"]["gloss"] > 0
    table = load_calibration(db, cand.DEFAULT_METHOD, "gloss")
    assert table and out["bins"]["gloss/all"] == len(table)
    by_bin = [table[b][0] for b in sorted(table)]
    assert by_bin == sorted(by_bin)  # precision never falls as the score rises
    assert by_bin[-1] == 1.0 and by_bin[0] == 0.0  # similar forms are cognate, unlike ones not
    # n_dev counts only dev pairs of the gate: fewer than all pairs, more than none
    n_dev = sum(n for _p, n in table.values())
    assert 0 < n_dev <= out["pairs"]["dev"]
    # strata: the two close languages are one sub-branch, L3 is another branch
    assert ("gloss/same_subbranch" in out["bins"]) and ("gloss/same_branch" not in out["bins"])
    assert "gloss/cross_branch" in out["bins"]


def test_the_held_out_dataset_is_never_a_scoring_source(world):
    db, tmp = world
    db.execute("DELETE FROM lexeme WHERE dataset = 'wiktionary'")  # only IE-CoR itself is left
    out = cal.calibrate(db, tmp)
    assert out["pass_gate"] == {"gloss": 0, "concept": 0}
    assert out["bins"] == {}
    assert load_calibration(db, cand.DEFAULT_METHOD, "gloss") == {}


def test_dry_run_writes_nothing_and_a_rerun_replaces(world):
    db, tmp = world
    out = cal.calibrate(db, tmp, store=False)
    assert out["bins"] and load_calibration(db, cand.DEFAULT_METHOD, "gloss") == {}
    cal.calibrate(db, tmp)
    first = load_calibration(db, cand.DEFAULT_METHOD, "gloss")
    cal.calibrate(db, tmp)
    assert load_calibration(db, cand.DEFAULT_METHOD, "gloss") == first


def test_missing_iecor_files_are_an_error(db, tmp_path):
    with pytest.raises(FileNotFoundError):
        cal.calibrate(db, tmp_path)
