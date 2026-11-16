"""Read-side queries: search, lexeme detail, bounded graph, relationship evidence.

Documented relations and computed candidates are returned in separate fields and are never
merged (docs/LINGUISTIC_ENGINE.md §2, §6).
"""

import re
import unicodedata

from sqlalchemy import Connection, text

from app.services.normalize import normalize_form, search_key
from app.services.transliterate import ISO15924, romanize_variants, script_of

# Scholarly reference layers written in Latin but read from Devanagari sources.
EXTRA_SCRIPT_LANGUAGES = {"Deva": ["oia", "pra", "pli", "x-apabhramsha", "x-ashokan-prakrit"]}
MATCH_RANK = {"exact": 0, "native_exact": 1, "transliteration": 2, "loose": 3}

OPEN_DECISIONS = ("APPROVED", "APPROVED WITH CONDITIONS")
RESTRICTED_ROOT_MESSAGE = (
    "This word comes from a dataset that is available for research use only, so it is not shown "
    "in the open-data view. Turn off 'open data only' to see it with its citation."
)


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


def get_lexeme(conn: Connection, lexeme_id: str, open_only: bool = False) -> dict | None:
    """One word with its source and concepts. With open_only, a word of a dataset that is not
    approved for redistribution (research use, blocked or unaudited) is treated as not found."""
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
    if open_only and row["dataset"] not in (open_datasets(conn, True) or []):
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
    root_row = conn.execute(text("SELECT dataset FROM lexeme WHERE id = :id"), {"id": root}).first()
    if not root_row:
        return None
    ds = open_datasets(conn, open_only)
    if ds is not None and root_row[0] not in ds:
        # The word itself is research-use (or blocked) data: an open-only view shows nothing of it.
        return {
            "root_lexeme_id": root,
            "nodes": [],
            "edges": [],
            "truncated": False,
            "warnings": [RESTRICTED_ROOT_MESSAGE],
            "restricted": True,
            "message": RESTRICTED_ROOT_MESSAGE,
        }
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
              -- an open-only view also drops links whose far end is a word of a restricted dataset
              AND (CAST(:ds AS text[]) IS NULL OR (s.dataset = ANY(:ds) AND tg.dataset = ANY(:ds)))
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
          AND (CAST(:ds AS text[]) IS NULL OR l.dataset = ANY(:ds))
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


def get_relationship(conn: Connection, rel_id: str, open_only: bool = False) -> dict | None:
    """One relationship with its evidence. With open_only, a relationship of a dataset that is
    not approved for redistribution, or one that touches a word of such a dataset, is treated as
    not found."""
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
    if open_only:
        ds = open_datasets(conn, True) or []
        ends = conn.execute(
            text("SELECT dataset FROM lexeme WHERE id = ANY(:ids)"),
            {"ids": [row["source"], row["target"]]},
        ).all()
        if row["dataset"] not in ds or any(e[0] not in ds for e in ends):
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


