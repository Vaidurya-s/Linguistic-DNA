"""Data pipeline commands.

python -m app.cli load-manifest
python -m app.cli import-jambu --cldf data/raw/jambu/cldf --version <commit>
python -m app.cli import-glottolog --cldf data/raw/glottolog-cldf/cldf
python -m app.cli import-concepticon --data data/raw/concepticon-data
python -m app.cli import-wordlist --cldf data/raw/lsi/cldf --dataset lsi --version v1.1
python -m app.cli validate [--public-seed]
python -m app.cli coverage
"""

import argparse
import json
import sys
from pathlib import Path

from app.config import REPO_ROOT
from app.importers.cldf_wordlist import import_cldf_wordlist
from app.importers.common import connect
from app.importers.concepticon import import_concepticon
from app.importers.glottolog import import_glottolog
from app.importers.jambu import JambuImporter
from app.importers.manifest import load_manifest, prune_orphan_sources
from app.importers.transliteration import import_aksharantar, import_dakshina
from app.importers.wikidata_lexemes import fetch_language_names, import_wikidata_lexemes
from app.pipeline.benchmark import run_benchmark
from app.pipeline.coverage import coverage, to_markdown
from app.pipeline.public_seed import build_public_seed, load_public_seed
from app.pipeline.validate import run_checks

REPORTS = REPO_ROOT / "reports"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    parser.add_argument("--database-url")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("load-manifest")
    j = sub.add_parser("import-jambu")
    j.add_argument("--cldf", type=Path, required=True)
    j.add_argument("--forms", type=Path, help="forms.csv if not inside --cldf (LFS object)")
    j.add_argument("--version", default="unknown")
    c = sub.add_parser("import-concepticon")
    c.add_argument("--data", type=Path, required=True)
    w = sub.add_parser("import-wordlist")
    w.add_argument("--cldf", type=Path, required=True)
    w.add_argument("--dataset", required=True, help="dataset_id from dataset_audit.csv")
    w.add_argument("--version", required=True)
    w.add_argument("--transcription", help="phonetic code the forms use, e.g. ASJPcode")
    wd = sub.add_parser("import-wikidata")
    wd.add_argument("--dump", type=Path, required=True)
    wd.add_argument("--version", required=True)
    wd.add_argument(
        "--fetch-language-names",
        action="store_true",
        help="look up names of unfamiliar language items once (needs network)",
    )
    dk = sub.add_parser("import-dakshina")
    dk.add_argument("--tar", type=Path, required=True)
    ak = sub.add_parser("import-aksharantar")
    ak.add_argument("--dir", type=Path, required=True)
    g = sub.add_parser("import-glottolog")
    g.add_argument("--cldf", type=Path, required=True)
    v = sub.add_parser("validate")
    v.add_argument("--public-seed", action="store_true")
    sub.add_parser("coverage")
    sub.add_parser("benchmark")
    sub.add_parser("rekey-search", help="recompute lexeme.search_key after a rule change")
    sub.add_parser("build-public-seed")
    sub.add_parser("load-public-seed")
    sub.add_parser("ensure-seed", help="load the public seed if the database has no lexemes")
    args = parser.parse_args(argv)
    if args.cmd == "benchmark":
        return _benchmark(args.database_url)

    with connect(args.database_url) as conn:
        if args.cmd == "load-manifest":
            result = {"sources": load_manifest(conn)}
        elif args.cmd == "import-jambu":
            load_manifest(conn)
            result = JambuImporter(conn, args.cldf, args.forms, args.version).run()
            result["orphan_sources_removed"] = prune_orphan_sources(conn)
        elif args.cmd == "import-concepticon":
            load_manifest(conn)
            result = import_concepticon(conn, args.data)
        elif args.cmd == "import-wordlist":
            load_manifest(conn)
            result = import_cldf_wordlist(
                conn, args.cldf, args.dataset, args.version, args.transcription
            )
        elif args.cmd == "import-wikidata":
            load_manifest(conn)
            result = import_wikidata_lexemes(conn, args.dump, args.version)
            if args.fetch_language_names and result["unknown_language_qids"]:
                fetch_language_names(result["unknown_language_qids"])
                result = import_wikidata_lexemes(conn, args.dump, args.version)
            result["unknown_language_qids"] = len(result["unknown_language_qids"])
        elif args.cmd == "rekey-search":
            result = rekey_search(conn)
        elif args.cmd == "build-public-seed":
            result = build_public_seed(conn)
        elif args.cmd == "load-public-seed":
            result = load_public_seed(conn)
        elif args.cmd == "ensure-seed":
            empty = conn.execute("SELECT NOT EXISTS (SELECT 1 FROM lexeme)").fetchone()[0]
            result = load_public_seed(conn) if empty else {"skipped": "database already has data"}
        elif args.cmd == "import-dakshina":
            load_manifest(conn)
            result = import_dakshina(conn, args.tar)
        elif args.cmd == "import-aksharantar":
            load_manifest(conn)
            result = import_aksharantar(conn, args.dir)
        elif args.cmd == "import-glottolog":
            load_manifest(conn)
            result = import_glottolog(conn, args.cldf)
        elif args.cmd == "validate":
            result = run_checks(conn, public_seed=args.public_seed)
            _write("validation.json", json.dumps(result, indent=2))
            for c in result["checks"]:
                flag = "ok  " if c["passed"] else "FAIL"
                print(f"{flag} [{c['severity']}] {c['name']}: {c['violations']}")
            return 0 if result["passed"] else 1
        else:
            rows = coverage(conn)
            _write("coverage.json", json.dumps(rows, indent=2))
            _write("coverage.md", to_markdown(rows))
            print(to_markdown(rows))
            return 0
    print(json.dumps(result, indent=2, default=str))
    return 0


def _benchmark(url: str | None) -> int:
    from app.db.session import make_engine

    engine = make_engine(url.replace("postgresql://", "postgresql+psycopg://") if url else None)
    with engine.begin() as conn:
        result = run_benchmark(conn)
    _write("benchmark.json", json.dumps(result, indent=2, ensure_ascii=False))
    label = "PROVISIONAL (cases not yet reviewed by a person)" if result["provisional"] else ""
    print(f"{result['reviewed_cases']}/{result['total_cases']} cases reviewed {label}")
    for cat, s in result["by_category"].items():
        print(f"  {cat:<28} {s['passed']}/{s['total']}")
    for cat, cases in result["cases"].items():
        for c in cases:
            if not c["passed"]:
                print(f"  FAIL {c['case_id']} ({cat}): {c['detail']}")
    return 0


def rekey_search(conn) -> dict:
    """Recompute every lexeme's loose search key with the current rules."""
    from app.services.normalize import lexeme_search_key

    with conn.cursor() as cur:
        cur.execute("SELECT id, form, language_id, search_key FROM lexeme")
        changes = [
            (lexeme_search_key(form, lang), lid)
            for lid, form, lang, old in cur.fetchall()
            if lexeme_search_key(form, lang) != old
        ]
        cur.executemany("UPDATE lexeme SET search_key = %s WHERE id = %s", changes)
    return {"updated": len(changes)}


def _write(name: str, text: str) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
