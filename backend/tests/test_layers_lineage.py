"""Source lineage: the seed only states what a document states; groups collapse by lineage."""

import psycopg
import pytest

from app.cli import init_layers
from app.layers import lineage
from app.layers.lineage import SEED, group_map, load_edges, seed


def edges(rows=SEED):
    return [(r.dataset, r.derived_from, r.kind, r.verified) for r in rows]


def test_every_seed_row_names_its_document_and_unknown_rows_are_unverified():
    for r in SEED:
        assert r.evidence_note.strip()
        assert r.kind in ("derived", "contains", "shared_origin", "unknown")
        if r.kind == "unknown":
            assert not r.verified
        else:
            assert r.verified
    unknown = {(r.dataset, r.derived_from) for r in SEED if r.kind == "unknown"}
    assert ("wikidata-lexemes", "wiktionary") in unknown  # partly derived; no dataset-level proof
    note = next(r.evidence_note for r in SEED if r.dataset == "wikidata-lexemes")
    assert "0.67%" in note and "cannot be determined" in note  # what the reference counts show


def test_documented_derivations_are_present():
    pairs = {(r.dataset, r.derived_from, r.kind) for r in SEED if r.verified}
    assert ("etymwn", "wiktionary", "derived") in pairs
    assert ("cognet", "etymwn", "derived") in pairs
    assert ("etymdb", "wiktionary", "derived") in pairs
    assert ("jambu", "lsi", "contains") in pairs and ("jambu", "dravlex", "contains") in pairs


def test_groups_by_kind_and_verification():
    strict = group_map(edges())
    assert strict["etymwn"] == strict["wiktionary"] == strict["cognet"]
    assert strict["jambu"] == strict["lsi"] == strict["dravlex"]
    assert "wikidata-lexemes" not in strict  # unverified rows never count by default
    assert "starostinkaren" not in strict  # shared origin is not a derivation
    broad = group_map(edges(), kinds=lineage.BROAD_KINDS)
    assert broad["starostinkaren"] == broad["starling"] == broad["starostinpie"]
    hypo = group_map(edges(), kinds=lineage.HYPOTHETICAL_KINDS, include_unverified=True)
    assert hypo["wikidata-lexemes"] == hypo["wiktionary"]


def test_group_labels_are_deterministic():
    a = group_map([("b", "a", "derived", True), ("c", "b", "derived", True)])
    b = group_map([("c", "b", "derived", True), ("b", "a", "derived", True)])
    assert a == b and set(a.values()) == {"a"}


@pytest.fixture
def conn(imported_db):
    c = psycopg.connect(imported_db.replace("postgresql+psycopg", "postgresql"))
    yield c
    c.rollback()
    c.close()


def test_seed_is_idempotent_and_unknown_cannot_be_verified(conn):
    init_layers(conn)
    n = seed(conn)
    assert seed(conn) == n
    assert conn.execute("select count(*) from layers.source_lineage").fetchone()[0] == n
    assert len(load_edges(conn)) == n
    # a savepoint, not a rollback: a rollback would also undo the uncommitted layer tables
    conn.execute("savepoint bad")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "insert into layers.source_lineage values ('x', 'y', 'unknown', 'n', true, now())"
        )
    conn.execute("rollback to savepoint bad")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "insert into layers.source_lineage (dataset, derived_from, kind, evidence_note)"
            " values ('x', 'y', 'guessed', 'n')"
        )


def test_load_edges_without_the_table_is_empty(conn):
    conn.execute("drop table if exists layers.source_lineage")
    assert load_edges(conn) == []
