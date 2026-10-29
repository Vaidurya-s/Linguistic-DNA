"""Download the pinned upstream datasets into data/raw/ (git-ignored).

    python scripts/fetch_data.py                       # public datasets (default)
    python scripts/fetch_data.py --group transliteration
    python scripts/fetch_data.py --group restricted    # Jambu: local development only
    python scripts/fetch_data.py --group all

Every input is pinned in data/manifests/downloads.json: git repositories by tag and commit,
files by SHA-256. Existing files that already match are skipped. Uses only the standard
library, so it works straight after cloning.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifests" / "downloads.json"
RAW = ROOT / "data" / "raw"
UA = "LinguisticDNA-fetch/0.1 (https://github.com/Vaidurya-s/Linguistic-DNA)"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_http(entry: dict, raw: Path) -> str:
    dest = raw / entry["dest"]
    if dest.exists() and sha256(dest) == entry["sha256"]:
        return "ok (cached)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(entry["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as fh:
        while chunk := r.read(1 << 20):
            fh.write(chunk)
    got = sha256(tmp)
    if got != entry["sha256"]:
        tmp.unlink()
        raise RuntimeError(f"{entry['id']}: checksum mismatch (got {got})")
    tmp.replace(dest)
    return "downloaded"


def git(*args: str, cwd: Path | None = None) -> str:
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}  # LFS files come via pinned http entries
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, env=env).stdout


def fetch_git(entry: dict, raw: Path) -> str:
    dest = raw / entry["dest"]
    if dest.exists():
        head = git("rev-parse", "HEAD", cwd=dest).strip()
        if head == entry["commit"]:
            return "ok (cached)"
        return f"exists at {head[:7]}, expected {entry['commit'][:7]}"
    if entry.get("full_history"):  # pinned to a commit that is not a tag
        git("clone", "--filter=blob:none", entry["url"], str(dest))
        git("checkout", "--quiet", entry["commit"], cwd=dest)
    else:
        git("clone", "--quiet", "--depth", "1", "--branch", entry["ref"], entry["url"], str(dest))
    head = git("rev-parse", "HEAD", cwd=dest).strip()
    if head != entry["commit"]:
        raise RuntimeError(f"{entry['id']}: got commit {head}, expected {entry['commit']}")
    return "cloned"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=RAW, help="download directory")
    parser.add_argument("--group", default="public",
                        choices=["public", "transliteration", "restricted", "all"])
    args = parser.parse_args()
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["inputs"]
    failed = 0
    for entry in entries:
        if args.group != "all" and entry["group"] != args.group:
            continue
        try:
            fetch = fetch_git if entry["kind"] == "git" else fetch_http
            status = fetch(entry, args.dest)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:  # report all
            status, failed = f"FAILED: {exc}", failed + 1
        print(f"{entry['id']:<22} {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
