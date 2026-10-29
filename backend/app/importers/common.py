"""Helpers shared by the importers: strict CSV reading, citation parsing, bulk COPY."""

import csv
import hashlib
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

from app.config import settings

csv.field_size_limit(2**31 - 1)


class SchemaMismatch(ValueError):
    """An input file does not have the columns the importer expects."""


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(
        (url or settings.database_url).replace("postgresql+psycopg", "postgresql")
    )


def read_csv(path: Path, required: Sequence[str]) -> Iterator[dict[str, str]]:
    """Stream rows, failing fast if the real header lacks a required column.

    Upstream CLDF metadata can disagree with the files (docs/DATASET_AUDIT.md finding 5),
    so the header in the file is what gets checked.
    """
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise SchemaMismatch(f"{path.name}: missing columns {missing}")
        yield from reader


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Citation:
    key: str
    locator: str | None


_CITATION = re.compile(r"^\s*(?P<key>[^\[\]]+?)\s*(?:\[(?P<loc>.*)\])?\s*$")


def parse_citations(value: str) -> list[Citation]:
    """Split a Jambu ``Source`` value such as ``dunkel2014lipp[p. 179];CDIAL`` into parts."""
    out: list[Citation] = []
    for part in _split_top_level(value or ""):
        m = _CITATION.match(part)
        if m and m.group("key"):
            out.append(Citation(m.group("key"), (m.group("loc") or None)))
    return out


def _split_top_level(value: str) -> Iterable[str]:
    """Split on ';' outside square brackets (locators may contain ';')."""
    depth, start = 0, 0
    for i, ch in enumerate(value):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(depth - 1, 0)
        elif ch == ";" and depth == 0:
            if value[start:i].strip():
                yield value[start:i]
            start = i + 1
    if value[start:].strip():
        yield value[start:]


def copy_rows(cur: psycopg.Cursor, table: str, columns: Sequence[str], rows: Iterable[tuple]):
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
