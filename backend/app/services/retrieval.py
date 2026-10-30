"""Read-side queries: search, lexeme detail, bounded graph, relationship evidence.

Documented relations and computed candidates are returned in separate fields and are never
merged (docs/LINGUISTIC_ENGINE.md §2, §6).
"""

import unicodedata

from sqlalchemy import Connection, text

from app.services.normalize import normalize_form, search_key
from app.services.transliterate import ISO15924, romanize_variants, script_of

# Scholarly reference layers written in Latin but read from Devanagari sources.
EXTRA_SCRIPT_LANGUAGES = {"Deva": ["oia", "pra", "pli", "x-apabhramsha", "x-ashokan-prakrit"]}
MATCH_RANK = {"exact": 0, "native_exact": 1, "transliteration": 2, "loose": 3}

OPEN_DECISIONS = ("APPROVED", "APPROVED WITH CONDITIONS")


def open_datasets(conn: Connection, open_only: bool) -> list[str] | None:
    """Datasets approved for redistribution, or None (no filter) when open_only is off.

    Research-use datasets (e.g. Jambu, CDIAL, DEDR) are left out of an open-only view."""
    if not open_only:
        return None
    rows = conn.execute(
        text("SELECT id FROM dataset_audit WHERE decision::text = ANY(:d)"),
        {"d": list(OPEN_DECISIONS)},
    )
    return [r[0] for r in rows]


