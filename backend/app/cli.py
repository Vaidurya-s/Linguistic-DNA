"""Data pipeline commands.

python -m app.cli load-manifest
python -m app.cli import-jambu --cldf data/raw/jambu/cldf --version <commit>
python -m app.cli import-glottolog --cldf data/raw/glottolog-cldf/cldf
python -m app.cli import-concepticon --data data/raw/concepticon-data
python -m app.cli import-wordlist --cldf data/raw/lsi/cldf --dataset lsi --version v1.1
python -m app.cli validate [--public-seed | --research]
python -m app.cli coverage
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from app.config import REPO_ROOT
from app.importers.cdsl import import_cdsl_mw
from app.importers.cldf_structure import import_cldf_structure
from app.importers.cldf_wordlist import import_cldf_wordlist
from app.importers.common import connect
from app.importers.concepticon import import_concepticon
from app.importers.dcs import import_dcs
from app.importers.dpd import import_dpd
from app.importers.glottolog import import_glottolog
from app.importers.jambu import JambuImporter
from app.importers.manifest import load_manifest, prune_orphan_sources
from app.importers.omw import import_omw
from app.importers.starling import import_starling, name_languages_from_glottolog
from app.importers.transliteration import import_aksharantar, import_dakshina
from app.importers.wikidata_lexemes import fetch_language_names, import_wikidata_lexemes
from app.importers.wiktionary import import_wiktionary, wiktionary_code_map
from app.pipeline.benchmark import run_benchmark
from app.pipeline.coverage import coverage, to_markdown
from app.pipeline.languages import (
    MACROLANGUAGE_MEMBER,
    Glottolog,
    canonical_targets,
    canonicalize_languages,
    enable_searchable,
    import_glottolog_languages,
    iso_tables,
    refresh_language_stats,
)
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
    j.add_argument(
        "--all-languages",
        action="store_true",
        help="import every form, filing unconfigured languages as disabled reference languages",
    )
    mw = sub.add_parser("import-cdsl-mw")
    mw.add_argument("--file", type=Path, required=True, help="csl-orig v02/mw/mw.txt")
    mw.add_argument("--version", default="unknown")
    dp = sub.add_parser("import-dpd")
    dp.add_argument("--db", type=Path, required=True, help="dpd.db unpacked from the release")
    dp.add_argument("--archive", type=Path, help="the release dpd.db.tar.xz, for its checksum")
    dp.add_argument("--version", default="unknown")
    st = sub.add_parser("import-starling", help="StarLing etymological databases (research use)")
    st.add_argument("--dir", type=Path, required=True, help="folder of the *.exe archives")
    st.add_argument("--version", default="unknown")
    st.add_argument("--glottolog", type=Path, help="glottolog-cldf/cldf: resolve other field names")
    st.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "reports" / "starling_unmapped.csv",
        help="where to list field names and abbreviations that no language was found for",
    )
    lb = sub.add_parser("import-lexibank", help="every dataset in data/manifests/lexibank.tsv")
    lb.add_argument("--list", type=Path, default=REPO_ROOT / "data/manifests/lexibank.tsv")
    lb.add_argument("--raw", type=Path, default=REPO_ROOT / "data/raw/lexibank")
    lb.add_argument("--only", help="comma-separated dataset ids")
    ow = sub.add_parser("import-omw", help="WN-LMF wordnets (Open Multilingual Wordnet)")
    ow.add_argument("--dir", type=Path, required=True, help="directory of omw-*-2.0.tar.xz")
    ow.add_argument("--glottolog", type=Path, required=True)
    ow.add_argument("--iso", type=Path, required=True)
    ow.add_argument("--version", default="unknown")
    st = sub.add_parser("import-structure", help="CLDF StructureDataset -> language profiles")
    st.add_argument("--cldf", type=Path, required=True)
    st.add_argument("--dataset", required=True, help="dataset_id from dataset_audit.csv")
    dc = sub.add_parser("import-dcs")
    dc.add_argument("--dictionary", type=Path, required=True)
    dc.add_argument("--version", default="unknown")
    wk = sub.add_parser("import-wiktionary")
    wk.add_argument("--dir", type=Path, required=True, help="directory of wiktextract *.jsonl[.gz]")
    wk.add_argument("--version", default="unknown")
    wk.add_argument(
        "--reference-codes",
        default="",
        help="comma-separated Wiktionary codes of ancestor languages whose entries to import",
    )
    wk.add_argument(
        "--etymology-only-codes",
        default="",
        help="comma-separated codes whose entries are imported only when they have etymologies",
    )
    wk.add_argument(
        "--all-languages",
        action="store_true",
        help="import entries in every language (the whole dump; about 10 million entries)",
    )
    c = sub.add_parser("import-concepticon")
    c.add_argument("--data", type=Path, required=True)
    w = sub.add_parser("import-wordlist")
    w.add_argument("--cldf", type=Path, required=True)
    w.add_argument(
        "--all-languages",
        action="store_true",
        help="also keep doculects of unconfigured languages, as disabled gl-<glottocode>",
    )
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
    wd.add_argument(
        "--lemma-codes",
        default="",
        help="also import these lemma languages (ISO codes, e.g. ru,uk), resolved via Glottolog;"
        " 'all' for every language",
    )
    wd.add_argument("--glottolog", type=Path, help="glottolog-cldf/cldf, for --lemma-codes")
    wd.add_argument("--iso", type=Path, help="SIL iso-639-3.tab, for --lemma-codes")
    dk = sub.add_parser("import-dakshina")
    dk.add_argument("--tar", type=Path, required=True)
    ak = sub.add_parser("import-aksharantar")
    ak.add_argument("--dir", type=Path, required=True)
    g = sub.add_parser("import-glottolog")
    g.add_argument("--cldf", type=Path, required=True)
    v = sub.add_parser("validate")
    v.add_argument("--public-seed", action="store_true")
    v.add_argument("--research", action="store_true", help="checks for the research database")
    gl = sub.add_parser(
        "refresh-languages",
        help="all Glottolog languages, one record per language, statistics, searchable flags",
    )
    gl.add_argument("--glottolog", type=Path, help="glottolog-cldf/cldf (omit: statistics only)")
    gl.add_argument("--iso", type=Path, help="SIL iso-639-3.tab")
    gl.add_argument("--min-words", type=int, default=200)
    sub.add_parser("coverage")
    sub.add_parser("benchmark")
    sub.add_parser("rekey-search", help="recompute lexeme.search_key after a rule change")
    sub.add_parser("db-size", help="database size, and words and links per dataset")
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
            result = JambuImporter(
                conn, args.cldf, args.forms, args.version, all_languages=args.all_languages
            ).run()
            result["orphan_sources_removed"] = prune_orphan_sources(conn)
        elif args.cmd == "import-cdsl-mw":
            load_manifest(conn)
            result = import_cdsl_mw(conn, args.file, args.version)
        elif args.cmd == "import-dpd":
            load_manifest(conn)
            result = import_dpd(conn, args.db, args.archive, args.version)
        elif args.cmd == "import-starling":
            load_manifest(conn)
            archives = sorted(p for p in args.dir.iterdir() if p.suffix.lower() in (".exe", ".zip"))
            names = (
                name_languages_from_glottolog(conn, Glottolog(args.glottolog))
                if args.glottolog
                else {}
            )
            result = import_starling(
                conn, archives, args.version, wiktionary_code_map(), names, args.report
            )
        elif args.cmd == "import-lexibank":
            load_manifest(conn)
            conn.commit()
            only = set(args.only.split(",")) if args.only else None
            result = {"imported": {}, "failed": {}}
            with args.list.open(encoding="utf-8", newline="") as fh:
                datasets = list(csv.DictReader(fh, delimiter="\t"))
            for d in datasets:
                if only and d["id"] not in only:
                    continue
                cldf = args.raw / d["id"] / "cldf"
                try:
                    stats = import_cldf_wordlist(
                        conn, cldf, d["id"], f"{d['tag']} ({d['commit'][:7]})", all_languages=True
                    )
                    conn.commit()  # one dataset at a time: a failure keeps the others
                    result["imported"][d["id"]] = {
                        k: stats[k]
                        for k in ("lexemes", "cognate_relationships", "borrowings")
                        if k in stats
                    }
                    print(d["id"], result["imported"][d["id"]], flush=True)
                except Exception as exc:  # report and continue with the next dataset
                    conn.rollback()
                    result["failed"][d["id"]] = f"{type(exc).__name__}: {exc}"[:300]
                    print(d["id"], "FAILED", result["failed"][d["id"]], flush=True)
        elif args.cmd == "import-omw":
            load_manifest(conn)
            part1, _ = iso_tables(args.iso)
            result = import_omw(
                conn,
                sorted(args.dir.glob("*.tar.xz")),
                Glottolog(args.glottolog),
                part1,
                args.version,
            )
        elif args.cmd == "import-structure":
            load_manifest(conn)
            result = import_cldf_structure(conn, args.cldf, args.dataset)
        elif args.cmd == "import-dcs":
            load_manifest(conn)
            result = import_dcs(conn, args.dictionary, args.version)
        elif args.cmd == "import-wiktionary":
            load_manifest(conn)
            files = sorted(args.dir.glob("*.jsonl")) + sorted(args.dir.glob("*.jsonl.gz"))
            result = import_wiktionary(
                conn,
                files,
                args.version,
                wiktionary_code_map(),
                reference_codes=[c for c in args.reference_codes.split(",") if c],
                etymology_only_codes=[c for c in args.etymology_only_codes.split(",") if c],
                all_languages=args.all_languages,
            )
        elif args.cmd == "import-concepticon":
            load_manifest(conn)
            result = import_concepticon(conn, args.data)
        elif args.cmd == "import-wordlist":
            load_manifest(conn)
            result = import_cldf_wordlist(
                conn,
                args.cldf,
                args.dataset,
                args.version,
                args.transcription,
                all_languages=args.all_languages,
            )
        elif args.cmd == "import-wikidata":
            load_manifest(conn)
            extra = {}
            if args.lemma_codes:
                glottolog = Glottolog(args.glottolog)
                part1, _ = iso_tables(args.iso)
                targets = canonical_targets(conn)
                every = args.lemma_codes == "all"
                part3 = sorted(glottolog.by_iso)
                wanted_codes = [*part1, *part3] if every else args.lemma_codes.split(",")
                for code in wanted_codes:
                    iso = part1.get(code, code)
                    iso = MACROLANGUAGE_MEMBER.get(iso, iso)
                    lang = targets.get(glottolog.language_of(glottolog.by_iso.get(iso)) or "")
                    if lang:
                        extra[code] = lang
                    elif not every:
                        print(f"lemma code {code}: no language record", file=sys.stderr)
            every = args.lemma_codes == "all"
            result = import_wikidata_lexemes(conn, args.dump, args.version, extra, every)
            if args.fetch_language_names and result["unknown_language_qids"]:
                fetch_language_names(result["unknown_language_qids"])
                result = import_wikidata_lexemes(conn, args.dump, args.version, extra, every)
            result["unknown_language_qids"] = len(result["unknown_language_qids"])
        elif args.cmd == "db-size":
            result = {
                "database": conn.execute(
                    "SELECT pg_size_pretty(pg_database_size(current_database()))"
                ).fetchone()[0],
                "words": dict(
                    conn.execute(
                        "SELECT dataset, count(*) FROM lexeme GROUP BY 1 ORDER BY 2 DESC"
                    ).fetchall()
                ),
                "links": dict(
                    conn.execute(
                        "SELECT dataset, count(*) FROM relationship GROUP BY 1 ORDER BY 2 DESC"
                    ).fetchall()
                ),
                "searchable_languages": conn.execute(
                    "SELECT count(*) FROM language WHERE is_enabled"
                ).fetchone()[0],
            }
        elif args.cmd == "rekey-search":
            result = rekey_search(conn)
        elif args.cmd == "build-public-seed":
            result = build_public_seed(conn)
        elif args.cmd == "load-public-seed":
            result = load_public_seed(conn)
            result["language_stats"] = refresh_language_stats(conn)
        elif args.cmd == "ensure-seed":
            empty = conn.execute("SELECT NOT EXISTS (SELECT 1 FROM lexeme)").fetchone()[0]
            result = load_public_seed(conn) if empty else {"skipped": "database already has data"}
            if empty:
                result["language_stats"] = refresh_language_stats(conn)
        elif args.cmd == "import-dakshina":
            load_manifest(conn)
            result = import_dakshina(conn, args.tar)
        elif args.cmd == "import-aksharantar":
            load_manifest(conn)
            result = import_aksharantar(conn, args.dir)
        elif args.cmd == "import-glottolog":
            load_manifest(conn)
            result = import_glottolog(conn, args.cldf)
        elif args.cmd == "refresh-languages":
            load_manifest(conn)  # sources such as glottolog, even on an empty database
            result = {}
            if args.glottolog:
                glottolog = Glottolog(args.glottolog)
                part1, _ = iso_tables(args.iso) if args.iso else ({}, set())
                result.update(import_glottolog_languages(conn, glottolog))
                result.update(canonicalize_languages(conn, glottolog, part1))
            result["language_stats"] = refresh_language_stats(conn)
            if args.glottolog:
                result["searchable_glottolog_languages"] = enable_searchable(conn, args.min_words)
                result["language_stats"] = refresh_language_stats(conn)
                # planner statistics go stale after moving many rows between languages
                conn.execute("ANALYZE lexeme")
                conn.execute("ANALYZE language")
        elif args.cmd == "validate":
            result = run_checks(conn, public_seed=args.public_seed, research=args.research)
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
