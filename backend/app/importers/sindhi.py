"""Import Sindhi headwords from the Sindhi Open Lexicon (SindhiLanguage.org; research use).

The master CSV merges several dictionaries. Only entries whose headword is Sindhi are taken
(``language_direction`` = ``sindhi`` or ``sindhi-english``: the Jamia Sindhi Lughat, the
Devanagari/Sindhi-English dictionary and the Mewaram Lughat); the translation dictionaries
with English, Hindi or Arabic headwords would add foreign words with Sindhi glosses, and no
Sindhi word history.

Entries of the same headword (homographs by part of speech, or the same word in two of the
dictionaries) become one word: its gloss is the English definition if a dictionary gives one,
otherwise the first Sindhi definition (tagged ``gloss:sd``), and its tags list the dictionaries
and parts of speech. The bracketed origin notes inside the Sindhi definitions (``[ع.ف]``,
``[سن. ...]``) are abbreviations in running text and are not interpreted.
"""

import csv
import unicodedata
from collections.abc import Iterator
from pathlib import Path

import psycopg

from app.importers.common import sha256_file
from app.importers.headwords import Headword, language_by_iso, write_headwords

DATASET = "sindhi-lexicon"
ISO = "snd"
SINDHI_HEADWORDS = {"sindhi", "sindhi-english"}
ENGLISH_GLOSS_SOURCES = {"Devanagari/Sindhi → English", "Mewaram لغت"}
ATTRIBUTION = "SindhiLanguage.org (prepared and curated by Amar Fayaz Buriro)"


def read_rows(path: Path) -> Iterator[dict[str, str]]:
    csv.field_size_limit(2**31 - 1)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("word") and row.get("lexical_id"):
                yield row


def headwords(rows: Iterator[dict[str, str]], language_id: str) -> list[Headword]:
    words: dict[str, dict] = {}
    for r in rows:
        if (r.get("language_direction") or "").strip().lower() not in SINDHI_HEADWORDS:
            continue
        word = unicodedata.normalize("NFC", r["word"].strip())
        w = words.setdefault(
            word,
            {"id": r["lexical_id"], "native": None, "en": None, "sd": None, "src": [], "pos": []},
        )
        source = (r.get("source_dictionary") or "").strip()
        definition = (r.get("definition") or "").strip()
        if source in ENGLISH_GLOSS_SOURCES:
            w["en"] = w["en"] or definition or None
        else:
            w["sd"] = w["sd"] or definition or None
        variant = (r.get("word_with_airab_or_variant") or "").strip().rstrip(":").strip()
        w["native"] = w["native"] or (variant if variant and variant != word else None)
        if source and source not in w["src"]:
            w["src"].append(source)
        pos = (r.get("part_of_speech") or "").strip()
        if pos and pos not in w["pos"]:
            w["pos"].append(pos)
    out = []
    for word, w in words.items():
        tags = [f"source:{s}" for s in w["src"]] + [f"pos:{p}" for p in w["pos"][:4]]
        gloss = w["en"]
        if not gloss and w["sd"]:
            gloss = w["sd"]
            tags.append("gloss:sd")
        out.append(
            Headword(
                record_id=w["id"],
                language_id=language_id,
                form=word,
                gloss=gloss,
                native_form=w["native"],
                tags=tags,
                citation=f"Sindhi Open Lexicon ({', '.join(w['src'])}), entry {w['id']}; "
                + ATTRIBUTION,
            )
        )
    return out


def import_sindhi(conn: psycopg.Connection, csv_path: Path, version: str) -> dict:
    with conn.cursor() as cur:
        lang = language_by_iso(cur, ISO)
    return write_headwords(
        conn,
        dataset=DATASET,
        source_id=DATASET,
        version=version,
        checksums={csv_path.name: sha256_file(csv_path)},
        transformations=[
            "Only entries with a Sindhi headword (language_direction sindhi or sindhi-english)",
            "One word per distinct headword; English definition preferred as the gloss",
            "Origin notes inside definitions are not interpreted; no relationships",
        ],
        entries=headwords(read_rows(csv_path), lang),
        default_citation="Sindhi Open Lexicon; " + ATTRIBUTION,
    )
