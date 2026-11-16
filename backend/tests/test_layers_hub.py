"""Cognate components and hub gating (layers.hub), on synthetic data."""

import pytest

from app.layers import hub

DS = "hubtest"


def test_components_pure_union_find_and_hub_removal():
    # 0-1-2 chain, plus a star around word 3 (3-4, 3-5, 3-6, 3-7) that also touches word 2
    a = [0, 1, 3, 3, 3, 3, 2]
    b = [1, 2, 4, 5, 6, 7, 3]
    plain = hub.components(8, a, b)
    assert set(plain["raw_size"]) == {8}
    assert plain["is_hub"] == [False] * 8
    assert plain["size"] == plain["raw_size"]
    gated = hub.components(8, a, b, hub_degree=3)
    assert gated["is_hub"][3] and gated["degree"][3] == 5
    assert gated["raw_size"][0] == 8  # raw components do not change
    assert gated["size"][0] == 3  # the chain 0-1-2 once the hub is removed
    assert gated["size"][3] == 1
    assert hub.edge_reasons(a, b, gated, cutoff=50) == [
        None,
        None,
        "hub_lexeme",
        "hub_lexeme",
        "hub_lexeme",
        "hub_lexeme",
        "hub_lexeme",
    ]


def test_degree_counts_distinct_neighbours_only():
    assert hub.cognate_degrees(3, [0, 0, 1], [1, 1, 2]) == [1, 2, 1]


def test_component_id_is_stable():
    assert hub.component_id("gl-x|a") == hub.component_id("gl-x|a")
    assert hub.component_id("gl-x|a") != hub.component_id("gl-x|b")


@pytest.fixture
def graph(db):
    """Languages hbt-a/b/c; a small cognate group (3 words) chained to a big one by a homograph.

    g1: a1 - b1 - c1. Big group: a hub word cognate with 6 words and with a twin of b1 (same word
    key as b1, other dataset record), so the two groups chain through a homograph.
    """
    for lid in ("hbt-a", "hbt-b", "hbt-c"):
        db.execute(
            "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
            " VALUES (%s, %s, 'modern', false, true, '{}') ON CONFLICT DO NOTHING",
            (lid, lid),
        )

    def lex(lid, lang, form, rec=None):
        db.execute(
            "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key,"
            " reconstruction_status, dataset, source_id, source_record_id)"
            " VALUES (%s, %s, %s, %s, %s, 'attested', %s, 'jambu', %s)",
            (lid, lang, form, form, form, DS, rec or lid),
        )

    def edge(rid, s, t):
        db.execute(
            "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,"
            " status, source_id, dataset) VALUES (%s, %s, %s, 'cognate', 'undirected',"
            " 'documented', 'jambu', %s)",
            (rid, s, t, DS),
        )

    lex("hx_a1", "hbt-a", "g1a")
    lex("hx_b1", "hbt-b", "g1b")
    lex("hx_c1", "hbt-c", "g1c")
    edge("hx_e1", "hx_a1", "hx_b1")
    edge("hx_e2", "hx_b1", "hx_c1")
    lex("hx_hub", "hbt-a", "hubword")
    for i in range(6):
        lex(f"hx_m{i}", "hbt-b", f"m{i}")
        edge(f"hx_h{i}", "hx_hub", f"hx_m{i}")
    lex("hx_b1twin", "hbt-b", "g1b", rec="twin")  # a homograph of hx_b1: same word key
    edge("hx_t1", "hx_hub", "hx_b1twin")
    lex("hx_far", "hbt-c", "far")  # a separate pair
    lex("hx_far2", "hbt-a", "far2")
    edge("hx_f1", "hx_far", "hx_far2")
    lex("hx_lonely", "hbt-c", "lonely")  # no cognate link
    db.commit()
    yield db
    db.execute("DELETE FROM lexeme WHERE dataset = %s", (DS,))  # cascades to relationships
    db.execute("DELETE FROM language WHERE id LIKE 'hbt-%'")
    db.commit()


