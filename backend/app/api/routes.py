from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection

from app.db.deps import get_conn
from app.schemas.api import (
    CitationsResponse,
    GraphResponse,
    LanguageOut,
    LanguageProfile,
    LexemeDetail,
    RelationshipDetail,
    SearchResponse,
)
from app.schemas.layers import LayeredRelated, TechniqueSearchResponse
from app.services import retrieval

router = APIRouter()
Conn = Annotated[Connection, Depends(get_conn)]
MAX_QUERY = 64


@router.get("/languages", response_model=list[LanguageOut])
def languages(conn: Conn):
    return retrieval.list_languages(conn)


@router.get("/languages/{language_id}/profile", response_model=LanguageProfile)
def language_profile(conn: Conn, language_id: str):
    """Typological and phonological facts (WALS, PHOIBLE) about one language, cited."""
    found = retrieval.get_language_profile(conn, language_id)
    if not found:
        raise HTTPException(404, "Language not found")
    return found


@router.get("/search", response_model=SearchResponse)
def search(
    conn: Conn,
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY)],
    language_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    open_only: bool = False,
):
    if not q.strip():
        raise HTTPException(422, "Query is empty")
    return retrieval.search(conn, q, language_id, limit, open_only)


@router.get("/lexemes/{lexeme_id}", response_model=LexemeDetail)
def lexeme(conn: Conn, lexeme_id: str, open_only: bool = False):
    """open_only=true answers 404 for a word of a research-use or blocked dataset."""
    found = retrieval.get_lexeme(conn, lexeme_id, open_only)
    if not found:
        raise HTTPException(404, "Lexeme not found")
    return found


@router.get("/graph/{lexeme_id}", response_model=GraphResponse)
def graph(
    conn: Conn,
    lexeme_id: str,
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    relationship_types: Annotated[list[str] | None, Query()] = None,
    language_ids: Annotated[list[str] | None, Query()] = None,
    limit_nodes: Annotated[int, Query(ge=1, le=150)] = 50,
    open_only: bool = False,
):
    found = retrieval.build_graph(
        conn, lexeme_id, depth, relationship_types, language_ids, limit_nodes, open_only
    )
    if not found:
        raise HTTPException(404, "Lexeme not found")
    return found


@router.get("/citations", response_model=CitationsResponse)
def citations(conn: Conn):
    """Datasets in use and the works their records cite, for 'how to cite' pages."""
    return retrieval.list_citations(conn)


@router.get("/relationships/{relationship_id}", response_model=RelationshipDetail)
def relationship(conn: Conn, relationship_id: str, open_only: bool = False):
    """open_only=true answers 404 for a link of a research-use or blocked dataset."""
    found = retrieval.get_relationship(conn, relationship_id, open_only)
    if not found:
        raise HTTPException(404, "Relationship not found")
    return found


# --- layered retrieval and extra search techniques ---------------------------


@router.get("/lexemes/{lexeme_id}/related", response_model=LayeredRelated)
def related(
    conn: Conn,
    lexeme_id: str,
    layers: str = "documented,inferred,candidate",
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    candidate_gate: Annotated[str, Query(pattern="^(gloss|concept)$")] = "gloss",
):
    """Relatives of a word in three separate blocks: documented (cited relationships), inferred
    (chains of documented ancestry, with the ids of the links they rest on) and candidate
    (computed similarity, with method, score and calibrated precision). Every item states its
    evidence kind. open_only=true keeps research-use data out of all three blocks."""
    wanted = [x.strip() for x in layers.split(",") if x.strip()]
    unknown = [x for x in wanted if x not in retrieval.LAYERS]
    if unknown or not wanted:
        raise HTTPException(422, f"layers must be a comma list of {', '.join(retrieval.LAYERS)}")
    found = retrieval.related_layers(conn, lexeme_id, wanted, open_only, limit, candidate_gate)
    if not found:
        raise HTTPException(404, "Lexeme not found")
    return found


@router.get("/search/fuzzy", response_model=TechniqueSearchResponse)
def search_fuzzy(
    conn: Conn,
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY)],
    language_id: str,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    threshold: Annotated[float, Query(ge=0.2, le=0.95)] = 0.4,
    open_only: bool = False,
):
    """Trigram-similar spellings inside one language."""
    return retrieval.fuzzy_search(conn, q, language_id, limit, threshold, open_only)


@router.get("/search/concept", response_model=TechniqueSearchResponse)
def search_concept(
    conn: Conn,
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY)],
    concept_id: Annotated[list[str] | None, Query()] = None,
    from_lexeme_id: str | None = None,
    language_ids: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    open_only: bool = False,
):
    """Words that share a concept with the query, ranked by spelling similarity. Give
    concept_id (repeatable) or from_lexeme_id (the concepts of that word)."""
    cids = list(concept_id or [])
    if from_lexeme_id:
        found = retrieval.get_lexeme(conn, from_lexeme_id, open_only)
        if not found:
            raise HTTPException(404, "Lexeme not found")
        cids += [c["id"] for c in found["concepts"]]
    if not cids:
        raise HTTPException(422, "Give concept_id or a from_lexeme_id that has concepts")
    return retrieval.concept_gated_search(conn, q, cids, language_ids, limit, open_only)


@router.get("/search/keys", response_model=TechniqueSearchResponse)
def search_keys(
    conn: Conn,
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY)],
    language_id: str,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    open_only: bool = False,
):
    """Same word in another script or spelling, found by rule through the word keys."""
    return retrieval.key_search(conn, q, language_id, limit, open_only)


@router.get("/search/sound", response_model=TechniqueSearchResponse)
def search_sound(
    conn: Conn,
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY)],
    level: Annotated[str, Query(pattern="^(exact|cons|prefix)$")] = "cons",
    language_ids: Annotated[list[str] | None, Query()] = None,
    exclude_language: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    open_only: bool = False,
):
    """Words with the same sound-class skeleton (computed blocking key), ranked by alignment."""
    return retrieval.sound_search(conn, q, level, language_ids, exclude_language, limit, open_only)
