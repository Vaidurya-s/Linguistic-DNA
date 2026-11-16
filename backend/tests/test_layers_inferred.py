"""Inferred layer: chains over documented ancestry, on small synthetic graphs.

Everything runs inside the test transaction (rolled back), so nothing is kept."""

import pytest

from app.layers.inferred import (
    AncestryWalker,
    ensure_schema,
    get_inferred,
    inferred_chain,
    materialise_inferred,
    stored_inferred,
)


def lang(db, lid: str) -> None:
    db.execute(
        "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
        " VALUES (%s, %s, 'modern', false, true, '{}')",
        (lid, lid),
    )


def lex(db, lid: str, language: str, form: str | None = None, dataset: str = "jambu") -> None:
    form = form or lid
    db.execute(
        "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key,"
        " reconstruction_status, dataset, source_id, source_record_id)"
        " VALUES (%s, %s, %s, %s, %s, 'attested', %s, 'jambu', %s)",
        (lid, language, form, form, form, dataset, lid),
    )


def edge(db, rid: str, src: str, tgt: str, type_id: str, dataset: str = "jambu") -> None:
    db.execute(
        "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,"
        " status, source_id, dataset) VALUES (%s, %s, %s, %s, %s, 'documented', 'jambu', %s)",
        (rid, src, tgt, type_id, "undirected" if type_id == "cognate" else "directed", dataset),
    )
    db.execute(
        "INSERT INTO evidence (relationship_id, source_id, citation) VALUES (%s, 'jambu', %s)",
        (rid, f"Citation for {rid}, p. 1"),
    )


@pytest.fixture
def g(db):
    """Three languages; tests add their own lexemes and edges. Rolled back afterwards."""
    for lid in ("la-x", "la-y", "la-z"):
        lang(db, lid)
    ensure_schema(db)
    yield db
    db.rollback()


def n_relationships(db) -> int:
    return db.execute("SELECT count(*) FROM relationship").fetchone()[0]