def relationships(db) -> list:
    return db.execute(
        "SELECT id, source_lexeme_id, target_lexeme_id, type_id, status, dataset FROM relationship"
        " WHERE dataset = %s ORDER BY id",
        (DS,),
    ).fetchall()


def test_build_flags_oversized_component_and_deletes_nothing(graph):
    before = relationships(graph)
    out = hub.build(graph, cutoff=5, datasets=[DS])
    assert out["edges"] == 10 and out["flagged_edges"] == 9  # the 9-edge big group is oversized
    assert relationships(graph) == before  # the documented layer is untouched
    flagged = dict(
        graph.execute("SELECT relationship_id, reason FROM layers.edge_hub_flag").fetchall()
    )
    assert set(flagged.values()) == {"oversized_component"}
    assert "hx_f1" not in flagged
    # the homograph chains g1 into the big group: hx_b1 and its twin share one component
    rows = dict(
        (r[0], r)
        for r in graph.execute(
            "SELECT lexeme_id, component_id, component_size FROM layers.cognate_component"
        ).fetchall()
    )
    assert rows["hx_b1"][1] == rows["hx_b1twin"][1] == rows["hx_a1"][1] == rows["hx_hub"][1]
    assert rows["hx_a1"][2] == 10  # g1 (3 words) + hub + 6 words
    assert "hx_lonely" not in rows
    assert rows["hx_far"][2] == 2


def test_gated_helper_blocks_the_big_component_only(graph):
    hub.build(graph, cutoff=5, datasets=[DS])
    assert hub.is_connected_documented(graph, "hx_far", "hx_far2")
    assert hub.is_connected_documented(graph, "hx_a1", "hx_c1", gated=False)
    assert not hub.is_connected_documented(
        graph, "hx_a1", "hx_c1"
    )  # inside the oversized component
    assert hub.is_connected_documented(graph, "hx_m0", "hx_m1", gated=False)
    assert not hub.is_connected_documented(graph, "hx_m0", "hx_m1")
    assert not hub.is_connected_documented(graph, "hx_far", "hx_far")
    assert not hub.is_connected_documented(graph, "hx_far", "hx_lonely", gated=False)
    # a large cutoff lets everything through
    hub.build(graph, cutoff=1000, datasets=[DS])
    assert hub.is_connected_documented(graph, "hx_a1", "hx_c1")
    assert graph.execute("SELECT count(*) FROM layers.edge_hub_flag").fetchone()[0] == 0


def test_degree_rule_cuts_the_hub_and_keeps_the_small_group(graph):
    out = hub.build(graph, cutoff=5, hub_degree=3, datasets=[DS])
    assert out["flagged_edges"] == 7  # the hub's seven edges
    reasons = {r[0] for r in graph.execute("SELECT reason FROM layers.edge_hub_flag").fetchall()}
    assert reasons == {"hub_lexeme"}
    assert graph.execute(
        "SELECT is_hub FROM layers.cognate_component WHERE lexeme_id = 'hx_hub'"
    ).fetchone()[0]
    # g1 reached the big group only through the hub, so without it g1 is a group of 3
    assert hub.is_connected_documented(graph, "hx_a1", "hx_c1")
    assert not hub.is_connected_documented(
        graph, "hx_hub", "hx_m0"
    )  # a hub is connected to nothing, gated
    assert hub.is_connected_documented(graph, "hx_hub", "hx_m0", gated=False)


def test_build_is_idempotent_and_replaces_the_previous_build(graph):
    first = hub.build(graph, cutoff=5, datasets=[DS])
    snap = graph.execute(
        "SELECT lexeme_id, component_id, component_size FROM layers.cognate_component ORDER BY 1"
    ).fetchall()
    second = hub.build(graph, cutoff=5, datasets=[DS])
    assert first == second
    assert (
        snap
        == graph.execute(
            "SELECT lexeme_id, component_id, component_size"
            " FROM layers.cognate_component ORDER BY 1"
        ).fetchall()
    )
    hub.build(graph, cutoff=5, datasets=[DS], exclude_datasets=[DS])
    assert graph.execute("SELECT count(*) FROM layers.cognate_component").fetchone()[0] == 0
    assert hub.build_params(graph)["exclude_datasets"] == DS


