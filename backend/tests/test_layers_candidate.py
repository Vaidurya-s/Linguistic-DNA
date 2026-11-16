"""Candidate layer: sound-aware scoring, gates, calibration and retrieval, on synthetic data.

Everything runs inside the test transaction (rolled back), so nothing is kept."""

import psycopg
import pytest

from app.layers import candidate as cand
from app.layers.candidate import (
    METHODS,
    bin_of,
    build_gloss_tokens,
    calibrated_precision,
    candidates_for,
    clade_stratum,
    concept_tokens,
    ensure_schema,
    fit_calibration,
    gate_passes,
    gloss_tokens,
    load_calibration,
    materialise_candidates,
    score,
    scoring_text,
    sound_classes,
    store_calibration,
)

# ---- scoring (no database)


@pytest.mark.parametrize("method", sorted(METHODS))
def test_scores_are_symmetric_bounded_and_one_for_identical(method):
    words = ["pater", "father", "padre", "water", "wasser", "night", "nacht", "ab", "", "x"]
    for a in words:
        for b in words:
            s = score(method, a, b)
            assert 0.0 <= s <= 1.0
            assert abs(s - score(method, b, a)) < 1e-9
        if a:
            assert score(method, a, a) == 1.0


def test_sound_classes_ignore_voicing_diacritics_and_double_letters():
    assert sound_classes("pàter") == sound_classes("pater")
    assert sound_classes("bader") == sound_classes("pater")  # b~p, d~t
    assert sound_classes("matter") == sound_classes("mater")
    assert sound_classes("nacht") == sound_classes("nakt") == "NAKT"
    assert sound_classes("ṭ") == sound_classes("t")
    assert sound_classes("πατήρ") == sound_classes("pater")  # Greek read as letters, marks gone
    assert sound_classes("ночь") == "NOC"  # Cyrillic: soft sign dropped, ч an affricate
    assert sound_classes("*h₂ent-") == sound_classes("hent")  # markers and subscripts dropped


def test_sound_aware_scores_beat_plain_edit_distance_on_regular_correspondences():
    # voiced/voiceless and t/d~θ shifts that Levenshtein counts as full mismatches
    assert score("sca", "pater", "father") > score("lev", "pater", "father")
    assert score("sca_c", "night", "nacht") > score("lev", "night", "nacht")
    # and unrelated words stay low
    assert score("sca_c", "pater", "mulier") < 0.5
    assert score("sca", "water", "tree") < score("sca", "water", "wasser")


def test_scoring_text_prefers_transliteration_then_known_letters_then_search_key():
    assert scoring_text("πατήρ", "patēr", "pater") == "patēr"
    assert scoring_text("पिता", None, "pita") == "pita"  # native script: romanised key
    assert scoring_text("pater", None, "pater") == "pater"
    assert scoring_text("πατήρ", None, "pater") == "πατήρ"  # Greek is in the class table


# ---- gloss gate


def test_gloss_tokens_keep_content_words_only():
    assert gloss_tokens("water") == ["water"]
    assert gloss_tokens("to learn") == ["learn"]
    assert gloss_tokens("mobility (the ability to move; capacity for movement)") == ["mobility"]
    assert gloss_tokens("trash, garbage") == ["trash", "garbage"]
    assert gloss_tokens(None) == [] and gloss_tokens("") == []


@pytest.mark.parametrize(
    "gloss",
    [
        "alternative form of unde",
        "Alternative form of glyptic.",
        "romanization of 𐍃𐌼𐌰𐌺𐌺𐌰𐌽𐍃",
        "plural of cat",
        "genitive singular of mater",
        "obsolete spelling of night",
    ],
)
def test_form_of_glosses_give_no_tokens(gloss):
    assert gloss_tokens(gloss) == []


def test_concept_tokens_and_gate_passes():
    assert concept_tokens("TO BREAK") == ["break"]
    assert gate_passes("gloss", ["water"], ["water", "river"]) == "gloss"
    assert gate_passes("gloss", ["water"], ["fire"]) is None
    assert gate_passes("concept", ["water"], ["water"]) is None  # concept gate needs a concept
    assert gate_passes("concept", [], [], ["c1"], ["c1", "c2"]) == "concept"
    assert gate_passes("gloss", [], [], ["c1"], ["c1"]) == "concept"  # gloss gate includes concepts


