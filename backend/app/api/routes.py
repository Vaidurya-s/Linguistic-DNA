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
def lexeme(conn: Conn, lexeme_id: str):
    found = retrieval.get_lexeme(conn, lexeme_id)
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
def relationship(conn: Conn, relationship_id: str):
    found = retrieval.get_relationship(conn, relationship_id)
    if not found:
        raise HTTPException(404, "Relationship not found")
    return found