LEXEME_FIELDS = """
    l.id, l.form, l.native_form, l.language_id, g.name AS language_name,
    g.metadata_json->>'group' AS "group", l.gloss, l.reconstruction_status::text,
    g.is_proto, l.form_kind::text
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


_citations_cache: dict[int | None, dict] = {}


def list_citations(conn: Connection) -> dict:
    """Every dataset in use and every work cited by its records, with record counts.

    Research-use datasets are listed with the citation the audit requires; works cited by
    an aggregate (e.g. the dictionaries Jambu draws on) are listed under it."""
    batch = conn.execute(text("SELECT max(id) FROM import_batch")).scalar()
    if batch not in _citations_cache:
        _citations_cache.clear()
        datasets = _rows(
            conn,
            """
            WITH lx AS (SELECT dataset, count(*) AS n FROM lexeme GROUP BY dataset),
                 rel AS (SELECT dataset, count(*) AS n FROM relationship GROUP BY dataset)
            SELECT d.id, d.name, d.decision::text AS decision, d.licence_name,
                   d.attribution_text AS citation, d.licence_url, d.version,
                   coalesce(lx.n, 0) AS lexeme_count, coalesce(rel.n, 0) AS relationship_count
            FROM dataset_audit d LEFT JOIN lx ON lx.dataset = d.id
            LEFT JOIN rel ON rel.dataset = d.id
            WHERE coalesce(lx.n, 0) + coalesce(rel.n, 0) > 0
            ORDER BY lexeme_count DESC, d.id
        """,
            {},
        )
        works = _rows(
            conn,
            """
            WITH cited AS (
                SELECT source_id, count(*) AS n FROM lexeme
                WHERE source_id IS NOT NULL GROUP BY source_id
                UNION ALL
                SELECT source_id, count(*) FROM evidence GROUP BY source_id
            )
            SELECT s.id, s.title, s.url, s.dataset_id, sum(c.n)::bigint AS record_count
            FROM cited c JOIN source s ON s.id = c.source_id
            GROUP BY s.id ORDER BY record_count DESC, s.title
        """,
            {},
        )
        _citations_cache[batch] = {"datasets": datasets, "works": works}
    return _citations_cache[batch]


def _language_rows(conn: Connection) -> list[dict]:
    """Searchable languages with word counts: from language_stats (computed after imports by
    ``app.cli refresh-languages``), or counted live when that table is empty."""
    precomputed = conn.execute(text("SELECT EXISTS (SELECT 1 FROM language_stats)")).scalar()
    counts = (
        """coalesce(st.lexeme_count, 0) AS lexeme_count,
               coalesce(st.linked_count, 0) AS linked_count,
               coalesce(st.open_lexeme_count, 0) AS open_lexeme_count,
               coalesce(st.open_linked_count, 0) AS open_linked_count
        FROM language g LEFT JOIN language_stats st ON st.language_id = g.id"""
        if precomputed
        else """(SELECT count(*) FROM lexeme l WHERE l.language_id = g.id) AS lexeme_count,
               (SELECT count(*) FROM lexeme l WHERE l.language_id = g.id AND (
                   EXISTS (SELECT 1 FROM relationship r WHERE r.source_lexeme_id = l.id)
                   OR EXISTS (SELECT 1 FROM relationship r WHERE r.target_lexeme_id = l.id)))
                   AS linked_count,
               NULL::int AS open_lexeme_count, NULL::int AS open_linked_count
        FROM language g"""
    )
    rows = conn.execute(
        text(f"""
        SELECT g.id, g.name, g.role, g.metadata_json->>'group' AS "group", g.family_id,
               f.name AS family_name, g.glottocode, ls.script_id AS primary_script,
               {counts}
        LEFT JOIN language_family f ON f.id = g.family_id
        LEFT JOIN language_script ls ON ls.language_id = g.id AND ls.is_primary
        WHERE g.is_enabled
        ORDER BY CASE g.role WHEN 'modern' THEN 0 WHEN 'historical' THEN 1 ELSE 2 END, g.name
    """)
    ).mappings()
    return [dict(r) for r in rows]


def search(
    conn: Connection, q: str, language_id: str | None, limit: int, open_only: bool = False
) -> dict:
    normalized = normalize_form(q)
    key = search_key(q)
    script = detect_script(normalized)
    warnings: list[str] = []
    ds = open_datasets(conn, open_only)
    params = {"q": normalized, "key": key, "lang": language_id, "limit": limit, "ds": ds}

    routes = transliteration_routes(conn, normalized, key)
    hits = _rows(
        conn,
        """
        WITH t(key, lang, via) AS (
            SELECT * FROM unnest(CAST(:tkeys AS text[]), CAST(:tlangs AS text[]),
                                 CAST(:tvias AS text[]))
        ), hits AS (
            SELECT l.*, CASE WHEN l.normalized_form = :q THEN 'exact'
                             WHEN l.native_form = :q THEN 'native_exact'
                             ELSE 'loose' END AS match_type, NULL::text AS via
            FROM lexeme l
            WHERE (l.normalized_form = :q OR l.native_form = :q
                   OR (:latin AND l.search_key = :key))
              AND (CAST(:lang AS text) IS NULL OR l.language_id = :lang)
              AND (CAST(:ds AS text[]) IS NULL OR l.dataset = ANY(:ds))
            UNION ALL
            SELECT l.*, 'transliteration', t.via
            FROM lexeme l JOIN t ON l.search_key = t.key AND l.language_id = t.lang
            WHERE (CAST(:lang AS text) IS NULL OR l.language_id = :lang)
              AND (CAST(:ds AS text[]) IS NULL OR l.dataset = ANY(:ds))
        ), best AS (
            SELECT DISTINCT ON (id) * FROM hits
            ORDER BY id, CASE match_type WHEN 'exact' THEN 0 WHEN 'native_exact' THEN 1
                                         WHEN 'transliteration' THEN 2 ELSE 3 END
        ), ranked AS (
            SELECT h.*, (SELECT count(*) FROM relationship r
                         WHERE (r.source_lexeme_id = h.id OR r.target_lexeme_id = h.id)
                           AND (CAST(:ds AS text[]) IS NULL OR r.dataset = ANY(:ds))) AS rels
            FROM best h
        ), grouped AS (
            SELECT DISTINCT ON (language_id, form, coalesce(gloss, '')) *,
                   count(*) OVER (PARTITION BY language_id, form, coalesce(gloss, '')) AS dups
            FROM ranked
            ORDER BY language_id, form, coalesce(gloss, ''), rels DESC, id
        )
        SELECT """
        + LEXEME_FIELDS
        + """, l.match_type, l.via, NULL::float AS score,
               l.rels AS relationship_count, l.dups AS duplicate_count
        FROM grouped l JOIN language g ON g.id = l.language_id
        WHERE g.is_enabled
        LIMIT :wide
    """,
        {
            **params,
            "wide": limit * 6,
            # Native-script queries reach romanised records only via script-restricted
            # transliteration routes, never via the bare loose key.
            "latin": script_of(normalized) is None,
            "tkeys": [r[0] for r in routes],
            "tlangs": [r[1] for r in routes],
            "tvias": [r[2] for r in routes],
        },
    )
    hits.sort(
        key=lambda h: (
            MATCH_RANK.get(h["match_type"], 9),
            -h["relationship_count"],
            h["language_name"],
            h["form"],
        )
    )
    # Only whole words can be matches; stems, affixes, roots, phrases and compounds that
    # happen to share the spelling are listed separately (they are different units).
    matches = [h for h in hits if h["form_kind"] == "word"][:limit]
    related_forms = [h for h in hits if h["form_kind"] != "word"][:limit]
    compounds = _compounds_containing(conn, [m["id"] for m in matches], limit, ds)

    candidates = []
    if len(key) >= 3:
        conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.45"))
        candidates = _rows(
            conn,
            """
            SELECT DISTINCT ON (l.language_id, l.form) """
            + LEXEME_FIELDS
            + """,
                   'spelling_candidate' AS match_type, NULL::text AS via,
                   similarity(l.search_key, :key) AS score,
                   (SELECT count(*) FROM relationship r WHERE r.source_lexeme_id = l.id
                    AND (CAST(:ds AS text[]) IS NULL OR r.dataset = ANY(:ds)))
                       AS relationship_count,
                   1 AS duplicate_count
            FROM lexeme l JOIN language g ON g.id = l.language_id
            WHERE l.search_key % :key AND l.search_key <> :key AND g.is_enabled
              AND l.form_kind = 'word'
              AND (CAST(:lang AS text) IS NULL OR l.language_id = :lang)
              AND (CAST(:ds AS text[]) IS NULL OR l.dataset = ANY(:ds))
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
    if not matches and not related_forms and not candidates:
        warnings.append("No form in the indexed dataset matches this query.")
    return {
        "query": q,
        "normalized_query": normalized,
        "detected_script": script,
        "language_hints": hints,
        "matches": matches,
        "related_forms": related_forms,
        "compounds": compounds,
        "spelling_candidates": candidates,
        "warnings": warnings,
    }


