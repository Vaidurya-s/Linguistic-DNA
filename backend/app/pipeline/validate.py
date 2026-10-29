"""Data-quality checks from docs/DATASET_AND_LICENSING_PLAN.md §8.

Each check is a SQL query that counts violations. ``error`` checks must be zero for any
build. ``release`` checks must be zero only for a public seed; they are reported but do
not fail a development import.
"""

from dataclasses import asdict, dataclass

import psycopg

ALLOWED_PUBLIC = "('approved', 'attribution_required')"


@dataclass(frozen=True)
class Check:
    name: str
    severity: str  # error | release | info
    description: str
    sql: str


CHECKS = [
    Check(
        "relationship_missing_lexeme",
        "error",
        "Relationships pointing at a lexeme that does not exist",
        """SELECT count(*) FROM relationship r
             LEFT JOIN lexeme s ON s.id = r.source_lexeme_id
             LEFT JOIN lexeme t ON t.id = r.target_lexeme_id
             WHERE s.id IS NULL OR t.id IS NULL""",
    ),
    Check(
        "lexeme_unknown_language",
        "error",
        "Lexemes whose language is not in the language table",
        """SELECT count(*) FROM lexeme l LEFT JOIN language g ON g.id = l.language_id
             WHERE g.id IS NULL""",
    ),
    Check(
        "documented_edge_without_evidence",
        "error",
        "Documented relationships with no evidence row",
        """SELECT count(*) FROM relationship r WHERE r.status = 'documented'
             AND NOT EXISTS (SELECT 1 FROM evidence e WHERE e.relationship_id = r.id)""",
    ),
    Check(
        "documented_edge_without_source",
        "error",
        "Documented relationships with no source",
        "SELECT count(*) FROM relationship WHERE status = 'documented' AND source_id IS NULL",
    ),
    Check(
        "candidate_without_method",
        "error",
        "Candidate relationships without a method",
        "SELECT count(*) FROM relationship WHERE status = 'candidate' AND method IS NULL",
    ),
    Check(
        "reconstructed_marked_attested",
        "error",
        "Starred forms or proto-language forms marked as attested",
        """SELECT count(*) FROM lexeme l JOIN language g ON g.id = l.language_id
             WHERE l.reconstruction_status = 'attested'
               AND (l.form LIKE '*%' OR g.is_proto)""",
    ),
    Check(
        "classification_type_on_word_edge",
        "error",
        "Classification-namespace types used for word-to-word edges",
        """SELECT count(*) FROM relationship r JOIN relationship_type t ON t.id = r.type_id
             WHERE t.namespace = 'classification'""",
    ),
    Check(
        "directed_type_without_direction",
        "error",
        "Borrowing/inheritance edges stored as undirected",
        """SELECT count(*) FROM relationship r JOIN relationship_type t ON t.id = r.type_id
             WHERE t.default_direction = 'directed' AND r.direction = 'undirected'""",
    ),
    Check(
        "normalized_form_empty",
        "error",
        "Lexemes with an empty normalized form",
        "SELECT count(*) FROM lexeme WHERE normalized_form = '' AND form <> ''",
    ),
    Check(
        "raw_form_lost",
        "error",
        "Lexemes whose raw form is missing",
        "SELECT count(*) FROM lexeme WHERE form IS NULL",
    ),
    Check(
        "evidence_unknown_source",
        "error",
        "Evidence rows citing a missing source",
        """SELECT count(*) FROM evidence e LEFT JOIN source s ON s.id = e.source_id
             WHERE s.id IS NULL""",
    ),
    Check(
        "markup_in_text_fields",
        "error",
        "Glosses or citations still carrying dictionary HTML markup",
        """SELECT count(*) FROM lexeme
             WHERE gloss ~ '</?(b|i|number|smallcaps|a)[ >]'
                OR source_citation ~ '</?(b|i|number|smallcaps|a)[ >]'""",
    ),
    Check(
        "exact_duplicate_lexemes",
        "info",
        "Same language + form + gloss + source (reviewed, never auto-removed)",
        """SELECT coalesce(sum(n - 1), 0) FROM (
               SELECT count(*) n FROM lexeme
               GROUP BY language_id, form, gloss, source_id HAVING count(*) > 1) d""",
    ),
    Check(
        "lexemes_from_unreviewed_sources",
        "release",
        "Lexemes whose source is not approved or attribution_required",
        f"""SELECT count(*) FROM lexeme l JOIN source s ON s.id = l.source_id
              WHERE s.reuse_status NOT IN {ALLOWED_PUBLIC}""",
    ),
    Check(
        "relationships_from_unreviewed_sources",
        "release",
        "Relationships whose source is not approved or attribution_required",
        f"""SELECT count(*) FROM relationship r JOIN source s ON s.id = r.source_id
              WHERE s.reuse_status NOT IN {ALLOWED_PUBLIC}""",
    ),
]


def run_checks(conn: psycopg.Connection, public_seed: bool = False) -> dict:
    results = []
    with conn.cursor() as cur:
        for check in CHECKS:
            cur.execute(check.sql)
            violations = cur.fetchone()[0]
            blocking = check.severity == "error" or (public_seed and check.severity == "release")
            results.append(
                {
                    **asdict(check),
                    "sql": None,
                    "violations": int(violations),
                    "passed": violations == 0 or not blocking,
                    "blocking": blocking,
                }
            )
    return {
        "mode": "public_seed" if public_seed else "development",
        "passed": all(r["passed"] for r in results),
        "checks": results,
    }
