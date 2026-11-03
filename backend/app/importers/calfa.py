"""Import Calfa's Classical Armenian dictionary (CC BY-NC 4.0, research use).

``definitions/en-definitions01.tsv`` (common words) and ``definitions_proper/`` (proper nouns)
have one row per headword: the Armenian title, the genitive ending, then up to six part-of-speech
and English definition pairs. Each headword becomes a Classical Armenian word with its first
definition as a short gloss. Headwords are stored lower-case, as Classical Armenian words are
written elsewhere (Wiktionary); a proper noun keeps its capital.

The repository's etymology file is Ačaṙean's dictionary as unstructured Armenian prose that its
maintainers describe as AI-processed. It is not read: reading relationships out of free text would
be guesswork, and every relationship here needs a stated source.
"""

import csv
import re
from pathlib import Path

import psycopg

from app.importers.common import sha256_file
from app.importers.headwords import Headword, language_by_iso, write_headwords

DATASET = "calfa-armenian"
ISO = "xcl"
_MARKUP = re.compile(r"<[^>]+>")
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
FILES = (
    ("definitions/en-definitions01.tsv", False),
    ("definitions_proper/en-definitions01.tsv", True),
)


def clean_title(title: str) -> str:
    """The headword without Calfa's letter markup or a trailing romanisation in brackets."""
    return _PAREN.sub("", _MARKUP.sub("", title)).strip()


def read_headwords(path: Path, proper: bool, language_id: str) -> list[Headword]:
    csv.field_size_limit(2**31 - 1)
    out, seen = [], {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            title = clean_title(row.get("Title") or "")
            definition = (row.get("Definition_1") or "").strip()
            if not title:
                continue
            form = title if proper else title.lower()
            # homographs are separate entries: number them in file order, which is stable
            key = f"{'p' if proper else 'c'}:{form}"
            seen[key] = seen.get(key, 0) + 1
            record = key if seen[key] == 1 else f"{key}#{seen[key]}"
            pos = (row.get("POS_1") or "").strip()
            out.append(
                Headword(
                    record_id=record,
                    language_id=language_id,
                    form=form,
                    gloss=definition or None,
                    tags=[f"pos:{pos}"] if pos else [],
                    citation=f"Calfa, Classical Armenian dictionary, headword {title}",
                )
            )
    return out


def import_calfa(conn: psycopg.Connection, directory: Path, version: str) -> dict:
    entries: list[Headword] = []
    checksums = {}
    with conn.cursor() as cur:
        lang = language_by_iso(cur, ISO)
    for name, proper in FILES:
        path = directory / name
        if path.exists():
            checksums[name] = sha256_file(path)
            entries += read_headwords(path, proper, lang)
    return write_headwords(
        conn,
        dataset=DATASET,
        source_id=DATASET,
        version=version,
        checksums=checksums,
        transformations=[
            "definitions TSV: one Classical Armenian word per headword; first English definition",
            "Headwords lower-cased (proper nouns keep their capital); letter markup removed",
            "The AI-processed etymology prose is not read; no relationships",
        ],
        entries=entries,
        default_citation="Calfa, Classical Armenian dictionary (https://dictionary.calfa.fr/)",
    )