# ---- calibration


def test_bins():
    assert bin_of(0.0) == 0.0 and bin_of(0.049) == 0.0 and bin_of(0.05) == 0.05
    assert bin_of(0.7) == 0.7 and bin_of(1.0) == 0.95


def test_fit_calibration_is_monotone_and_supports_weights():
    scores = [0.1, 0.1, 0.5, 0.5, 0.5, 0.9, 0.9]
    labels = [0, 1, 0, 1, 0, 1, 1]  # the 0.1 bin (0.5) is above the 0.5 bin (0.33): pooled
    rows = fit_calibration(scores, labels)
    p = [r["precision_balanced"] for r in rows]
    assert p == sorted(p)
    assert rows[-1]["precision_balanced"] == 1.0 and rows[-1]["n"] == 2
    # natural-mix weights: negatives weigh 4x
    w = [4.0 if y == 0 else 1.0 for y in labels]
    rows_w = fit_calibration(scores, labels, w)
    top = rows_w[-1]
    assert top["precision"] == 1.0
    mid = next(r for r in rows_w if r["score_bin"] == 0.5)
    assert mid["precision"] < next(r for r in rows if r["score_bin"] == 0.5)["precision_balanced"]


@pytest.fixture
def g(db):
    """A small world: three IE languages, one non-IE, one constructed. Rolled back afterwards."""
    db.execute(
        "INSERT INTO language_family (id, name) VALUES ('indo1319', 'IE') ON CONFLICT DO NOTHING"
    )
    db.execute(
        "INSERT INTO language_family (id, name) VALUES ('xtst9999', 'Other') ON CONFLICT DO NOTHING"
    )
    for lid, fam in (
        ("lc-en", "indo1319"),
        ("lc-de", "indo1319"),
        ("lc-la", "indo1319"),
        ("lc-xx", "xtst9999"),
        ("conlang-t1", None),
        ("conlang-t2", None),
    ):
        db.execute(
            "INSERT INTO language (id, name, family_id, role, is_proto, is_enabled, metadata_json)"
            " VALUES (%s, %s, %s, 'modern', false, true, '{}')",
            (lid, lid, fam),
        )
    ensure_schema(db)
    yield db
    db.rollback()


def lex(db, lid, lang, form, gloss=None, dataset="jambu", concept=None, kind="word"):
    db.execute(
        "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key, gloss,"
        " reconstruction_status, dataset, source_id, source_record_id, form_kind)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'attested', %s, 'jambu', %s, %s)",
        (lid, lang, form, form, form.lower(), gloss, dataset, lid, kind),
    )
    if concept:
        db.execute(
            "INSERT INTO concept (id, label) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (concept, concept.split(":")[-1].upper()),
        )
        db.execute(
            "INSERT INTO lexeme_concept (lexeme_id, concept_id) VALUES (%s, %s)", (lid, concept)
        )


def test_calibration_roundtrip(g):
    rows = fit_calibration([0.2, 0.2, 0.8, 0.8], [0, 0, 1, 1])
    assert store_calibration(g, "sca_c", "gloss", rows) == 2
    table = load_calibration(g, "sca_c", "gloss")
    assert calibrated_precision(table, 0.83) == (1.0, 2)
    assert calibrated_precision(table, 0.21) == (0.0, 2)
    assert calibrated_precision(table, 0.5) == (None, 0)
    assert calibrated_precision(table, 0.87) == (1.0, 2)  # empty bin: nearest lower bin
    assert calibrated_precision(table, 0.1) == (None, 0)  # below every fitted bin
    store_calibration(g, "sca_c", "gloss", rows[:1])  # replaces
    assert len(load_calibration(g, "sca_c", "gloss")) == 1


# ---- retrieval


