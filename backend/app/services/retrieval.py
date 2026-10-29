"""Read-side queries: search, lexeme detail, bounded graph, relationship evidence.

Documented relations and computed candidates are returned in separate fields and are never
merged (docs/LINGUISTIC_ENGINE.md §2, §6).
"""

import unicodedata

from sqlalchemy import Connection, text

from app.services.normalize import normalize_form, search_key

LEXEME_FIELDS = """
    l.id, l.form, l.native_form, l.language_id, g.name AS language_name,
    g.metadata_json->>'group' AS "group", l.gloss, l.reconstruction_status::text,
    g.is_proto
"""


def detect_script(value: str) -> str:
    """Name of the first non-Latin script in the string, or Latin."""
    for ch in value:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            first = name.split(" ")[0]
            if first not in ("LATIN", "MODIFIER", "COMBINING", "GREEK"):
                return first.title()
    return "Latin"


_languages_cache: dict[int | None, list[dict]] = {}


def list_languages(conn: Connection) -> list[dict]:
    """Enabled languages with counts, cached until the next import batch."""
    batch = conn.execute(text("SELECT max(id) FROM import_batch")).scalar()
    if batch not in _languages_cache:
        _languages_cache.clear()
        _languages_cache[batch] = _language_rows(conn)
    return _languages_cache[batch]


def _language_rows(conn: Connection) -> list[dict]:
    rows = conn.execute(
        text("""
                SELECT g.id, g.name, g.role, g.metadata_json->>'group' AS "group", g.family_id,
               f.name AS family_name, g.glottocode, ls.script_id AS primary_script,
               count(l.id) AS lexeme_count,
               count(l.id) FILTER (WHERE EXISTS (
                   SELECT 1 FROM relationship r WHERE r.source_lexeme_id = l.id
                     AND r.status = 'documented')) AS linked_count
        FROM language g
        LEFT JOIN language_family f ON f.id = g.family_id
        LEFT JOIN language_script ls ON ls.language_id = g.id AND ls.is_primary
        LEFT JOIN lexeme l ON l.language_id = g.id
        WHERE g.is_enabled
        GROUP BY g.id, f.name, ls.script_id
        ORDER BY CASE g.role WHEN 'modern' THEN 0 WHEN 'historical' THEN 1 ELSE 2 END, g.name
    """)
    ).mappings()
    return [dict(r) for r in rows]


def search(conn: Connection, q: str, language_id: str | None, limit: int) -> dict:
    normalized = normalize_form(q)
    key = search_key(q)
    script = detect_script(normalized)
    warnings: list[str] = []
    params = {"q": normalized, "key": key, "lang": language_id, "limit": limit}

    matches = _rows(
        conn,
        """
        WITH hits AS (
            SELECT l.*, CASE WHEN l.normalized_form = :q THEN 'exact'
                             WHEN l.native_form = :q THEN 'native_exact'
                             ELSE 'loose' END AS match_type
            FROM lexeme l
            WHERE (l.normalized_form = :q OR l.native_form = :q OR l.search_key = :key)
              AND (CAST(:lang AS text) IS NULL OR l.language_id = :lang)
        ), ranked AS (
            SELECT h.*, (SELECT count(*) FROM relationship r
                         WHERE r.source_lexeme_id = h.id OR r.target_lexeme_id = h.id) AS rels
            FROM hits h
        ), grouped AS (
            SELECT DISTINCT ON (language_id, form, coalesce(gloss, '')) *,
                   count(*) OVER (PARTITION BY language_id, form, coalesce(gloss, '')) AS dups
            FROM ranked
            ORDER BY language_id, form, coalesce(gloss, ''), rels DESC, id
        )
        SELECT """
        + LEXEME_FIELDS
        + """, l.match_type, NULL::float AS score,
               l.rels AS relationship_count, l.dups AS duplicate_count
        FROM grouped l JOIN language g ON g.id = l.language_id
        WHERE g.is_enabled
        ORDER BY (l.match_type = 'loose'), l.rels DESC, g.name, l.form
        LIMIT :limit
    """,
        params,
    )

    candidates = []
    if len(key) >= 3:
        conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.45"))
        candidates = _rows(
            conn,
            """
            SELECT DISTINCT ON (l.language_id, l.form) """
            + LEXEME_FIELDS
            + """,
                   'spelling_candidate' AS match_type,
                   similarity(l.search_key, :key) AS score,
                   (SELECT count(*) FROM relationship r WHERE r.source_lexeme_id = l.id)
                       AS relationship_count,
                   1 AS duplicate_count
            FROM lexeme l JOIN language g ON g.id = l.language_id
            WHERE l.search_key % :key AND l.search_key <> :key AND g.is_enabled
              AND (CAST(:lang AS text) IS NULL OR l.language_id = :lang)
            ORDER BY l.language_id, l.form, score DESC
        """,
            params,
        )
        candidates = sorted(candidates, key=lambda r: -r["score"])[:limit]

    hints = sorted({m["language_id"] for m in matches})
    if len(hints) > 1 and not language_id:
        warnings.append("This form exists in several languages; pick one to narrow the result.")
    if script != "Latin" and not matches:
        warnings.append(
            f"Few records in this dataset carry {script} spellings; most forms are in scholarly "
            "romanisation. Try a romanised spelling."
        )
    if not matches and not candidates:
        warnings.append("No form in the indexed dataset matches this query.")
    return {
        "query": q,
        "normalized_query": normalized,
        "detected_script": script,
        "language_hints": hints,
        "matches": matches,
        "spelling_candidates": candidates,
        "warnings": warnings,
    }


