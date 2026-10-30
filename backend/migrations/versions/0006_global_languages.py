"""global languages: per-language statistics, language profiles, translation links

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Counts computed after imports (app.cli refresh-stats), so /languages needs no scan.
    op.execute("""
        CREATE TABLE language_stats (
            language_id varchar(64) PRIMARY KEY
                REFERENCES language (id) ON DELETE CASCADE,
            lexeme_count integer NOT NULL,
            linked_count integer NOT NULL,
            open_lexeme_count integer NOT NULL,
            open_linked_count integer NOT NULL,
            refreshed_at timestamptz NOT NULL DEFAULT now()
        )""")
    # Typological and phonological facts about a language (WALS, PHOIBLE), cited per row.
    op.execute("""
        CREATE TABLE language_profile (
            id serial PRIMARY KEY,
            language_id varchar(64) NOT NULL REFERENCES language (id) ON DELETE CASCADE,
            dataset varchar(64) NOT NULL REFERENCES dataset_audit (id),
            feature_id text NOT NULL,
            feature_name text NOT NULL,
            value text NOT NULL,
            source_record_id text,
            citation text,
            UNIQUE (language_id, dataset, feature_id, value)
        )""")
    op.execute("CREATE INDEX ix_language_profile_language ON language_profile (language_id)")
    # Same-meaning pairs from parallel data and translation dictionaries. Kept apart from
    # relationship: a shared meaning is never drawn as word history.
    op.execute("""
        CREATE TABLE translation_link (
            id bigserial PRIMARY KEY,
            source_lexeme_id varchar(32) NOT NULL REFERENCES lexeme (id) ON DELETE CASCADE,
            target_lexeme_id varchar(32) NOT NULL REFERENCES lexeme (id) ON DELETE CASCADE,
            dataset varchar(64) NOT NULL REFERENCES dataset_audit (id),
            evidence_count integer NOT NULL DEFAULT 1,
            source_record_id text,
            UNIQUE (source_lexeme_id, target_lexeme_id, dataset)
        )""")
    op.execute("CREATE INDEX ix_translation_link_source ON translation_link (source_lexeme_id)")
    op.execute("CREATE INDEX ix_translation_link_target ON translation_link (target_lexeme_id)")


def downgrade() -> None:
    op.execute("DROP TABLE translation_link")
    op.execute("DROP TABLE language_profile")
    op.execute("DROP TABLE language_stats")
