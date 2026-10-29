"""Data pipeline commands.

python -m app.cli load-manifest
python -m app.cli import-jambu --cldf data/raw/jambu/cldf --version <commit>
python -m app.cli import-glottolog --cldf data/raw/glottolog-cldf/cldf
python -m app.cli validate [--public-seed]
python -m app.cli coverage
"""

import argparse
import json
import sys
from pathlib import Path

from app.config import REPO_ROOT
from app.importers.common import connect
from app.importers.glottolog import import_glottolog
from app.importers.jambu import JambuImporter
from app.importers.manifest import load_manifest
from app.pipeline.coverage import coverage, to_markdown
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
    g = sub.add_parser("import-glottolog")
    g.add_argument("--cldf", type=Path, required=True)
    v = sub.add_parser("validate")
    v.add_argument("--public-seed", action="store_true")
    sub.add_parser("coverage")
    args = parser.parse_args(argv)

    with connect(args.database_url) as conn:
        if args.cmd == "load-manifest":
            result = {"sources": load_manifest(conn)}
        elif args.cmd == "import-jambu":
            load_manifest(conn)
            result = JambuImporter(conn, args.cldf, args.forms, args.version).run()
        elif args.cmd == "import-glottolog":
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


def _write(name: str, text: str) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