def script_languages(conn: Connection, iso: str) -> list[str]:
    rows = conn.execute(
        text("""
        SELECT ls.language_id FROM language_script ls JOIN language g ON g.id = ls.language_id
        WHERE ls.script_id = :s AND g.is_enabled"""),
        {"s": iso},
    )
    return [r[0] for r in rows] + EXTRA_SCRIPT_LANGUAGES.get(iso, [])


def transliteration_routes(conn: Connection, normalized: str, key: str) -> list[tuple]:
    """(search key, language, explanation) triples for matching across scripts.

    Native-script input is romanised by rule for the languages that use that script.
    Romanised input is looked up in the transliteration aliases (Dakshina, Aksharantar) to
    find native spellings, which are then romanised the same way.
    """
    routes: list[tuple] = []
    script = script_of(normalized)
    if script:
        langs = script_languages(conn, ISO15924[script])
        for variant in romanize_variants(normalized):
            for lang in langs:
                routes.append((search_key(variant), lang, f"{normalized} → {variant} (by rule)"))
    elif key:
        aliases = conn.execute(
            text("""
            SELECT language_id, native, max(dataset) AS dataset, sum(coalesce(weight, 1)) AS w
            FROM transliteration_alias WHERE roman_key = :k
            GROUP BY language_id, native ORDER BY w DESC LIMIT 12"""),
            {"k": key},
        ).all()
        for lang, native, dataset, _ in aliases:
            for variant in romanize_variants(native)[:2]:
                routes.append(
                    (search_key(variant), lang, f"{normalized} → {native} ({dataset}) → {variant}")
                )
    seen, unique = set(), []
    for r in routes:
        if (r[0], r[1]) not in seen and r[0]:
            seen.add((r[0], r[1]))
            unique.append(r)
    return unique


