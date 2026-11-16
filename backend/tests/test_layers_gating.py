"""open_only gating on the lookups by id and on the graph. Synthetic fixtures."""

import pytest
from sqlalchemy import text

API = "/api/v1"


@pytest.fixture(scope="module")
def ids(client, lsi_imported):
    """(research-use word, research-use link, open word, open link) from the fixtures."""
    from sqlalchemy import create_engine

    engine = create_engine(lsi_imported)
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT r.id, r.source_lexeme_id, r.dataset FROM relationship r"
                " JOIN dataset_audit d ON d.id = r.dataset ORDER BY r.id"
            )
        ).all()
        decisions = dict(c.execute(text("SELECT id, decision::text FROM dataset_audit")).all())
        lex = c.execute(
            text("SELECT id, dataset FROM lexeme WHERE dataset IN ('jambu', 'lsi') ORDER BY id")
        ).all()
    engine.dispose()
    research_rel = next(r for r in rows if decisions[r[2]] == "RESEARCH USE")
    research_word = research_rel[1]
    open_word = next(i for i, d in lex if decisions[d] != "RESEARCH USE")
    open_rel = next((r for r in rows if decisions[r[2]] != "RESEARCH USE"), None)
    return research_word, research_rel[0], open_word, open_rel[0] if open_rel else None


def test_lexeme_by_id_default_unchanged_and_open_only_hides_research_use(client, ids):
    research_word, _, open_word, _ = ids
    assert client.get(f"{API}/lexemes/{research_word}").status_code == 200
    assert (
        client.get(f"{API}/lexemes/{research_word}", params={"open_only": False}).status_code == 200
    )
    assert (
        client.get(f"{API}/lexemes/{research_word}", params={"open_only": True}).status_code == 404
    )
    assert client.get(f"{API}/lexemes/{open_word}", params={"open_only": True}).status_code == 200


def test_relationship_by_id_open_only(client, ids):
    _, research_rel, _, open_rel = ids
    assert client.get(f"{API}/relationships/{research_rel}").status_code == 200
    r = client.get(f"{API}/relationships/{research_rel}", params={"open_only": True})
    assert r.status_code == 404
    if open_rel:
        assert (
            client.get(f"{API}/relationships/{open_rel}", params={"open_only": True}).status_code
            == 200
        )


def test_graph_rooted_at_research_word_is_empty_with_message(client, ids):
    research_word, *_ = ids
    full = client.get(f"{API}/graph/{research_word}").json()
    assert full["nodes"] and not full["restricted"]
    body = client.get(f"{API}/graph/{research_word}", params={"open_only": True}).json()
    assert body["nodes"] == [] and body["edges"] == []
    assert body["restricted"] is True and "research use" in body["message"]
    assert body["root_lexeme_id"] == research_word


def test_graph_open_only_from_open_root_has_no_restricted_node(client, ids):
    _, _, open_word, _ = ids
    body = client.get(f"{API}/graph/{open_word}", params={"open_only": True}).json()
    assert body["restricted"] is False
    assert any(n["id"] == open_word for n in body["nodes"])


def test_unknown_ids_stay_404(client):
    assert client.get(f"{API}/lexemes/nope", params={"open_only": True}).status_code == 404
    assert client.get(f"{API}/relationships/nope", params={"open_only": True}).status_code == 404
    assert client.get(f"{API}/graph/nope", params={"open_only": True}).status_code == 404


def test_unaudited_dataset_is_treated_as_restricted(client, lsi_imported):
    """Fail closed: a dataset missing from the audit is not open."""
    from sqlalchemy import create_engine

    from app.services import retrieval

    engine = create_engine(lsi_imported)
    with engine.connect() as c:
        ds = retrieval.open_datasets(c, True)
    engine.dispose()
    assert "jambu" not in ds and "lsi" in ds and "no-such-dataset" not in ds
