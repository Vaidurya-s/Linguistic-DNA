"""Per-language coverage computed from the database (Dataset plan §3)."""

import psycopg

COVERAGE_SQL = """
WITH linked AS (
    SELECT DISTINCT r.source_lexeme_id AS id FROM relationship r
    JOIN relationship_type t ON t.id = r.type_id
    WHERE r.status = 'documented' AND t.namespace = 'lexical'
)
SELECT g.id, g.name,
       count(DISTINCT l.id) AS forms,
       count(DISTINCT lc.concept_id) AS concepts,
       count(DISTINCT l.id) FILTER (WHERE l.id IN (SELECT id FROM linked)) AS linked,
       count(DISTINCT l.id) FILTER (WHERE l.native_form IS NOT NULL) AS native_script,
       count(DISTINCT l.id) FILTER (WHERE l.phonemic IS NOT NULL OR l.ipa IS NOT NULL)
           AS pronunciation,
       count(DISTINCT l.id) FILTER (WHERE l.reconstruction_status = 'reconstructed')
           AS reconstructed,
       count(DISTINCT l.id) FILTER (WHERE s.reuse_status IN ('approved', 'attribution_required'))
           AS publishable
FROM language g
JOIN lexeme l ON l.language_id = g.id
LEFT JOIN lexeme_concept lc ON lc.lexeme_id = l.id
LEFT JOIN source s ON s.id = l.source_id
WHERE g.is_enabled
GROUP BY g.id, g.name
ORDER BY g.id
"""

COLUMNS = (
    "language_id",
    "name",
    "forms",
    "concepts",
    "linked",
    "native_script",
    "pronunciation",
    "reconstructed",
    "publishable",
)


def coverage(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(COVERAGE_SQL)
        return [dict(zip(COLUMNS, row, strict=True)) for row in cur.fetchall()]


def to_markdown(rows: list[dict]) -> str:
    head = "| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n"
    return head + "".join("| " + " | ".join(str(r[c]) for c in COLUMNS) + " |\n" for r in rows)
