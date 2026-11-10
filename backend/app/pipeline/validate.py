"""Data-quality checks from docs/DATASET_AND_LICENSING_PLAN.md §8.

Each check is a SQL query that counts violations. ``error`` checks must be zero for any
build. ``research`` checks must also be zero for the research database (no BLOCKED data,
every research-use record cited). ``release`` checks must additionally be zero for a
public seed (only data approved for redistribution). Non-blocking checks are reported.
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
    Check(
        "lexeme_dataset_not_audited",
        "error",
        "Lexemes whose import dataset has no row in dataset_audit.csv",
        """SELECT count(*) FROM lexeme l LEFT JOIN dataset_audit d ON d.id = l.dataset
           WHERE d.id IS NULL""",
    ),
    Check(
        "relationship_dataset_not_audited",
        "error",
        "Relationships whose import dataset has no row in dataset_audit.csv",
        """SELECT count(*) FROM relationship r LEFT JOIN dataset_audit d ON d.id = r.dataset
           WHERE d.id IS NULL""",
    ),
    Check(
        "source_without_dataset",
        "error",
        "Sources not linked to a dataset audit record",
        "SELECT count(*) FROM source WHERE dataset_id IS NULL",
    ),
    Check(
        "lexemes_from_blocked_datasets",
        "research",
        "Lexemes imported from a dataset the audit marks BLOCKED",
        """SELECT count(*) FROM lexeme l JOIN dataset_audit d ON d.id = l.dataset
           WHERE d.decision = 'BLOCKED'""",
    ),
    Check(
        "relationships_from_blocked_datasets",
        "research",
        "Relationships imported from a dataset the audit marks BLOCKED",
        """SELECT count(*) FROM relationship r JOIN dataset_audit d ON d.id = r.dataset
           WHERE d.decision = 'BLOCKED'""",
    ),
    Check(
        "research_lexeme_without_citation",
        "research",
        "Lexemes from a RESEARCH USE dataset that cite no source",
        """SELECT count(*) FROM lexeme l JOIN dataset_audit d ON d.id = l.dataset
           WHERE d.decision = 'RESEARCH USE' AND l.source_id IS NULL""",
    ),
    Check(
        "research_relationship_without_evidence",
        "research",
        "Relationships from a RESEARCH USE dataset with no evidence row citing a source",
        """SELECT count(*) FROM relationship r JOIN dataset_audit d ON d.id = r.dataset
           WHERE d.decision = 'RESEARCH USE'
             AND NOT EXISTS (SELECT 1 FROM evidence e WHERE e.relationship_id = r.id)""",
    ),
    Check(
        "lexemes_not_redistributable",
        "release",
        "Lexemes from a dataset the audit does not approve for redistribution",
        """SELECT count(*) FROM lexeme l JOIN dataset_audit d ON d.id = l.dataset
           WHERE d.decision NOT IN ('APPROVED', 'APPROVED WITH CONDITIONS')""",
    ),
    Check(
        "relationships_not_redistributable",
        "release",
        "Relationships from a dataset the audit does not approve for redistribution",
        """SELECT count(*) FROM relationship r JOIN dataset_audit d ON d.id = r.dataset
           WHERE d.decision NOT IN ('APPROVED', 'APPROVED WITH CONDITIONS')""",
    ),
    Check(
        "stem_or_affix_marked_word",
        "error",
        "Forms with a leading/trailing hyphen or a root sign classified as words",
        """SELECT count(*) FROM lexeme WHERE form_kind = 'word'
           AND (form ~ '^\\*?-' OR form ~ '-$' OR form ~ '^\\*?√')""",
    ),
    # The checks below are informational for now: the live data still has violations.
    Check(
        "mutual_ancestry_pairs",
        "info",
        "Two-node ancestry cycles: a and b of the same type (inherited_form, borrowed_from, "
        "etymon, calque_or_loan_translation) with a.source = b.target and a.target = b.source. "
        "Each cycle is counted once. Uses the source/target lexeme indexes.",
        """SELECT count(*) FROM relationship a
             WHERE a.type_id IN ('inherited_form', 'borrowed_from', 'etymon',
                                 'calque_or_loan_translation')
               AND EXISTS (SELECT 1 FROM relationship b
                             WHERE b.source_lexeme_id = a.target_lexeme_id
                               AND b.target_lexeme_id = a.source_lexeme_id
                               AND b.type_id = a.type_id
                               AND a.id < b.id)""",
    ),
    Check(
        "conflicting_ancestry_types",
        "info",
        "The same (source, target) pair holds inherited_form and also borrowed_from or "
        "calque_or_loan_translation. Counts the inherited_form edges that have such a twin.",
        """SELECT count(*) FROM relationship a
             WHERE a.type_id = 'inherited_form'
               AND EXISTS (SELECT 1 FROM relationship b
                             WHERE b.source_lexeme_id = a.source_lexeme_id
                               AND b.target_lexeme_id = a.target_lexeme_id
                               AND b.type_id IN ('borrowed_from', 'calque_or_loan_translation'))""",
    ),
    Check(
        "searchable_language_empty_search_key",
        "info",
        "Lexemes with an empty search_key in a searchable (is_enabled) language: "
        "they can never be found by search",
        """SELECT count(*) FROM lexeme l JOIN language g ON g.id = l.language_id
             WHERE l.search_key = '' AND g.is_enabled""",
    ),
    Check(
        "markup_in_forms_and_glosses",
        "info",
        "Forms or glosses with wiki or HTML-entity markup ({{ }} [[ ]], &amp; &lt; &#...). "
        "markup_in_text_fields covers only HTML tags in gloss and source_citation, so this "
        "is separate; <...> infix notation is not flagged. Scans lexeme in full (sequential).",
        """SELECT count(*) FROM lexeme
             WHERE form LIKE '%{{%' OR form LIKE '%}}%' OR form LIKE '%[[%' OR form LIKE '%]]%'
                OR form ~ '&(#|[A-Za-z][A-Za-z0-9]{1,7};)'
                OR gloss LIKE '%{{%' OR gloss LIKE '%}}%'
                OR gloss LIKE '%[[%' OR gloss LIKE '%]]%'
                OR gloss ~ '&(#|[A-Za-z][A-Za-z0-9]{1,7};)'""",
    ),
    Check(
        "markup_in_citations",
        "info",
        "Evidence citations still carrying wiki template braces ({{ or }}). "
        "Scans evidence in full (sequential).",
        """SELECT count(*) FROM evidence
             WHERE citation LIKE '%{{%' OR citation LIKE '%}}%'""",
    ),
    Check(
        "citation_is_bare_source_key",
        "info",
        "Evidence whose citation is only the source key (any case) or a single short token "
        "(no space, under 12 characters, e.g. dedr, CDIAL, strand) instead of a real citation. "
        "Scans evidence in full (sequential).",
        """SELECT count(*) FROM evidence
             WHERE lower(citation) = lower(source_id)
                OR (citation !~ '[[:space:]]' AND length(citation) < 12)""",
    ),
    Check(
        "ancestor_inherited_from_descendant",
        "info",
        "Heuristic: inherited_form edges (source = entry, target = ancestor) whose source "
        "language name starts with Proto-, Old or Middle and whose target is one of the "
        "configured modern languages (role 'modern'): an older stage 'inherited from' a "
        "modern word. Names are not a classification; review, never auto-fix.",
        """SELECT count(*) FROM relationship r
             JOIN lexeme s ON s.id = r.source_lexeme_id
             JOIN language sl ON sl.id = s.language_id
             JOIN lexeme t ON t.id = r.target_lexeme_id
             JOIN language tl ON tl.id = t.language_id
             WHERE r.type_id = 'inherited_form'
               AND sl.name ~ '^(Proto-|Old |Middle )'
               AND tl.role = 'modern'""",
    ),
]


BLOCKING = {
    "development": {"error"},
    "research": {"error", "research"},
    "public_seed": {"error", "research", "release"},
}


def run_checks(conn: psycopg.Connection, public_seed: bool = False, research: bool = False) -> dict:
    mode = "public_seed" if public_seed else "research" if research else "development"
    results = []
    with conn.cursor() as cur:
        for check in CHECKS:
            cur.execute(check.sql)
            violations = cur.fetchone()[0]
            blocking = check.severity in BLOCKING[mode]
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
        "mode": mode,
        "passed": all(r["passed"] for r in results),
        "checks": results,
    }