def test_common_ancestor_chain_is_ordered_and_cited(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p", "la-z")
    lex(g, "i_q", "la-z")
    edge(g, "ie_1", "i_a", "i_p", "inherited_form")
    edge(g, "ie_2", "i_p", "i_q", "inherited_form")
    edge(g, "ie_3", "i_b", "i_q", "etymon")
    rep: dict = {}
    c = inferred_chain(g, "i_b", "i_a", report=rep)  # arguments in any order
    assert c is not None
    assert (c.lexeme_a, c.lexeme_b) == ("i_a", "i_b")  # canonical order
    assert c.kind == "common_ancestor"
    assert c.ancestor_id == "i_q"
    assert (c.depth_a, c.depth_b, c.depth) == (2, 1, 2)
    assert c.relationship_ids == ["ie_1", "ie_2", "ie_3"]  # a up, then down to b
    assert c.types == ["inherited_form", "inherited_form", "etymon"]
    assert c.datasets == ["jambu"]
    assert rep["capped"] is False


def test_ancestor_descendant_kind(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_p", "la-y")
    edge(g, "ie_1", "i_a", "i_p", "derived_form")
    c = inferred_chain(g, "i_a", "i_p")
    assert c.kind == "b_ancestor_of_a" and c.ancestor_id == "i_p" and c.depth == 1
    c2 = inferred_chain(g, "i_p", "i_a")
    assert c2.kind == "b_ancestor_of_a" and (c2.lexeme_a, c2.lexeme_b) == ("i_a", "i_p")


def test_reconstructed_ancestor_of_is_followed_downwards(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_p", "la-y")
    edge(g, "ie_1", "i_p", "i_a", "reconstructed_ancestor_of")  # source is the ancestor
    c = inferred_chain(g, "i_a", "i_p")
    assert c is not None and c.ancestor_id == "i_p"


@pytest.mark.parametrize(
    "bad", ["borrowed_from", "calque_or_loan_translation", "contact_influence"]
)
def test_loan_edge_blocks_the_chain(g, bad):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p", "la-z")
    edge(g, "ie_1", "i_a", "i_p", bad)
    edge(g, "ie_2", "i_b", "i_p", "inherited_form")
    assert inferred_chain(g, "i_a", "i_b") is None
    # a loan in the middle of an otherwise good chain also blocks it
    lex(g, "i_m", "la-z")
    edge(g, "ie_3", "i_p", "i_m", bad)
    edge(g, "ie_4", "i_a", "i_m", "inherited_form")
    assert inferred_chain(g, "i_a", "i_b") is None


def test_loan_types_cannot_be_configured_as_ancestry(g):
    with pytest.raises(ValueError):
        AncestryWalker(g, ancestry_types=("inherited_form", "borrowed_from"))


def test_other_types_do_not_connect(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p", "la-z")
    edge(g, "ie_1", "i_a", "i_p", "has_component")
    edge(g, "ie_2", "i_b", "i_p", "variant_of")
    assert inferred_chain(g, "i_a", "i_b") is None


def test_depth_cap(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    for i in range(1, 5):
        lex(g, f"i_p{i}", "la-z")
    edge(g, "ie_a", "i_a", "i_p1", "inherited_form")
    for i in range(1, 4):
        edge(g, f"ie_p{i}", f"i_p{i}", f"i_p{i + 1}", "inherited_form")
    edge(g, "ie_b", "i_b", "i_p4", "inherited_form")
    assert inferred_chain(g, "i_a", "i_b", max_depth=4).depth == 4
    assert inferred_chain(g, "i_a", "i_b", max_depth=3) is None
    assert inferred_chain(g, "i_a", "i_b", max_depth=8).relationship_ids == [
        "ie_a",
        "ie_p1",
        "ie_p2",
        "ie_p3",
        "ie_b",
    ]


def test_shortest_chain_wins(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p", "la-z")
    lex(g, "i_far", "la-z")
    edge(g, "ie_1", "i_a", "i_far", "inherited_form")
    edge(g, "ie_2", "i_far", "i_p", "inherited_form")
    edge(g, "ie_3", "i_a", "i_p", "inherited_form")
    edge(g, "ie_4", "i_b", "i_p", "inherited_form")
    assert inferred_chain(g, "i_a", "i_b").relationship_ids == ["ie_3", "ie_4"]


def test_hub_cap_is_reported(g):
    # one word with 30 parents; only the parent sorted last leads to the other word
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    for i in range(30):
        lex(g, f"i_h{i:02d}", "la-z")
        edge(g, f"ie_h{i:02d}", "i_a", f"i_h{i:02d}", "inherited_form")
    lex(g, "i_top", "la-z")
    # depth 2 from a: h29 -> top; b -> top
    edge(g, "ie_up", "i_h29", "i_top", "inherited_form")
    edge(g, "ie_b", "i_b", "i_top", "inherited_form")
    rep: dict = {}
    assert inferred_chain(g, "i_a", "i_b", report=rep).depth == 2  # uncapped search finds it
    assert rep["capped"] is False
    rep = {}
    capped = inferred_chain(g, "i_a", "i_b", report=rep, max_frontier=10)
    assert capped is None  # the cap cut the search before h29
    assert rep["capped"] is True and rep["stats"]["frontier_capped"] >= 1
    # the node cap is reported too
    rep = {}
    assert inferred_chain(g, "i_a", "i_b", report=rep, max_nodes=5) is None
    assert rep["capped"] is True


def test_identical_words_across_datasets_are_one_node(g):
    # the same language and spelling in two datasets is one word (the project's identity)
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p1", "la-z", form="proto", dataset="jambu")
    lex(g, "i_p2", "la-z", form="proto", dataset="other")
    edge(g, "ie_1", "i_a", "i_p1", "inherited_form", dataset="jambu")
    edge(g, "ie_2", "i_b", "i_p2", "inherited_form", dataset="other")
    c = inferred_chain(g, "i_a", "i_b")
    assert c is not None and c.depth == 1
    assert c.datasets == ["jambu", "other"]


def test_dataset_filters(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p", "la-z")
    edge(g, "ie_1", "i_a", "i_p", "inherited_form", dataset="jambu")
    edge(g, "ie_2", "i_b", "i_p", "inherited_form", dataset="other")
    assert inferred_chain(g, "i_a", "i_b") is not None
    assert inferred_chain(g, "i_a", "i_b", exclude_datasets=["other"]) is None
    assert inferred_chain(g, "i_a", "i_b", datasets=["jambu"]) is None
    assert inferred_chain(g, "i_a", "i_b", datasets=["jambu", "other"]) is not None


def test_cognate_hops_are_optional_and_bounded(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_c", "la-z")
    edge(g, "ie_1", "i_a", "i_c", "cognate")
    edge(g, "ie_2", "i_c", "i_b", "cognate")
    assert inferred_chain(g, "i_a", "i_b") is None  # off by default: ancestry only
    c = inferred_chain(g, "i_a", "i_b", cognate_hops=True)
    assert c.kind == "cognate_component" and c.depth == 0
    assert sorted(c.relationship_ids) == ["ie_1", "ie_2"]
    assert inferred_chain(g, "i_a", "i_b", cognate_hops=True, cognate_component_max=2) is None


def test_cognate_hop_then_ancestry(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_c", "la-y")
    lex(g, "i_p", "la-z")
    lex(g, "i_b", "la-z", form="i_b2")
    edge(g, "ie_1", "i_a", "i_c", "cognate")
    edge(g, "ie_2", "i_c", "i_p", "inherited_form")
    edge(g, "ie_3", "i_b", "i_p", "inherited_form")
    c = inferred_chain(g, "i_a", "i_b", cognate_hops=True)
    assert c.relationship_ids == ["ie_1", "ie_2", "ie_3"] and c.depth == 1


def test_same_word_and_unknown_lexeme(g):
    lex(g, "i_a", "la-x", form="same")
    lex(g, "i_a2", "la-x", form="same", dataset="other")
    assert inferred_chain(g, "i_a", "i_a2") is None
    with pytest.raises(ValueError):
        inferred_chain(g, "i_a", "nope")


def test_materialise_only_asked_pairs_and_never_touch_documented(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_c", "la-y", form="i_c")
    lex(g, "i_p", "la-z")
    edge(g, "ie_1", "i_a", "i_p", "inherited_form")
    edge(g, "ie_2", "i_b", "i_p", "inherited_form")
    edge(g, "ie_3", "i_c", "i_p", "inherited_form")
    before = n_relationships(g)
    counts = materialise_inferred(g, [("i_b", "i_a")])
    assert counts == {"pairs": 1, "found": 1, "none": 0, "capped_none": 0}
    # only the asked pair is stored; the other inferable pairs (a-c, b-c) are not
    assert g.execute("SELECT count(*) FROM layers.inferred_pair").fetchone()[0] == 1
    row = stored_inferred(g, "i_a", "i_b")
    assert row["chain_relationship_ids"] == ["ie_1", "ie_2"]
    assert row["kind"] == "common_ancestor" and row["rule_version"] == "ancestry-v1"
    # idempotent
    materialise_inferred(g, [("i_a", "i_b")])
    assert g.execute("SELECT count(*) FROM layers.inferred_pair").fetchone()[0] == 1
    # the evidence view shows each step with the documented citation
    steps = g.execute(
        "SELECT step, relationship_id, citation FROM layers.inferred_chain_step"
        " WHERE a = 'i_a' AND b = 'i_b' ORDER BY step"
    ).fetchall()
    assert [s[1] for s in steps] == ["ie_1", "ie_2"]
    assert steps[0][2].startswith("Citation for ie_1")
    # the documented layer is unchanged
    assert n_relationships(g) == before


def test_materialise_counts_pairs_without_chain(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    counts = materialise_inferred(g, [("i_a", "i_b")])
    assert counts["none"] == 1 and counts["found"] == 0
    assert g.execute("SELECT count(*) FROM layers.inferred_pair").fetchone()[0] == 0


def test_get_inferred_stores_on_first_request(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_p", "la-y")
    edge(g, "ie_1", "i_a", "i_p", "inherited_form")
    assert stored_inferred(g, "i_a", "i_p") is None
    row = get_inferred(g, "i_p", "i_a")
    assert row["chain_relationship_ids"] == ["ie_1"]
    assert stored_inferred(g, "i_a", "i_p") is not None
    assert get_inferred(g, "i_a", "i_p")["kind"] == "b_ancestor_of_a"


def test_rule_versions_are_stored_side_by_side(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p", "la-z")
    edge(g, "ie_1", "i_a", "i_p", "inherited_form")
    edge(g, "ie_2", "i_b", "i_p", "inherited_form")
    row1 = get_inferred(g, "i_a", "i_b")
    row2 = get_inferred(g, "i_a", "i_b", cognate_hops=True)
    assert row1["rule_version"] == "ancestry-v1"
    assert row2["rule_version"] == "ancestry-v1+cognate50"
    assert g.execute("SELECT count(*) FROM layers.inferred_pair").fetchone()[0] == 2


def test_report_says_whether_a_shared_ancestor_lies_above_both_words(g):
    lex(g, "i_a", "la-x")
    lex(g, "i_b", "la-y")
    lex(g, "i_p", "la-z")
    lex(g, "i_q", "la-z")
    edge(g, "ie_1", "i_a", "i_b", "inherited_form")  # b is an ancestor of a ...
    rep: dict = {}
    assert inferred_chain(g, "i_a", "i_b", report=rep).kind == "b_ancestor_of_a"
    assert rep["shared_ancestor"] is False  # ... and nothing lies above both
    edge(g, "ie_2", "i_b", "i_p", "inherited_form")  # now p is above both a and b
    rep = {}
    assert inferred_chain(g, "i_a", "i_b", report=rep).kind == "b_ancestor_of_a"  # shortest wins
    assert rep["shared_ancestor"] is True
