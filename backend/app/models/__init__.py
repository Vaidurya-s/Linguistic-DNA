"""ORM models. See docs/TECHNICAL_ARCHITECTURE.md §5 and docs/DATASET_AUDIT.md §5."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    Direction,
    NativeFormOrigin,
    ReconstructionStatus,
    RelationshipNamespace,
    RelationshipStatus,
    ReuseStatus,
    SourceConfidence,
)


def pg_enum(enum_cls, name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class ImportBatch(Base):
    __tablename__ = "import_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(128))
    input_checksums: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    transformations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Source(Base):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    author_or_editor: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[str | None] = mapped_column(String(32))
    version_or_release: Mapped[str | None] = mapped_column(Text)
    licence_name: Mapped[str | None] = mapped_column(Text)
    licence_url: Mapped[str | None] = mapped_column(Text)
    reuse_status: Mapped[ReuseStatus] = mapped_column(pg_enum(ReuseStatus, "reuse_status"))
    attribution_text: Mapped[str | None] = mapped_column(Text)
    transliteration_scheme: Mapped[str | None] = mapped_column(Text)
    # A reference inside an aggregate (e.g. a Jambu bibliography key) points at the aggregate.
    parent_source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))
    notes: Mapped[str | None] = mapped_column(Text)


class LanguageFamily(Base):
    """Glottolog classification nodes. Kept apart from word relationships."""

    __tablename__ = "language_family"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # glottocode
    name: Mapped[str] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(String(32))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("language_family.id"))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))


class Language(Base):
    __tablename__ = "language"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    iso_code: Mapped[str | None] = mapped_column(String(8))
    # Not unique: several historical varieties share one glottocode (e.g. Prakrits).
    glottocode: Mapped[str | None] = mapped_column(String(16), index=True)
    family_id: Mapped[str | None] = mapped_column(ForeignKey("language_family.id"))
    classification_parent_id: Mapped[str | None] = mapped_column(ForeignKey("language_family.id"))
    role: Mapped[str] = mapped_column(String(16))  # modern | historical | reference | other
    is_proto: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class LanguageAlias(Base):
    __tablename__ = "language_alias"
    __table_args__ = (UniqueConstraint("scheme", "value", "language_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language_id: Mapped[str] = mapped_column(ForeignKey("language.id", ondelete="CASCADE"))
    scheme: Mapped[str] = mapped_column(String(32))  # jambu | iso639-3 | glottocode | name
    value: Mapped[str] = mapped_column(Text)


class Script(Base):
    __tablename__ = "script"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # ISO 15924 code
    name: Mapped[str] = mapped_column(Text)
    unicode_script: Mapped[str | None] = mapped_column(Text)
    transliteration_profile: Mapped[str | None] = mapped_column(Text)


class LanguageScript(Base):
    __tablename__ = "language_script"

    language_id: Mapped[str] = mapped_column(
        ForeignKey("language.id", ondelete="CASCADE"), primary_key=True
    )
    script_id: Mapped[str] = mapped_column(ForeignKey("script.id"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))


class Variety(Base):
    __tablename__ = "variety"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    language_id: Mapped[str] = mapped_column(ForeignKey("language.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    region_description: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))


class Lexeme(Base):
    __tablename__ = "lexeme"
    __table_args__ = (
        UniqueConstraint("dataset", "source_record_id"),
        Index("ix_lexeme_language_normalized", "language_id", "normalized_form"),
        Index("ix_lexeme_search_key", "search_key"),
        Index("ix_lexeme_native_form", "native_form"),
        Index(
            "ix_lexeme_search_key_trgm",
            "search_key",
            postgresql_using="gin",
            postgresql_ops={"search_key": "gin_trgm_ops"},
        ),
        Index(
            "ix_lexeme_normalized_trgm",
            "normalized_form",
            postgresql_using="gin",
            postgresql_ops={"normalized_form": "gin_trgm_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    language_id: Mapped[str] = mapped_column(ForeignKey("language.id"))
    variety_id: Mapped[str | None] = mapped_column(ForeignKey("variety.id"))
    form: Mapped[str] = mapped_column(Text)  # raw source representation
    normalized_form: Mapped[str] = mapped_column(Text)
    search_key: Mapped[str] = mapped_column(Text, server_default="")  # loose romanised key
    lemma: Mapped[str | None] = mapped_column(Text)
    native_form: Mapped[str | None] = mapped_column(Text)
    native_form_origin: Mapped[NativeFormOrigin | None] = mapped_column(
        pg_enum(NativeFormOrigin, "native_form_origin")
    )
    transliteration: Mapped[str | None] = mapped_column(Text)
    phonemic: Mapped[str | None] = mapped_column(Text)  # source transcription, not IPA
    ipa: Mapped[str | None] = mapped_column(Text)
    gloss: Mapped[str | None] = mapped_column(Text)
    reconstruction_status: Mapped[ReconstructionStatus] = mapped_column(
        pg_enum(ReconstructionStatus, "reconstruction_status")
    )
    source_status: Mapped[str | None] = mapped_column(String(32))  # e.g. Jambu entry/unlinked
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    dataset: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"), index=True)
    source_record_id: Mapped[str] = mapped_column(Text)
    source_citation: Mapped[str | None] = mapped_column(Text)  # raw citation keys and locators
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))


class Concept(Base):
    __tablename__ = "concept"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))


class LexemeConcept(Base):
    __tablename__ = "lexeme_concept"

    lexeme_id: Mapped[str] = mapped_column(
        ForeignKey("lexeme.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"), primary_key=True, index=True)
    sense_note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))


class RelationshipType(Base):
    __tablename__ = "relationship_type"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace: Mapped[RelationshipNamespace] = mapped_column(
        pg_enum(RelationshipNamespace, "relationship_namespace")
    )
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    default_direction: Mapped[Direction] = mapped_column(pg_enum(Direction, "direction"))


class Relationship(Base):
    """A typed edge read as: source_lexeme --type--> target_lexeme.

    For Jambu edges the source is the child (descendant, borrower, derivative, compound or
    variant) and the target is the parent it was taken from.
    """

    __tablename__ = "relationship"
    __table_args__ = (
        CheckConstraint(
            "source_id IS NOT NULL OR (status = 'candidate' AND method IS NOT NULL)",
            name="provenance_or_method",
        ),
        CheckConstraint("source_lexeme_id <> target_lexeme_id", name="no_self_loop"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_lexeme_id: Mapped[str] = mapped_column(
        ForeignKey("lexeme.id", ondelete="CASCADE"), index=True
    )
    target_lexeme_id: Mapped[str] = mapped_column(
        ForeignKey("lexeme.id", ondelete="CASCADE"), index=True
    )
    type_id: Mapped[str] = mapped_column(ForeignKey("relationship_type.id"), index=True)
    direction: Mapped[Direction] = mapped_column(pg_enum(Direction, "direction"))
    status: Mapped[RelationshipStatus] = mapped_column(
        pg_enum(RelationshipStatus, "relationship_status")
    )
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))
    source_record_id: Mapped[str | None] = mapped_column(Text)
    original_label: Mapped[str | None] = mapped_column(Text)
    source_confidence: Mapped[SourceConfidence | None] = mapped_column(
        pg_enum(SourceConfidence, "source_confidence")
    )
    method: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    dataset: Mapped[str] = mapped_column(String(64))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    relationship_id: Mapped[str] = mapped_column(
        ForeignKey("relationship.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    citation: Mapped[str] = mapped_column(Text)
    locator: Mapped[str | None] = mapped_column(Text)
    evidence_note: Mapped[str | None] = mapped_column(Text)