def get_lexeme(conn: Connection, lexeme_id: str) -> dict | None:
    row = (
        conn.execute(
            text(f"""
        SELECT {LEXEME_FIELDS}, l.transliteration, l.phonemic, l.source_status,
               l.source_record_id, l.source_citation, l.source_id
        FROM lexeme l JOIN language g ON g.id = l.language_id WHERE l.id = :id
    """),
            {"id": lexeme_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    out = dict(row)
    out["source"] = _source(conn, out.pop("source_id"))
    out["concepts"] = _rows(
        conn,
        """
        SELECT c.id, c.label FROM lexeme_concept lc JOIN concept c ON c.id = lc.concept_id
        WHERE lc.lexeme_id = :id ORDER BY c.label
    """,
        {"id": lexeme_id},
    )
    return out


def build_graph(
    conn: Connection,
    root: str,
    depth: int,
    types: list[str] | None,
    language_ids: list[str] | None,
    limit_nodes: int,
) -> dict | None:
    if not conn.execute(text("SELECT 1 FROM lexeme WHERE id = :id"), {"id": root}).first():
        return None
    seen = {root}
    frontier = [root]
    edges: dict[str, dict] = {}
    truncated = False
    for _ in range(depth):
        if not frontier or truncated:
            break
        rows = _rows(
            conn,
            """
            SELECT r.id, r.source_lexeme_id AS source, r.target_lexeme_id AS target,
                   r.type_id AS type, t.label, t.namespace::text, r.status::text,
                   r.direction::text, r.source_id,
                   (SELECT e.citation || coalesce(' [' || e.locator || ']', '') FROM evidence e
                    WHERE e.relationship_id = r.id ORDER BY e.id LIMIT 1) AS citation,
                   s.language_id AS source_language, tg.language_id AS target_language
            FROM relationship r
            JOIN relationship_type t ON t.id = r.type_id
            JOIN lexeme s ON s.id = r.source_lexeme_id
            JOIN lexeme tg ON tg.id = r.target_lexeme_id
            WHERE (r.source_lexeme_id = ANY(:ids) OR r.target_lexeme_id = ANY(:ids))
              AND r.status <> 'rejected'
              AND (CAST(:types AS text[]) IS NULL OR r.type_id = ANY(:types))
            ORDER BY r.type_id, r.id
        """,
            {"ids": frontier, "types": types},
        )
        nxt = []
        for e in rows:
            other = e["target"] if e["source"] in frontier else e["source"]
            other_lang = e["target_language"] if other == e["target"] else e["source_language"]
            if language_ids and other not in seen and other_lang not in language_ids:
                continue
            if other not in seen:
                if len(seen) >= limit_nodes:
                    truncated = True
                    continue
                seen.add(other)
                nxt.append(other)
            edges[e["id"]] = {
                k: v for k, v in e.items() if k not in ("source_language", "target_language")
            }
        frontier = nxt

    nodes = _rows(
        conn,
        f"""
        SELECT {LEXEME_FIELDS},
               (SELECT count(*) FROM relationship r
                WHERE r.source_lexeme_id = l.id OR r.target_lexeme_id = l.id) AS degree
        FROM lexeme l JOIN language g ON g.id = l.language_id WHERE l.id = ANY(:ids)
    """,
        {"ids": list(seen)},
    )
    warnings = []
    if truncated:
        warnings.append(f"Graph truncated at {limit_nodes} nodes; expand nodes or filter.")
    return {
        "root_lexeme_id": root,
        "nodes": nodes,
        "edges": list(edges.values()),
        "truncated": truncated,
        "warnings": warnings,
    }


def get_relationship(conn: Connection, rel_id: str) -> dict | None:
    row = (
        conn.execute(
            text("""
        SELECT r.id, r.source_lexeme_id AS source, r.target_lexeme_id AS target,
               r.type_id AS type, t.label, t.description, t.namespace::text, r.status::text,
               r.direction::text, r.source_id, r.original_label,
               r.source_confidence::text, r.method, r.score, r.notes
        FROM relationship r JOIN relationship_type t ON t.id = r.type_id WHERE r.id = :id
    """),
            {"id": rel_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    out = dict(row)
    lex = {
        r["id"]: r
        for r in _rows(
            conn,
            f"""
        SELECT {LEXEME_FIELDS} FROM lexeme l JOIN language g ON g.id = l.language_id
        WHERE l.id = ANY(:ids)""",
            {"ids": [out["source"], out["target"]]},
        )
    }
    out["source_lexeme"], out["target_lexeme"] = lex[out["source"]], lex[out["target"]]
    evidence = _rows(
        conn,
        """
        SELECT citation, locator, evidence_note AS note, source_id FROM evidence
        WHERE relationship_id = :id ORDER BY id""",
        {"id": rel_id},
    )
    for e in evidence:
        e["source"] = _source(conn, e.pop("source_id"))
    out["evidence"] = evidence
    out["citation"] = evidence[0]["citation"] if evidence else None
    return out


def _source(conn: Connection, source_id: str | None) -> dict | None:
    if not source_id:
        return None
    row = (
        conn.execute(
            text("""
        SELECT id, title, reuse_status::text, licence_name, url FROM source WHERE id = :id
    """),
            {"id": source_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def _rows(conn: Connection, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]
