"""Import the Mongolian Wordnet (MonWN, CC BY-SA 4.0) as words and meanings.

``wn-data-mon.tsv`` has the format of the Open Multilingual Wordnet's tab files: a Princeton
WordNet 3.0 synset (``06177450-n``), a field (``mon:lemma``, ``mon:def 0``) and a value. Each
lemma becomes a Halh Mongolian word. Each synset is mapped to the interlingual concept
``ili:<id>`` through the OMW English wordnet's synset IDs (``omw-en-<offset>-<pos>``), so a
Mongolian word meets words of other languages through the shared concept, never through a
drawn link (docs/LINGUISTIC_ENGINE.md). The wordnet states no word-to-word relationships.
"""

import re
import tarfile
from collections import defaultdict
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.importers.headwords import LEXEME_COLS, language_by_iso
from app.models.enums import ReconstructionStatus
from app.services.ids import lexeme_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "monwn"
SOURCE_ID = "monwn"
ISO = "khk"  # the wordnet is of Mongolian; our record for it is Halh Mongolian
_SYNSET = re.compile(r'<Synset id="omw-en-(\d{8}-[nvasr])" ili="(i\d+)"')
_LEMMA = re.compile(r"^(?P<ss>\d{8}-[nvasr])\tmon:lemma\t(?P<w>.+)$")


def ili_by_offset(omw_en: Path) -> dict[str, str]:
    """WordNet 3.0 ``<offset>-<pos>`` -> ILI id, from the OMW English wordnet package."""
    if omw_en.suffix == ".xml":
        xml = omw_en.read_text(encoding="utf-8")
    else:
        with tarfile.open(omw_en, "r:*") as tar:
            member = next(m for m in tar.getmembers() if m.isfile() and m.name.endswith(".xml"))
            xml = tar.extractfile(member).read().decode("utf-8")  # type: ignore[union-attr]
    return dict(_SYNSET.findall(xml))


def read_lemmas(tsv: Path) -> list[tuple[str, str]]:
    out = []
    for line in tsv.read_text(encoding="utf-8").splitlines():
        m = _LEMMA.match(line)
        if m and m["w"].strip():
            out.append((m["ss"], m["w"].strip()))
    return out


def import_monwn(conn: psycopg.Connection, tsv: Path, omw_en: Path, version: str) -> dict:
    ilis = ili_by_offset(omw_en)
    stats = {"lemmas": 0, "unmapped_synsets": 0, "lexemes": 0, "senses": 0}
    by_word: dict[str, set[str]] = defaultdict(set)  # (lemma) -> synsets, one word per lemma
    for synset, word in read_lemmas(tsv):
        stats["lemmas"] += 1
        # WordNet 3.0 marks adjective satellites 's'; OMW English files them under 'a'
        ili = ilis.get(synset) or ilis.get(synset[:-1] + ("a" if synset.endswith("s") else "s"))
        if ili:
            by_word[word].add(f"ili:{ili}")
        else:
            stats["unmapped_synsets"] += 1
            by_word.setdefault(word, set())
    with conn.cursor() as cur:
        lang = language_by_iso(cur, ISO)
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({tsv.name: sha256_file(tsv)}),
                psycopg.types.json.Jsonb(
                    [
                        "mon:lemma lines -> one Halh Mongolian word per distinct lemma",
                        "WordNet 3.0 synset offsets -> ili:<id> through the OMW English wordnet",
                        "Word-concept links only; no word-to-word relationships",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute(
            "DELETE FROM lexeme_concept WHERE lexeme_id IN"
            " (SELECT id FROM lexeme WHERE dataset = %s)",
            (DATASET,),
        )
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))
        used = {c for cs in by_word.values() for c in cs}
        labels: dict[str, str] = {}
        if used:
            cur.execute("SELECT id, label FROM concept WHERE id = ANY(%s)", (sorted(used),))
            labels = dict(cur.fetchall())
        rows, links = [], set()
        for word, concepts in sorted(by_word.items()):
            lid = lexeme_id(DATASET, word)
            gloss = "; ".join(dict.fromkeys(labels[c] for c in sorted(concepts) if c in labels))
            rows.append(
                (
                    lid,
                    lang,
                    word,
                    normalize_form(word),
                    lexeme_search_key(word, lang),
                    word,
                    "source",
                    gloss[:300] or None,
                    form_kind(word).value,
                    ReconstructionStatus.attested.value,
                    None,
                    DATASET,
                    SOURCE_ID,
                    word,
                    "Mongolian Wordnet (MonWN), entry " + word,
                    batch,
                )
            )
            links.update((lid, c, SOURCE_ID) for c in concepts)
        # concepts the OMW import has not created yet (it normally runs first)
        cur.executemany(
            "INSERT INTO concept (id, label, definition, source_id) VALUES (%s, %s, NULL, NULL)"
            " ON CONFLICT (id) DO NOTHING",
            [(c, c) for c in sorted(used)],
        )
        copy_rows(cur, "lexeme", LEXEME_COLS, rows)
        copy_rows(cur, "lexeme_concept", ("lexeme_id", "concept_id", "source_id"), sorted(links))
        stats.update(lexemes=len(rows), senses=len(links), concepts=len(used))
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
