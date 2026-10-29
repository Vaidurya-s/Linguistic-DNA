"""Response models for the public API (docs/TECHNICAL_ARCHITECTURE.md §7)."""

from pydantic import BaseModel


class LanguageOut(BaseModel):
    id: str
    name: str
    role: str
    group: str | None
    family_id: str | None
    family_name: str | None
    glottocode: str | None
    primary_script: str | None
    lexeme_count: int
    linked_count: int


class LexemeSummary(BaseModel):
    id: str
    form: str
    native_form: str | None
    language_id: str
    language_name: str
    group: str | None
    gloss: str | None
    reconstruction_status: str
    is_proto: bool
    form_kind: str


class SearchMatch(LexemeSummary):
    # exact | native_exact | loose | spelling_candidate | compound_of_match
    match_type: str  # ... | transliteration
    via: str | None = None  # how a transliteration match was found
    score: float | None = None
    relationship_count: int
    duplicate_count: int


class SearchResponse(BaseModel):
    query: str
    normalized_query: str
    detected_script: str
    language_hints: list[str]
    matches: list[SearchMatch]  # whole words only
    related_forms: list[SearchMatch]  # stems, affixes, roots, phrases, compounds
    compounds: list[SearchMatch]  # documented compounds containing a matched word
    spelling_candidates: list[SearchMatch]
    warnings: list[str]


class SourceOut(BaseModel):
    id: str
    title: str
    reuse_status: str
    licence_name: str | None
    url: str | None


class ConceptOut(BaseModel):
    id: str
    label: str


class LexemeDetail(LexemeSummary):
    transliteration: str | None
    phonemic: str | None
    source_status: str | None
    source_record_id: str
    source_citation: str | None
    source: SourceOut | None
    concepts: list[ConceptOut]


class GraphNode(LexemeSummary):
    degree: int


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    label: str
    namespace: str
    status: str
    direction: str
    source_id: str | None
    citation: str | None


class GraphResponse(BaseModel):
    root_lexeme_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool
    warnings: list[str]


class EvidenceOut(BaseModel):
    citation: str
    locator: str | None
    note: str | None
    source: SourceOut


class RelationshipDetail(GraphEdge):
    description: str
    original_label: str | None
    source_confidence: str | None
    method: str | None
    score: float | None
    notes: str | None
    source_lexeme: LexemeSummary
    target_lexeme: LexemeSummary
    evidence: list[EvidenceOut]
