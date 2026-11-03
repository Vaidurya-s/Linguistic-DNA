"""Shared writer for plain headword lexicons: one word per headword, with a short gloss.

Dictionary-style datasets (Sindhi Open Lexicon, Kurdish lexicons, Calfa's Armenian dictionary)
state words and meanings but no word-to-word relationships, so only lexemes are written. Every
word cites its dictionary. A dataset is replaced as a whole on re-import, and IDs are
deterministic, so a repeat import keeps them.
"""

import html
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import psycopg

from app.importers.common import copy_rows
from app.models.enums import ReconstructionStatus
from app.services.ids import lexeme_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

LEXEME_COLS = (
    "id",
    "language_id",
    "form",
    "normalized_form",
    "search_key",
    "native_form",
    "native_form_origin",
    "gloss",
    "form_kind",
    "reconstruction_status",
    "tags",
    "dataset",
    "source_id",
    "source_record_id",
    "source_citation",
    "import_batch_id",
)
GLOSS_MAX = 300
# An HTML tag starts with a letter right after "<" or "</": a bare "<" in running text
# ("< Persian", "a < b") is not markup and stays.
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")


@dataclass
class Headword:
    record_id: str  # the dataset's own identifier for the entry; unique within the dataset
    language_id: str
    form: str
    gloss: str | None = None
    native_form: str | None = None  # the same word with diacritics or in its source spelling
    tags: list[str] = field(default_factory=list)
    citation: str | None = None


def language_by_iso(cur: psycopg.Cursor, iso: str) -> str:
    """The Glottolog-based language record for an ISO 639-3 code (``refresh-languages`` makes
    one per Glottolog language)."""
    cur.execute(
        "SELECT id FROM language WHERE iso_code = %s AND id LIKE 'gl-%%' ORDER BY id LIMIT 1",
        (iso,),
    )
    row = cur.fetchone()
    if not row:
        raise LookupError(
            f"no language record for ISO 639-3 '{iso}': run `make refresh-languages` first"
        )
    return row[0]


def clip(text: str | None, limit: int = GLOSS_MAX) -> str | None:
    """A short gloss: markup removed, whitespace collapsed, cut at a word boundary. Definitions
    are not copied at length; the full entry stays at its source."""
    if not text:
        return None
    text = " ".join(html.unescape(_TAG.sub("", text)).split())
    if len(text) <= limit:
        return text or None
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;: ") + "…"


def write_headwords(
    conn: psycopg.Connection,
    *,
    dataset: str,
    source_id: str,
    version: str,
    checksums: dict[str, str],
    transformations: Sequence[str],
    entries: Iterable[Headword],
    default_citation: str,
) -> dict:
    stats = {"lexemes": 0, "skipped_empty": 0, "skipped_duplicate": 0}
    rows, seen = [], set()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                dataset,
                version,
                psycopg.types.json.Jsonb(checksums),
                psycopg.types.json.Jsonb(list(transformations)),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (dataset,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (dataset,))
        for e in entries:
            form = (e.form or "").strip()
            if not form or not any(ch.isalpha() for ch in form):
                stats["skipped_empty"] += 1
                continue
            if e.record_id in seen:
                stats["skipped_duplicate"] += 1
                continue
            seen.add(e.record_id)
            native = (e.native_form or "").strip()
            rows.append(
                (
                    lexeme_id(dataset, e.record_id),
                    e.language_id,
                    form,
                    normalize_form(form),
                    lexeme_search_key(form, e.language_id),
                    native if native and native != form else form,
                    "source",
                    clip(e.gloss),
                    form_kind(form).value,
                    # a headword the dictionary stars is a hypothetical form, never attested
                    (
                        ReconstructionStatus.reconstructed
                        if form.startswith("*")
                        else ReconstructionStatus.attested
                    ).value,
                    e.tags or None,
                    dataset,
                    source_id,
                    e.record_id,
                    e.citation or default_citation,
                    batch,
                )
            )
        copy_rows(cur, "lexeme", LEXEME_COLS, rows)
        stats["lexemes"] = len(rows)
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
