"""Layered retrieval endpoint: three separate blocks, each item with its evidence kind.

The HTTP tests use stubs for the inferred and candidate layers (the functions of
layers/inferred.py and layers/candidate.py) and the fixture database for the documented layer;
the integration tests call the real layers on small synthetic graphs inside a rolled-back
transaction."""

import pytest
from sqlalchemy import create_engine, text

from app.layers import candidate as cand
from app.layers import inferred as inf
from app.services import retrieval
from app.services.ids import lexeme_id

API = "/api/v1"
ROOT = lexeme_id("jambu", "6152")


def test_documented_block_has_citations_and_the_other_blocks_follow(client):
    body = client.get(f"{API}/lexemes/{ROOT}/related", params={"layers": "documented"}).json()
    assert body["layers_requested"] == ["documented"]
    assert body["inferred"] is None and body["candidate"] is None
    doc = body["documented"]
    assert doc["evidence_kind"] == "documented" and doc["count"] == len(doc["items"]) > 0
    for item in doc["items"]:
        assert item["evidence_kind"] == "documented"
        assert item["evidence"] and item["evidence"][0]["citation"]
        assert item["dataset"] == "jambu" and item["role"] in ("source", "target")
        assert item["other"]["id"] != ROOT


def test_open_only_hides_research_use_word_and_links(client):
    assert client.get(f"{API}/lexemes/{ROOT}/related").status_code == 200
    assert (
        client.get(f"{API}/lexemes/{ROOT}/related", params={"open_only": True}).status_code == 404
    )


def test_bad_layer_name_is_422_and_unknown_word_404(client):
    assert (
        client.get(f"{API}/lexemes/{ROOT}/related", params={"layers": "magic"}).status_code == 422
    )
    assert client.get(f"{API}/lexemes/nope/related").status_code == 404


def test_blocks_in_order_with_stubs(client, monkeypatch):
    docs = client.get(f"{API}/lexemes/{ROOT}/related", params={"layers": "documented"}).json()
    partner = docs["documented"]["items"][0]["other"]["id"]  # any existing word as the partner
    chain = inf.InferredChain(
        lexeme_a=ROOT, lexeme_b=partner, kind="common_ancestor", depth=2, depth_a=1, depth_b=1,
        ancestor_id=partner, relationship_ids=["rel_x"], types=["etymon"], datasets=["jambu"],
        capped=False,
    )  # fmt: skip
    monkeypatch.setattr(
        retrieval,
        "_inferred_items",
        lambda pg, lid, ds, limit: [{"chain": chain, "other": partner}],
    )
    monkeypatch.setattr(retrieval, "_candidate_items", lambda pg, lid, ds, limit, gate="gloss": [
        cand.Candidate(lexeme_id=partner, language_id="x", form="f", gloss=None, score=0.8,
                       method="blend", gate=gate, gate_via="gloss", calibrated_precision=0.42,
                       calibrated=True, stratum="same_branch")])  # fmt: skip
    r = client.get(f"{API}/lexemes/{ROOT}/related")
    assert r.status_code == 200
    body = r.json()
    assert list(body)[:5] == [
        "lexeme_id",
        "open_only",
        "layers_requested",
        "documented",
        "inferred",
    ]
    assert body["layers_requested"] == ["documented", "inferred", "candidate"]
    (inferred,) = body["inferred"]["items"]
    assert inferred["evidence_kind"] == "inferred" and inferred["chain_relationship_ids"] == [
        "rel_x"
    ]
    assert inferred["other"]["id"] == partner and inferred["kind"] == "common_ancestor"
    (c,) = body["candidate"]["items"]
    assert c["evidence_kind"] == "computed" and c["method"] == "blend"
    assert c["score"] == pytest.approx(0.8) and c["calibrated_precision"] == pytest.approx(0.42)
    assert body["candidate"]["evidence_kind"] == "computed"