@pytest.fixture
def world(g):
    lex(g, "c_en", "lc-en", "father", gloss="father", concept="concepticon:1")
    lex(g, "c_de", "lc-de", "vater", gloss="father", concept="concepticon:1")
    lex(g, "c_la", "lc-la", "pater", gloss="male parent; father")
    lex(g, "c_la_dup", "lc-la", "pater", gloss="father", dataset="other")
    lex(g, "c_xx", "lc-xx", "pita", gloss="father")
    lex(g, "c_en2", "lc-en", "dad", gloss="father")  # same language as the query
    lex(g, "c_de_far", "lc-de", "tisch", gloss="table", concept="concepticon:2")
    lex(g, "c_la_form", "lc-la", "patris", gloss="genitive singular of pater")
    lex(g, "c_la_phrase", "lc-la", "pater noster", gloss="father", kind="phrase")
    lex(g, "c_con", "conlang-t1", "pater", gloss="father")
    lex(g, "c_con2", "conlang-t2", "vater", gloss="father")
    build_gloss_tokens(g)
    return g


def test_gloss_gate_ranks_by_sound_score_and_dedupes(world):
    got = candidates_for(world, "c_en", k=10, gate="gloss", method="sca_c")
    ids = [c.lexeme_id for c in got]
    # same-language, other-meaning, form-of, phrase and constructed-language words are absent
    assert "c_en2" not in ids and "c_de_far" not in ids and "c_la_form" not in ids
    assert "c_la_phrase" not in ids and "c_con" not in ids and "c_con2" not in ids
    by_lang = {c.language_id: c for c in got}
    assert set(by_lang) == {"lc-de", "lc-la", "lc-xx"}
    assert [c.score for c in got] == sorted((c.score for c in got), reverse=True)
    assert by_lang["lc-la"].n_sources == 2  # same spelling in two datasets: one row
    assert by_lang["lc-de"].gate_via == "concept"  # shares the concept link
    assert by_lang["lc-la"].gate_via == "gloss"
    for c in got:
        assert c.evidence_kind == "computed" and c.method == "sca_c" and c.gate == "gloss"


def test_concept_gate_uses_concept_links_only(world):
    got = candidates_for(world, "c_en", gate="concept", method="sca_c")
    assert [c.lexeme_id for c in got] == ["c_de"]
    # a word without concept links has no concept-gate candidates
    assert candidates_for(world, "c_la", gate="concept") == []


def test_k_min_score_datasets_and_constructed_query(world):
    assert len(candidates_for(world, "c_en", k=1, gate="gloss")) == 1
    hi = candidates_for(world, "c_en", gate="gloss", min_score=0.99)
    assert all(c.score >= 0.99 for c in hi)
    only_other = candidates_for(world, "c_en", gate="gloss", datasets=["other"])
    assert [c.lexeme_id for c in only_other] == ["c_la_dup"]
    assert candidates_for(world, "c_con", gate="gloss") == []  # a constructed language gets none


def test_calibrated_precision_only_inside_the_indo_european_domain(world):
    rows = fit_calibration([0.1, 0.85] * 20, [0, 1] * 20)
    store_calibration(world, "sca_c", "gloss", rows)
    got = {c.language_id: c for c in candidates_for(world, "c_en", gate="gloss", method="sca_c")}
    assert got["lc-de"].calibrated and got["lc-de"].calibrated_precision is not None
    assert got["lc-de"].calibration_n >= 1
    assert not got["lc-xx"].calibrated and got["lc-xx"].calibrated_precision is None
    # a query word of a non-IE language gets no calibrated precision either
    from_xx = candidates_for(world, "c_xx", gate="gloss", method="sca_c")
    assert from_xx and all(c.calibrated_precision is None for c in from_xx)


def test_without_calibration_the_precision_is_none_not_a_guess(world):
    got = candidates_for(world, "c_en", gate="gloss", method="blend")
    assert got and all(c.calibrated_precision is None for c in got)


def test_bad_arguments(world):
    with pytest.raises(ValueError):
        candidates_for(world, "c_en", gate="oracle")
    with pytest.raises(ValueError):
        candidates_for(world, "c_en", method="nope")
    with pytest.raises(ValueError):
        candidates_for(world, "no_such_lexeme")