def get_language_profile(conn: Connection, language_id: str) -> dict | None:
    row = (
        conn.execute(
            text("""
        SELECT g.id AS language_id, g.name, f.name AS family_name, g.glottocode
        FROM language g LEFT JOIN language_family f ON f.id = g.family_id WHERE g.id = :id"""),
            {"id": language_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    out = dict(row)
    out["values"] = _rows(
        conn,
        """SELECT dataset, feature_id, feature_name, value, citation FROM language_profile
           WHERE language_id = :id ORDER BY dataset, feature_name, value""",
        {"id": language_id},
    )
    return out


def _rows(conn: Connection, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]


# --- layered retrieval ---------------------------------------------------------
# Three separate blocks, never merged: documented (cited relationships), inferred (chains of
# documented ancestry, layers/inferred.py) and candidate (computed similarity,
# layers/candidate.py).

LAYERS = ("documented", "inferred", "candidate")
_TYPE_RANK = """CASE r.type_id
    WHEN 'inherited_form' THEN 0 WHEN 'borrowed_from' THEN 1 WHEN 'etymon' THEN 2
    WHEN 'cognate' THEN 3 WHEN 'calque_or_loan_translation' THEN 4 WHEN 'derived_form' THEN 5
    WHEN 'related_form' THEN 6 WHEN 'has_component' THEN 8 ELSE 7 END"""


def _summaries(conn: Connection, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    rows = _rows(
        conn,
        f"""SELECT {LEXEME_FIELDS} FROM lexeme l JOIN language g ON g.id = l.language_id
            WHERE l.id = ANY(:ids)""",
        {"ids": ids},
    )
    return {r["id"]: r for r in rows}


def _documented_block(conn: Connection, lexeme_id: str, ds: list[str] | None, limit: int) -> dict:
    fields = re.sub(r"\bl\.", "o.", LEXEME_FIELDS)
    rows = _rows(
        conn,
        f"""
        SELECT r.id AS relationship_id, r.type_id AS type, t.label, t.namespace::text AS namespace,
               r.direction::text AS direction, r.status::text AS status, r.dataset, r.source_id,
               CASE WHEN r.source_lexeme_id = :id THEN 'source' ELSE 'target' END AS role,
               {fields}
        FROM relationship r
        JOIN relationship_type t ON t.id = r.type_id
        JOIN lexeme o ON o.id = CASE WHEN r.source_lexeme_id = :id THEN r.target_lexeme_id
                                     ELSE r.source_lexeme_id END
        JOIN language g ON g.id = o.language_id
        WHERE (r.source_lexeme_id = :id OR r.target_lexeme_id = :id) AND r.status <> 'rejected'
          AND (CAST(:ds AS text[]) IS NULL OR (r.dataset = ANY(:ds) AND o.dataset = ANY(:ds)))
        ORDER BY {_TYPE_RANK}, g.name, o.form, r.id
        LIMIT :lim
        """,
        {"id": lexeme_id, "ds": ds, "lim": limit + 1},
    )
    truncated = len(rows) > limit
    rows = rows[:limit]
    ev: dict[str, list[dict]] = {}
    dataset_of = {r["relationship_id"]: r["dataset"] for r in rows}
    if rows:
        for e in _rows(
            conn,
            """SELECT relationship_id, citation, locator, evidence_note AS note, source_id
               FROM evidence WHERE relationship_id = ANY(:ids) ORDER BY id""",
            {"ids": [r["relationship_id"] for r in rows]},
        ):
            rel = e.pop("relationship_id")
            e["source"] = _source(conn, e.pop("source_id"), dataset_of[rel])
            ev.setdefault(rel, []).append(e)
    own = {"relationship_id", "type", "label", "namespace", "direction", "status", "dataset",
           "source_id", "role"}  # fmt: skip
    items = []
    for r in rows:
        items.append(
            {
                **{k: r[k] for k in own},
                "other": {k: v for k, v in r.items() if k not in own},
                "evidence": ev.get(r["relationship_id"], []),
            }
        )
    return {"count": len(items), "truncated": truncated, "items": items}


_UP = ("inherited_form", "etymon", "derived_form")


def _inferred_partners(pg, lexeme_id: str, ds: list[str] | None, cap: int = 150) -> list[str]:
    """Words that may share an ancestor with `lexeme_id`: other descendants of the ancestors it
    reaches by documented ancestry (up to three steps). Only a way to propose partners: whether a
    chain really exists is decided by the inferred layer's own function."""
    ds_sql = " AND r.dataset = ANY(%(ds)s)" if ds is not None else ""
    args = {"ds": ds, "up": list(_UP)}
    ancestors: set[str] = set()
    frontier = [lexeme_id]
    for _ in range(3):
        if not frontier:
            break
        rows = pg.execute(
            "SELECT r.target_lexeme_id FROM relationship r WHERE r.source_lexeme_id = ANY(%(f)s)"
            " AND r.type_id = ANY(%(up)s) AND r.direction = 'directed'"
            + ds_sql
            + " UNION SELECT r.source_lexeme_id FROM relationship r"
            " WHERE r.target_lexeme_id = ANY(%(f)s) AND r.type_id = 'reconstructed_ancestor_of'"
            + ds_sql,
            {**args, "f": frontier},
        ).fetchall()
        frontier = [r[0] for r in rows if r[0] not in ancestors and r[0] != lexeme_id]
        ancestors.update(frontier)
    if not ancestors:
        return []
    rows = pg.execute(
        "SELECT r.source_lexeme_id FROM relationship r WHERE r.target_lexeme_id = ANY(%(a)s)"
        " AND r.type_id = ANY(%(up)s) AND r.direction = 'directed'"
        + ds_sql
        + " UNION SELECT r.target_lexeme_id FROM relationship r"
        " WHERE r.source_lexeme_id = ANY(%(a)s) AND r.type_id = 'reconstructed_ancestor_of'"
        + ds_sql,
        {**args, "a": sorted(ancestors)},
    ).fetchall()
    direct = {
        r[0]
        for r in pg.execute(
            "SELECT target_lexeme_id FROM relationship WHERE source_lexeme_id = %s"
            " UNION SELECT source_lexeme_id FROM relationship WHERE target_lexeme_id = %s",
            (lexeme_id, lexeme_id),
        ).fetchall()
    }
    partners = sorted({r[0] for r in rows} - direct - {lexeme_id})
    return partners[:cap]


def _inferred_items(pg, lexeme_id: str, ds: list[str] | None, limit: int) -> list[dict]:
    """Inferred relatives from layers/inferred.py: [{'chain': InferredChain, 'other': id}]."""
    from app.layers import inferred as inf

    walker = inf.AncestryWalker(pg, max_depth=6, datasets=ds)
    found = []
    for partner in _inferred_partners(pg, lexeme_id, ds):
        chain, _ = walker.chain(lexeme_id, partner)
        if chain is not None:
            found.append({"chain": chain, "other": partner})
    found.sort(key=lambda f: (f["chain"].depth, f["other"]))
    return found[: limit + 1]


def _candidate_items(
    pg, lexeme_id: str, ds: list[str] | None, limit: int, gate: str = "gloss"
) -> list:
    """Candidates from layers/candidate.py, best score first."""
    from app.layers import candidate as cand

    return cand.candidates_for(pg, lexeme_id, k=limit + 1, gate=gate, datasets=ds)


def _chain_steps(conn: Connection, chain_ids: list[str]) -> list[dict]:
    if not chain_ids:
        return []
    rows = {
        r["id"]: r
        for r in _rows(
            conn,
            """SELECT r.id, r.type_id AS type, r.dataset,
                      (SELECT e.citation FROM evidence e WHERE e.relationship_id = r.id
                       ORDER BY e.id LIMIT 1) AS citation,
                      (SELECT e.locator FROM evidence e WHERE e.relationship_id = r.id
                       ORDER BY e.id LIMIT 1) AS locator
               FROM relationship r WHERE r.id = ANY(:ids)""",
            {"ids": chain_ids},
        )
    }
    return [
        {
            "relationship_id": rid,
            "type": rows[rid]["type"] if rid in rows else "unknown",
            "dataset": rows[rid]["dataset"] if rid in rows else "unknown",
            "citation": rows[rid]["citation"] if rid in rows else None,
            "locator": rows[rid]["locator"] if rid in rows else None,
        }
        for rid in chain_ids
    ]


def related_layers(
    conn: Connection,
    lexeme_id: str,
    layers: list[str] | None = None,
    open_only: bool = False,
    limit: int = 20,
    candidate_gate: str = "gloss",
) -> dict | None:
    """Documented, inferred and candidate relatives of one word, in three separate blocks.

    A layer that fails (its tables are not built, or its module is missing) is reported in the
    block's status and in `warnings`; the other layers are still returned. None when the word is
    unknown, or hidden by open_only."""
    if get_lexeme(conn, lexeme_id, open_only) is None:
        return None
    wanted = [x for x in LAYERS if x in (layers or LAYERS)]
    ds = open_datasets(conn, open_only)
    out: dict = {
        "lexeme_id": lexeme_id,
        "open_only": open_only,
        "layers_requested": wanted,
        "documented": None,
        "inferred": None,
        "candidate": None,
        "warnings": [],
    }
    if "documented" in wanted:
        out["documented"] = _documented_block(conn, lexeme_id, ds, limit)
    pg = conn.connection.driver_connection

    if "inferred" in wanted:
        block = {"count": 0, "truncated": False, "items": [], "status": "ok"}
        try:
            with conn.begin_nested():
                found = _inferred_items(pg, lexeme_id, ds, limit)
            block["truncated"] = len(found) > limit
            found = found[:limit]
            lex = _summaries(
                conn,
                sorted(
                    {f["other"] for f in found}
                    | {f["chain"].ancestor_id for f in found if f["chain"].ancestor_id}
                ),
            )
            for f in found:
                c = f["chain"]
                if f["other"] not in lex:
                    continue
                block["items"].append(
                    {
                        "other": lex[f["other"]],
                        "kind": c.kind,
                        "depth": c.depth,
                        "ancestor": lex.get(c.ancestor_id) if c.ancestor_id else None,
                        "chain_relationship_ids": list(c.relationship_ids),
                        "chain": _chain_steps(conn, list(c.relationship_ids)),
                        "datasets": list(c.datasets),
                        "capped": bool(c.capped),
                        "rule_version": c.rule_version,
                    }
                )
            block["count"] = len(block["items"])
        except Exception as exc:  # a layer that is missing must not take the answer down
            block["status"] = "unavailable"
            out["warnings"].append(f"inferred layer unavailable: {type(exc).__name__}")
        out["inferred"] = block

    if "candidate" in wanted:
        block = {"count": 0, "truncated": False, "items": [], "status": "ok"}
        try:
            with conn.begin_nested():
                found = _candidate_items(pg, lexeme_id, ds, limit, candidate_gate)
            block["truncated"] = len(found) > limit
            found = found[:limit]
            lex = _summaries(conn, [c.lexeme_id for c in found])
            for c in found:
                if c.lexeme_id not in lex:
                    continue
                block["items"].append(
                    {
                        "other": lex[c.lexeme_id],
                        "method": c.method,
                        "score": float(c.score),
                        "gate": c.gate,
                        "gate_via": c.gate_via,
                        "calibrated_precision": c.calibrated_precision,
                        "calibrated": bool(c.calibrated),
                        "stratum": c.stratum,
                        "n_sources": c.n_sources,
                        "params": dict(c.params),
                    }
                )
            block["count"] = len(block["items"])
        except Exception as exc:
            block["status"] = "unavailable"
            out["warnings"].append(f"candidate layer unavailable: {type(exc).__name__}")
        out["candidate"] = block
    return out


# --- extra search techniques ---------------------------------------------------
# Each returns the same match shape as /search with its own match_type, so a reader sees how a
# word was found. None of them creates a relationship.


def _matches(
    conn: Connection,
    scored: list[tuple[str, float | None, str | None]],
    match_type: str,
    ds: list[str] | None,
    limit: int,
) -> list[dict]:
    """Search matches (id, score, via) -> match dicts in the given order."""
    ids = [s[0] for s in scored]
    if not ids:
        return []
    rows = {
        r["id"]: r
        for r in _rows(
            conn,
            f"""SELECT {LEXEME_FIELDS},
                   (SELECT count(*) FROM relationship r
                    WHERE (r.source_lexeme_id = l.id OR r.target_lexeme_id = l.id)
                      AND (CAST(:ds AS text[]) IS NULL OR r.dataset = ANY(:ds)))
                       AS relationship_count, 1 AS duplicate_count
                FROM lexeme l JOIN language g ON g.id = l.language_id
                WHERE l.id = ANY(:ids) AND (CAST(:ds AS text[]) IS NULL OR l.dataset = ANY(:ds))""",
            {"ids": ids, "ds": ds},
        )
    }
    out = []
    for lex_id, score, via in scored:
        if lex_id in rows and len(out) < limit:
            out.append({**rows[lex_id], "match_type": match_type, "via": via, "score": score})
    return out


def _technique_response(q: str, technique: str, matches: list[dict], warnings: list[str]) -> dict:
    if not matches:
        warnings.append("No word matches under this technique.")
    return {
        "query": q,
        "normalized_query": normalize_form(q),
        "technique": technique,
        "matches": matches,
        "warnings": warnings,
    }


def fuzzy_search(
    conn: Connection,
    q: str,
    language_id: str,
    limit: int = 10,
    threshold: float = 0.4,
    open_only: bool = False,
) -> dict:
    """Trigram-similar spellings inside ONE language (pg_trgm on the loose search key).

    Restricting by language keeps the candidate set to that language's words; the result is a
    list of similar spellings, not of relatives."""
    key = search_key(q)
    ds = open_datasets(conn, open_only)
    warnings: list[str] = []
    scored: list[tuple[str, float | None, str | None]] = []
    if len(key) < 3:
        warnings.append("Fuzzy search needs at least three letters.")
    else:
        conn.execute(
            text("SELECT set_config('pg_trgm.similarity_threshold', :t, true)"),
            {"t": str(threshold)},
        )
        rows = conn.execute(
            text("""
            SELECT l.id, similarity(l.search_key, :key) AS score FROM lexeme l
            WHERE l.language_id = :lang AND l.search_key % :key AND l.form_kind = 'word'
              AND (CAST(:ds AS text[]) IS NULL OR l.dataset = ANY(:ds))
            ORDER BY score DESC, l.id LIMIT :lim"""),
            {"key": key, "lang": language_id, "ds": ds, "lim": limit * 3},
        ).all()
        scored = [(r[0], float(r[1]), None) for r in rows]
    return _technique_response(q, "fuzzy", _matches(conn, scored, "fuzzy", ds, limit), warnings)


def concept_gated_search(
    conn: Connection,
    q: str,
    concept_ids: list[str],
    language_ids: list[str] | None = None,
    limit: int = 10,
    open_only: bool = False,
) -> dict:
    """Words that share one of the given concepts (lexeme_concept), ranked by trigram similarity
    of their spelling to the query. The concept is the gate: a similar spelling with another
    meaning is never returned."""
    key = search_key(q)
    ds = open_datasets(conn, open_only)
    rows = conn.execute(
        text("""
        SELECT l.id, similarity(l.search_key, :key) AS score
        FROM lexeme_concept lc JOIN lexeme l ON l.id = lc.lexeme_id
        JOIN language g ON g.id = l.language_id
        WHERE lc.concept_id = ANY(:cids) AND g.is_enabled AND l.form_kind = 'word'
          AND (CAST(:langs AS text[]) IS NULL OR l.language_id = ANY(:langs))
          AND (CAST(:ds AS text[]) IS NULL OR l.dataset = ANY(:ds))
        ORDER BY score DESC, l.id LIMIT :lim"""),
        {"key": key, "cids": concept_ids, "langs": language_ids, "ds": ds, "lim": limit * 3},
    ).all()
    scored = [(r[0], float(r[1]), None) for r in rows]
    return _technique_response(
        q, "concept_gated", _matches(conn, scored, "concept_gated", ds, limit), []
    )


def key_search(
    conn: Connection, q: str, language_id: str, limit: int = 10, open_only: bool = False
) -> dict:
    """Words of one language that spell the query the same way under the word-identity keys
    (layers/keys.py): the native spelling, then its case/diacritic fold, then its romanisation.
    `via` names the key that matched, so a reader can see HOW two spellings were matched."""
    from app.layers import keys

    pg = conn.connection.driver_connection
    ds = open_datasets(conn, open_only)
    warnings: list[str] = []
    try:
        with conn.begin_nested():
            found = keys.resolve_form(pg, language_id, q)
    except Exception as exc:  # the key table is not built: fall back to the native spelling
        warnings.append(f"word keys unavailable ({type(exc).__name__}); native spelling only")
        with conn.begin_nested():
            found = keys.resolve_form(pg, language_id, q, kinds=("native",))
    scored = [(lex_id, None, kind) for lex_id, kind in found]
    kinds = {lex_id: kind for lex_id, kind in found}
    matches = _matches(conn, scored, "key", ds, limit)
    for m in matches:
        m["via"] = kinds[m["id"]]
    return _technique_response(q, "keys", matches, warnings)


def sound_search(
    conn: Connection,
    q: str,
    level: str = "cons",
    language_ids: list[str] | None = None,
    exclude_language: str | None = None,
    limit: int = 10,
    open_only: bool = False,
) -> dict:
    """Words in the query's sound-class bucket (layers/sound_key.py), ranked by the alignment
    score of layers/candidate.py when it exists. Computed: a likely relative, not a record."""
    from app.layers import sound_key

    pg = conn.connection.driver_connection
    ds = open_datasets(conn, open_only)
    warnings: list[str] = []
    key = sound_key.skey(q)
    if not key:
        return _technique_response(q, "sound", [], ["The query has no consonant to key on."])
    with conn.begin_nested():
        ids = sound_key.block(
            pg, key, level, language_ids, exclude_language, datasets=ds, limit=3000
        )
    if len(ids) >= 3000:
        warnings.append("The sound bucket is large and was cut at 3000 words.")
    scored: list[tuple[str, float | None, str | None]] = []
    if ids:
        try:
            from app.layers import candidate as cand

            qtext = cand.scoring_text(q, None, search_key(q))
            rows = conn.execute(
                text(
                    "SELECT id, form, transliteration, search_key FROM lexeme WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            ).all()
            scored = [
                (r[0], cand.score("blend", qtext, cand.scoring_text(r[1], r[2], r[3])), key)
                for r in rows
            ]
        except ImportError:
            scored = [(i, None, key) for i in ids]
        scored.sort(key=lambda s: (-(s[1] or 0.0), s[0]))
    return _technique_response(
        q, "sound", _matches(conn, scored[: limit * 3], "sound_block", ds, limit), warnings
    )