def test_stats_reports_sizes_and_flagged_edges_per_dataset(graph):
    hub.build(graph, cutoff=5, datasets=[DS])
    s = hub.stats(graph)
    assert s["built"] and s["params"]["cutoff"] == 5
    assert s["flagged_edges_by_dataset"] == [
        {"dataset": DS, "flagged": 9, "hub_lexeme": 0, "oversized_component": 9}
    ]
    assert s["largest_components"][0][1] == 10


def test_default_cutoff_is_5000_and_small_components_are_not_flagged(graph):
    assert hub.DEFAULT_CUTOFF == 5000
    out = hub.build(graph, datasets=[DS])  # the default: the 10-word group is far below it
    assert out["flagged_edges"] == 0
    assert hub.build_params(graph)["cutoff"] == 5000


@pytest.fixture
def ancestry(db):
    """Cognate pairs x1-x2 and y1-y2; x1 and y1 inherit from p and q, which are cognate.

    p also heads a group of 6 more cognates, so the group has 8 words and the cutoff matters.
    """
    db.execute(
        "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
        " VALUES ('hbt-a', 'hbt-a', 'modern', false, true, '{}') ON CONFLICT DO NOTHING"
    )

    def lex(lid):
        db.execute(
            "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key,"
            " reconstruction_status, dataset, source_id, source_record_id)"
            " VALUES (%s, 'hbt-a', %s, %s, %s, 'attested', %s, 'jambu', %s)",
            (lid, lid, lid, lid, DS, lid),
        )

    def edge(rid, s, t, type_id="cognate"):
        db.execute(
            "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,"
            " status, source_id, dataset) VALUES (%s, %s, %s, %s, 'undirected',"
            " 'documented', 'jambu', %s)",
            (rid, s, t, type_id, DS),
        )

    for name in ("x1", "x2", "y1", "y2", "p", "q", "z1", "z2", "z3", "z4", "z5", "z6"):
        lex("an_" + name)
    edge("an_e1", "an_x1", "an_x2")
    edge("an_e2", "an_y1", "an_y2")
    edge("an_e3", "an_p", "an_q")
    edge("an_i1", "an_x1", "an_p", "inherited_form")
    edge("an_i2", "an_y1", "an_q", "inherited_form")
    # a big group around p that would join everything if contracted
    for n in range(1, 7):
        edge(f"an_g{n}", "an_p", f"an_z{n}")
    db.commit()
    yield db
    db.execute("DELETE FROM lexeme WHERE dataset = %s", (DS,))
    db.execute("DELETE FROM language WHERE id LIKE 'hbt-%'")
    db.commit()


def test_ancestry_rule_follows_ancestors_through_contracted_small_components(ancestry):
    hub.build(ancestry, cutoff=50, datasets=[DS])
    # the cognate leg alone does not connect x1 and y1; contracting {p, q, z1..z6} does
    assert not hub.is_connected_documented(ancestry, "an_x1", "an_y1")
    assert hub.is_connected_documented(ancestry, "an_x1", "an_y1", ancestry=True)
    # x2 shares x1's contracted component, so it climbs to the same ancestors
    assert hub.is_connected_documented(ancestry, "an_x2", "an_y2", ancestry=True)
    # with a cutoff below the group size the group is not contracted: p and q stay separate words
    hub.build(ancestry, cutoff=5, datasets=[DS])
    assert not hub.is_connected_documented(ancestry, "an_x1", "an_y1", ancestry=True)
    # ungated, everything contracts again
    assert hub.is_connected_documented(ancestry, "an_x1", "an_y1", gated=False, ancestry=True)
    assert not hub.is_connected_documented(ancestry, "an_x1", "an_x1", ancestry=True)
