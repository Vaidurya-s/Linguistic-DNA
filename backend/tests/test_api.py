from fastapi.testclient import TestClient

from app.main import app
from app.services.ids import lexeme_id


def test_health():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_exact_loose_and_candidates(client):
    body = client.get("/api/v1/search", params={"q": "dānt"}).json()
    assert [(m["language_id"], m["match_type"]) for m in body["matches"]] == [("pan", "exact")]
    loose = client.get("/api/v1/search", params={"q": "dant"}).json()
    assert {m["form"] for m in loose["matches"]} >= {"dānt"}
    assert all(m["match_type"] == "loose" for m in loose["matches"] if m["form"] == "dānt")
    assert all(c["match_type"] == "spelling_candidate" for c in loose["spelling_candidates"])


def test_search_groups_identical_records(client):
    body = client.get("/api/v1/search", params={"q": "ajī"}).json()
    assert len(body["matches"]) == 1 and body["matches"][0]["duplicate_count"] == 2


def test_search_unknown_and_native_script_warnings(client):
    body = client.get("/api/v1/search", params={"q": "zzzq"}).json()
    assert body["matches"] == [] and body["warnings"]
    deva = client.get("/api/v1/search", params={"q": "पानी"}).json()
    assert deva["detected_script"] == "Devanagari" and any(
        "romanised" in w for w in deva["warnings"]
    )


def test_search_rejects_bad_input(client):
    assert client.get("/api/v1/search", params={"q": ""}).status_code == 422
    assert client.get("/api/v1/search", params={"q": "x" * 65}).status_code == 422
    assert client.get("/api/v1/search", params={"q": "a", "limit": 500}).status_code == 422


def test_graph_depth_and_limits(client):
    root = lexeme_id("jambu", "6152")  # dánta
    g = client.get(f"/api/v1/graph/{root}").json()
    langs = {n["language_id"] for n in g["nodes"]}
    assert {"hin", "ben", "mar", "pan"} <= langs
    assert all(e["status"] == "documented" and e["citation"] for e in g["edges"])
    small = client.get(f"/api/v1/graph/{root}", params={"limit_nodes": 3}).json()
    assert small["truncated"] and len(small["nodes"]) == 3
    only = client.get(
        f"/api/v1/graph/{root}", params={"relationship_types": "borrowed_from"}
    ).json()
    assert only["edges"] == []
    assert client.get(f"/api/v1/graph/{root}", params={"depth": 5}).status_code == 422
    assert client.get("/api/v1/graph/lx_missing").status_code == 404


def test_relationship_evidence_and_licence(client):
    root = lexeme_id("jambu", "f_27fxniq4x3i6i")  # Kannada sottu
    edge = client.get(f"/api/v1/graph/{root}").json()["edges"][0]
    rel = client.get(f"/api/v1/relationships/{edge['id']}").json()
    assert rel["type"] == "borrowed_from" and rel["direction"] == "directed"
    assert rel["source_lexeme"]["form"] == "sottu" and rel["target_lexeme"]["form"] == "svatva-"
    assert rel["evidence"] and rel["evidence"][0]["source"]["reuse_status"] == "permission_required"


def test_lexeme_detail_and_languages(client):
    lx = client.get(f"/api/v1/lexemes/{lexeme_id('jambu', 'd1041')}").json()
    assert lx["form"] == "*ōṭu" and lx["reconstruction_status"] == "reconstructed"
    langs = client.get("/api/v1/languages").json()
    assert langs[0]["role"] == "modern"
    assert {"hin", "tam"} <= {lang["id"] for lang in langs}


def test_stems_are_not_word_matches(client):
    body = client.get("/api/v1/search", params={"q": "svatva"}).json()
    assert body["matches"] == []
    assert [(m["form"], m["form_kind"]) for m in body["related_forms"]] == [("svatva-", "stem")]
    assert all(c["form_kind"] == "word" for c in body["spelling_candidates"])


def test_research_records_carry_their_citation(client):
    body = client.get("/api/v1/search", params={"q": "dānt"}).json()
    detail = client.get(f"/api/v1/lexemes/{body['matches'][0]['id']}").json()
    source = detail["source"]
    assert source["dataset_decision"] == "RESEARCH USE"
    # the database the record came from is Jambu, whatever work it cites (e.g. CDIAL)
    assert source["dataset_id"] == "jambu" and "Arora" in source["dataset_citation"]


def test_open_only_hides_research_use_data(client):
    assert client.get("/api/v1/search", params={"q": "dānt"}).json()["matches"]
    body = client.get("/api/v1/search", params={"q": "dānt", "open_only": True}).json()
    assert body["matches"] == []
    root = lexeme_id("jambu", "6152")
    assert client.get(f"/api/v1/graph/{root}").json()["edges"]
    assert client.get(f"/api/v1/graph/{root}", params={"open_only": True}).json()["edges"] == []


def test_citations_list_datasets_and_cited_works(client):
    body = client.get("/api/v1/citations").json()
    jambu = next(d for d in body["datasets"] if d["id"] == "jambu")
    assert jambu["decision"] == "RESEARCH USE" and "Arora" in jambu["citation"]
    assert jambu["lexeme_count"] > 0
    assert any("Indo-Aryan" in w["title"] for w in body["works"])  # Turner's CDIAL