def test_materialise_writes_only_layer_rows_with_computed_kind(world):
    before = world.execute("SELECT count(*) FROM relationship").fetchone()[0]
    counts = materialise_candidates(world, ["c_en"], k=5, gate="gloss", method="sca_c")
    assert counts["pairs"] == 3
    rows = world.execute(
        "SELECT a, b, method, gate, evidence_kind, score FROM layers.candidate_pair ORDER BY a, b"
    ).fetchall()
    assert len(rows) == 3
    assert all(r[0] < r[1] and r[4] == "computed" and r[2] == "sca_c" for r in rows)
    materialise_candidates(world, ["c_en"], k=5, gate="gloss", method="sca_c")  # idempotent
    assert world.execute("SELECT count(*) FROM layers.candidate_pair").fetchone()[0] == 3
    assert world.execute("SELECT count(*) FROM relationship").fetchone()[0] == before
    # the pair is stored once even when asked from the other side
    materialise_candidates(world, ["c_de"], k=5, gate="gloss", method="sca_c")
    assert (
        world.execute(
            "SELECT count(*) FROM layers.candidate_pair"
            " WHERE a IN ('c_de','c_en') AND b IN ('c_de','c_en')"
        ).fetchone()[0]
        == 1
    )


def test_a_candidate_can_never_be_stored_as_documented(world):
    with pytest.raises(psycopg.errors.CheckViolation):
        world.execute(
            "INSERT INTO layers.candidate_pair (a, b, method, score, gate, gate_via, evidence_kind)"
            " VALUES ('x', 'y', 'sca', 0.9, 'gloss', 'gloss', 'documented')"
        )


def test_default_method_is_a_known_method():
    assert cand.DEFAULT_METHOD in METHODS


def test_clade_stratum():
    ge = ["indo1319", "clas1257", "germ1287", "nort3152", "west2793"]
    ge2 = ["indo1319", "clas1257", "germ1287", "nort3152", "nort3175"]
    got = ["indo1319", "clas1257", "germ1287", "east2805"]
    sl = ["indo1319", "clas1257", "balt1263", "slav1255"]
    assert clade_stratum(ge, ge2) == "same_subbranch"
    assert clade_stratum(ge, got) == "same_branch"
    assert clade_stratum(ge, sl) == "cross_branch"
    assert clade_stratum(ge, ["indo1319"]) == "unknown" and clade_stratum(None, ge) == "unknown"


def test_stratum_calibration_replaces_the_overall_one(world):
    world.execute(
        "UPDATE language SET metadata_json = %s::jsonb WHERE id = 'lc-en'",
        ('{"classification_path": ["indo1319", "clas1257", "germ1287", "nort3152", "west2793"]}',),
    )
    world.execute(
        "UPDATE language SET metadata_json = %s::jsonb WHERE id = 'lc-de'",
        ('{"classification_path": ["indo1319", "clas1257", "germ1287", "nort3152", "high1289"]}',),
    )
    world.execute(
        "UPDATE language SET metadata_json = %s::jsonb WHERE id = 'lc-la'",
        ('{"classification_path": ["indo1319", "clas1257", "ital1284", "lati1261"]}',),
    )
    scores, labels = [0.1, 0.8] * 20, [0, 1] * 20
    store_calibration(world, "blend", "gloss", fit_calibration(scores, labels))  # overall: high
    got = {c.language_id: c for c in candidates_for(world, "c_en", gate="gloss", method="blend")}
    assert got["lc-de"].stratum == "same_subbranch" and got["lc-la"].stratum == "cross_branch"
    assert got["lc-de"].calibrated_precision is not None  # no strata fitted: overall is used
    # once a stratum is fitted, only that stratum's table counts; the others get no number
    flat = [{"score_bin": b / 20, "precision": 0.2, "precision_balanced": 0.2, "n": 9, "n_pos": 2}
            for b in range(20)]  # fmt: skip
    store_calibration(world, "blend", "gloss", flat, stratum="cross_branch")
    got = {c.language_id: c for c in candidates_for(world, "c_en", gate="gloss", method="blend")}
    assert got["lc-la"].calibrated_precision == pytest.approx(0.2)
    assert got["lc-de"].calibrated_precision is None  # same_subbranch not fitted: no guess
