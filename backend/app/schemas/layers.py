"""Response models for the layered retrieval endpoints.

Every item states its evidence kind, so a reader can never mistake a computed suggestion for a
cited record:

* ``documented``  a relationship a source dataset states; carries its evidence rows (citation,
  locator) and the dataset it came from.
* ``inferred``    a pair that a chain of documented ancestry relationships puts under one
  ancestor; carries the ids of the documented relationships the chain rests on.
* ``computed``    a candidate: same-meaning words ranked by a sound-aware similarity score; has
  no citation, only a method, its parameters, a score and a calibrated precision.
"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.api import EvidenceOut, LexemeSummary, SearchMatch


class DocumentedItem(BaseModel):
    evidence_kind: Literal["documented"] = "documented"
    relationship_id: str
    type: str
    label: str
    namespace: str
    direction: str
    status: str
    role: str  # the asked-about word is the "source" or the "target" of the stored link
    dataset: str
    source_id: str | None
    other: LexemeSummary
    evidence: list[EvidenceOut]


class ChainStep(BaseModel):
    relationship_id: str
    type: str
    dataset: str
    citation: str | None
    locator: str | None


class InferredItem(BaseModel):
    evidence_kind: Literal["inferred"] = "inferred"
    other: LexemeSummary
    kind: str  # common_ancestor | a_ancestor_of_b | b_ancestor_of_a | cognate_component
    depth: int
    ancestor: LexemeSummary | None
    chain_relationship_ids: list[str]
    chain: list[ChainStep]
    datasets: list[str]
    capped: bool
    rule_version: str


class CandidateItem(BaseModel):
    evidence_kind: Literal["computed"] = "computed"
    other: LexemeSummary
    method: str
    score: float
    gate: str
    gate_via: str
    calibrated_precision: float | None
    calibrated: bool
    stratum: str | None = None
    n_sources: int = 1
    params: dict = {}


class DocumentedBlock(BaseModel):
    layer: Literal["documented"] = "documented"
    evidence_kind: Literal["documented"] = "documented"
    count: int
    truncated: bool
    items: list[DocumentedItem]


class InferredBlock(BaseModel):
    layer: Literal["inferred"] = "inferred"
    evidence_kind: Literal["inferred"] = "inferred"
    count: int
    truncated: bool
    items: list[InferredItem]
    status: str = "ok"  # ok | unavailable


class CandidateBlock(BaseModel):
    layer: Literal["candidate"] = "candidate"
    evidence_kind: Literal["computed"] = "computed"
    count: int
    truncated: bool
    items: list[CandidateItem]
    status: str = "ok"  # ok | unavailable


class LayeredRelated(BaseModel):
    lexeme_id: str
    open_only: bool
    layers_requested: list[str]
    # in this order: documented first, then inferred, then candidate; a layer that was not
    # asked for is null
    documented: DocumentedBlock | None = None
    inferred: InferredBlock | None = None
    candidate: CandidateBlock | None = None
    warnings: list[str] = []


class TechniqueSearchResponse(BaseModel):
    """Result of one named search technique; every match says how it was found."""

    query: str
    normalized_query: str
    technique: str  # fuzzy | concept_gated | keys | sound
    matches: list[SearchMatch]
    warnings: list[str]