def _compounds_containing(
    conn: Connection, ids: list[str], limit: int, ds: list[str] | None = None
) -> list[dict]:
    """Compounds documented (has_component) as containing one of the matched words."""
    if not ids:
        return []
    return _rows(
        conn,
        """
        SELECT DISTINCT ON (l.id) """
        + LEXEME_FIELDS
        + """, 'compound_of_match' AS match_type, NULL::text AS via, NULL::float AS score,
               (SELECT count(*) FROM relationship x
                WHERE x.source_lexeme_id = l.id OR x.target_lexeme_id = l.id)
                   AS relationship_count, 1 AS duplicate_count
        FROM relationship r
        JOIN lexeme l ON l.id = r.source_lexeme_id
        JOIN language g ON g.id = l.language_id
        WHERE r.type_id = 'has_component' AND r.target_lexeme_id = ANY(:ids)
          AND (CAST(:ds AS text[]) IS NULL OR r.dataset = ANY(:ds))
        ORDER BY l.id
        LIMIT :limit
    """,
        {"ids": ids, "limit": limit, "ds": ds},
    )


def get_lexeme(conn: Connection, lexeme_id: str) -> dict | None:
    row = (
        conn.execute(
            text(f"""
        SELECT {LEXEME_FIELDS}, l.transliteration, l.phonemic, l.source_status,
               l.source_record_id, l.source_citation, l.source_id, l.dataset
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
    out["source"] = _source(conn, out.pop("source_id"), out.pop("dataset"))
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
    open_only: bool = False,
) -> dict | None:
    if not conn.execute(text("SELECT 1 FROM lexeme WHERE id = :id"), {"id": root}).first():
        return None
    ds = open_datasets(conn, open_only)
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
            JOIN language sl ON sl.id = s.language_id
            JOIN language tl ON tl.id = tg.language_id
            WHERE (r.source_lexeme_id = ANY(:ids) OR r.target_lexeme_id = ANY(:ids))
              AND r.status <> 'rejected'
              AND (CAST(:types AS text[]) IS NULL OR r.type_id = ANY(:types))
              AND (CAST(:ds AS text[]) IS NULL OR r.dataset = ANY(:ds))
            -- When the node cap bites, keep word histories before compounds, and words in
            -- configured languages before dialects and other reference languages.
            ORDER BY CASE r.type_id
                       WHEN 'inherited_form' THEN 0 WHEN 'borrowed_from' THEN 1
                       WHEN 'etymon' THEN 2 WHEN 'cognate' THEN 3
                       WHEN 'calque_or_loan_translation' THEN 4 WHEN 'derived_form' THEN 5
                       WHEN 'related_form' THEN 6 WHEN 'has_component' THEN 8 ELSE 7 END,
                     (sl.is_enabled AND tl.is_enabled) DESC,
                     (sl.role = 'modern' OR tl.role = 'modern') DESC,
                     r.id
        """,
            {"ids": frontier, "types": types, "ds": ds},
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
                WHERE (r.source_lexeme_id = l.id OR r.target_lexeme_id = l.id)
                  AND (CAST(:ds AS text[]) IS NULL OR r.dataset = ANY(:ds))) AS degree
        FROM lexeme l JOIN language g ON g.id = l.language_id WHERE l.id = ANY(:ids)
    """,
        {"ids": list(seen), "ds": ds},
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
               r.source_confidence::text, r.method, r.score, r.notes, r.dataset
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
    dataset = out.pop("dataset")
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
        e["source"] = _source(conn, e.pop("source_id"), dataset)
    out["evidence"] = evidence
    out["citation"] = evidence[0]["citation"] if evidence else None
    return out


def _source(conn: Connection, source_id: str | None, dataset: str | None = None) -> dict | None:
    """A cited source, with the audit decision and citation of the dataset the record was
    imported from (e.g. a CDIAL entry reached through Jambu carries Jambu's citation)."""
    if not source_id:
        return None
    row = (
        conn.execute(
            text("""
        SELECT s.id, s.title, s.reuse_status::text, s.licence_name, s.url,
               coalesce(CAST(:dataset AS text), s.dataset_id) AS dataset_id,
               d.decision::text AS dataset_decision, d.attribution_text AS dataset_citation
        FROM source s
        LEFT JOIN dataset_audit d ON d.id = coalesce(CAST(:dataset AS text), s.dataset_id)
        WHERE s.id = :id
    """),
            {"id": source_id, "dataset": dataset},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def _rows(conn: Connection, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]