def test_a_failing_layer_is_reported_and_the_others_still_answer(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("layer tables are not built")

    monkeypatch.setattr(retrieval, "_inferred_items", boom)
    monkeypatch.setattr(retrieval, "_candidate_items", boom)
    body = client.get(f"{API}/lexemes/{ROOT}/related").json()
    assert body["documented"]["count"] > 0
    assert (
        body["inferred"]["status"] == "unavailable" and body["candidate"]["status"] == "unavailable"
    )
    assert body["inferred"]["items"] == [] and len(body["warnings"]) == 2


# --- real layers on synthetic data, rolled back --------------------------------------------------


@pytest.fixture
def conn(lsi_imported):
    engine = create_engine(lsi_imported)
    with engine.connect() as c:
        pg = c.connection.driver_connection
        inf.ensure_schema(pg)
        cand.ensure_schema(pg)
        for lid in ("zz-a", "zz-b", "zz-c"):
            c.execute(
                text(
                    "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
                    " VALUES (:i, :n, 'modern', false, true, '{}')"
                ),
                {"i": lid, "n": lid},
            )
        yield c
        c.rollback()
    engine.dispose()


def _lex(c, lid, language, form, dataset="lsi", gloss=None):
    c.execute(
        text(
            "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key,"
            " reconstruction_status, dataset, source_id, source_record_id, gloss)"
            " VALUES (:i, :l, :f, :n, :k, 'attested', :d, :s, :r, :g)"
        ),
        {
            "i": lid,
            "l": language,
            "f": form,
            "n": form,
            "k": form,
            "d": dataset,
            "s": dataset,
            "r": lid,
            "g": gloss,
        },
    )


def _edge(c, rid, src, tgt, type_id, dataset="lsi"):
    c.execute(
        text(
            "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,"
            " status, source_id, dataset)"
            " VALUES (:r, :s, :t, :ty, 'directed', 'documented', :sid, :d)"
        ),
        {"r": rid, "s": src, "t": tgt, "ty": type_id, "sid": dataset, "d": dataset},
    )
    c.execute(
        text(
            "INSERT INTO evidence (relationship_id, source_id, citation, locator)"
            " VALUES (:r, :sid, :c, 'p. 1')"
        ),
        {"r": rid, "sid": dataset, "c": f"citation of {rid}"},
    )


def test_real_inferred_siblings_through_a_documented_ancestor(conn):
    _lex(conn, "b2_a", "zz-a", "alpha")
    _lex(conn, "b2_b", "zz-b", "beta")
    _lex(conn, "b2_p", "zz-c", "proto")
    _edge(conn, "b2_e1", "b2_a", "b2_p", "inherited_form")
    _edge(conn, "b2_e2", "b2_b", "b2_p", "inherited_form")
    out = retrieval.related_layers(conn, "b2_a", ["documented", "inferred"])
    assert [i["relationship_id"] for i in out["documented"]["items"]] == ["b2_e1"]
    assert out["documented"]["items"][0]["evidence"][0]["citation"] == "citation of b2_e1"
    (item,) = out["inferred"]["items"]
    assert item["other"]["id"] == "b2_b" and item["kind"] == "common_ancestor"
    assert item["chain_relationship_ids"] == ["b2_e1", "b2_e2"]
    assert [s["citation"] for s in item["chain"]] == ["citation of b2_e1", "citation of b2_e2"]
    assert out["inferred"]["status"] == "ok" and out["candidate"] is None


def test_real_candidates_are_computed_and_never_documented(conn):
    _lex(conn, "b2_q", "zz-a", "pater", gloss="father")
    _lex(conn, "b2_r", "zz-b", "father", gloss="father")
    cand.build_gloss_tokens(conn.connection.driver_connection)  # the gloss gate's index
    out = retrieval.related_layers(conn, "b2_q", ["documented", "candidate"])
    assert out["documented"]["items"] == []
    (c,) = out["candidate"]["items"]
    assert c["other"]["id"] == "b2_r" and c["gate"] == "gloss"
    assert 0 < c["score"] <= 1
    assert (
        conn.execute(text("SELECT count(*) FROM relationship WHERE id LIKE 'b2_%'")).scalar() == 0
    )


def test_open_only_drops_research_use_chain_and_candidates(conn):
    _lex(conn, "b2_oa", "zz-a", "alpha")
    _lex(conn, "b2_ob", "zz-b", "beta")
    _lex(conn, "b2_op", "zz-c", "proto")
    _edge(conn, "b2_oe1", "b2_oa", "b2_op", "inherited_form")
    _edge(conn, "b2_oe2", "b2_ob", "b2_op", "inherited_form", dataset="jambu")  # research use
    shown = retrieval.related_layers(conn, "b2_oa", ["inferred"], open_only=False)
    assert len(shown["inferred"]["items"]) == 1
    hidden = retrieval.related_layers(conn, "b2_oa", ["inferred"], open_only=True)
    assert hidden["inferred"]["items"] == []
