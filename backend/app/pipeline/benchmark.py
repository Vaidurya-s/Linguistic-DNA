"""Run data/benchmark/relationships.csv against the database (EVALUATION_AND_TESTING.md).

Metrics are reported per category and never merged into one score. Until a person has
reviewed a case (review_status = reviewed), its result is provisional.
"""

from collections import defaultdict
from pathlib import Path

from sqlalchemy import Connection, text

from app.config import REPO_ROOT
from app.importers.common import read_csv
from app.services.retrieval import search

BENCHMARK = REPO_ROOT / "data" / "benchmark" / "relationships.csv"
COLUMNS = (
    "case_id",
    "category",
    "query",
    "query_language",
    "target_form",
    "target_language",
    "expected",
    "source_ref",
    "restricted_source",
    "split",
    "reviewer",
    "review_status",
)


def _ids(conn: Connection, form: str, language: str) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            text("SELECT id FROM lexeme WHERE normalized_form = :f AND language_id = :l"),
            {"f": form, "l": language},
        )
    ]


def _direct_types(conn: Connection, a: list[str], b: list[str]) -> set[str]:
    if not a or not b:
        return set()
    rows = conn.execute(
        text("""
        SELECT DISTINCT type_id FROM relationship
        WHERE (source_lexeme_id = ANY(:a) AND target_lexeme_id = ANY(:b))
           OR (source_lexeme_id = ANY(:b) AND target_lexeme_id = ANY(:a))"""),
        {"a": a, "b": b},
    )
    return {r[0] for r in rows}


def evaluate_case(conn: Connection, case: dict) -> tuple[bool, str]:
    cat, expected = case["category"], case["expected"]
    if cat in ("exact_match", "native_script_match", "transliteration_alias", "ambiguous_form"):
        res = search(conn, case["query"], case["query_language"] or None, 50)
        forms = {(m["form"].strip(), m["language_id"], m["match_type"]) for m in res["matches"]}
        if cat == "ambiguous_form":
            n = len({m["language_id"] for m in res["matches"]})
            return n >= int(expected), f"{n} languages matched"
        hit = any(
            f == case["target_form"]
            and lang == case["target_language"]
            and (expected == "any" or kind == expected)
            for f, lang, kind in forms
        )
        return hit, f"{len(forms)} matches"
    if cat == "stem_not_word":
        res = search(conn, case["query"], case["query_language"] or None, 50)
        as_word = any(m["form"] == case["target_form"] for m in res["matches"])
        as_related = any(
            m["form"] == case["target_form"] and m["form_kind"] == expected
            for m in res["related_forms"]
        )
        return as_related and not as_word, f"word={as_word} related={as_related}"
    if cat == "unknown_query":
        res = search(conn, case["query"], None, 10)
        return not res["matches"] and not res["related_forms"], f"{len(res['matches'])} matches"
    if cat == "reconstructed":
        rows = conn.execute(
            text(
                "SELECT reconstruction_status::text FROM lexeme"
                " WHERE normalized_form = :f AND language_id = :l"
            ),
            {"f": case["query"], "l": case["query_language"]},
        ).all()
        return bool(rows) and all(r[0] == expected for r in rows), f"{[r[0] for r in rows]}"
    a = _ids(conn, case["query"], case["query_language"])
    b = _ids(conn, case["target_form"], case["target_language"])
    if not a or not b:
        return False, "form not in database"
    types = _direct_types(conn, a, b)
    if expected == "none":
        return not types, f"links found: {sorted(types)}" if types else "no direct link"
    return expected in types, f"link types: {sorted(types)}"


def run_benchmark(conn: Connection, path: Path = BENCHMARK) -> dict:
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for case in read_csv(path, COLUMNS):
        ok, detail = evaluate_case(conn, case)
        by_cat[case["category"]].append(
            {
                "case_id": case["case_id"],
                "passed": ok,
                "detail": detail,
                "review": case["review_status"],
            }
        )
    summary = {
        cat: {"passed": sum(r["passed"] for r in rs), "total": len(rs)}
        for cat, rs in sorted(by_cat.items())
    }
    reviewed = sum(r["review"] == "reviewed" for rs in by_cat.values() for r in rs)
    total = sum(len(rs) for rs in by_cat.values())
    return {
        "provisional": reviewed < total,
        "reviewed_cases": reviewed,
        "total_cases": total,
        "by_category": summary,
        "cases": {c: rs for c, rs in sorted(by_cat.items())},
    }
