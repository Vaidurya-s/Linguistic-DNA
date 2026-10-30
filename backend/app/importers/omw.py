"""Import wordnets in WN-LMF (Open Multilingual Wordnet 2.0 packages) as words and meanings.

Every lexicon's entries become words in its language (resolved by ISO code through
Glottolog to one language record). Every sense links the word to an interlingual concept,
``ili:<ILI id>``, so words with the same meaning in any language meet through the shared
concept: meaning links are never stored pairwise and never drawn as word history. English
definitions and lemmas label the concepts. Each wordnet is its own source, with its own
licence and citation, so every word cites the wordnet it comes from.
"""

import tarfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.models.enums import ReconstructionStatus
from app.pipeline.languages import MACROLANGUAGE_MEMBER, Glottolog, canonical_targets
from app.services.ids import lexeme_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "omw"
LEXEME_COLS = (
    "id",
    "language_id",
    "form",
    "normalized_form",
    "search_key",
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


def lmf_documents(path: Path) -> Iterator[tuple[str, bytes]]:
    """(member name, XML bytes) for the WN-LMF files in a .tar.xz package or a bare .xml."""
    if path.suffix == ".xml":
        yield path.name, path.read_bytes()
        return
    with tarfile.open(path, "r:*") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name.endswith(".xml"):
                fh = tar.extractfile(m)
                if fh:
                    yield m.name, fh.read()


def parse_lexicon(xml: bytes) -> dict:
    root = ET.fromstring(xml)
    lex = root.find("Lexicon")
    if lex is None:
        raise ValueError("no <Lexicon> element")
    synset_ili, definitions = {}, {}
    for ss in lex.iter("Synset"):
        if ss.get("ili") and ss.get("ili") != "in":
            synset_ili[ss.get("id")] = ss.get("ili")
            d = ss.find("Definition")
            if d is not None and d.text:
                definitions[ss.get("ili")] = d.text.strip()
    entries = []
    for e in lex.iter("LexicalEntry"):
        lemma = e.find("Lemma")
        if lemma is None or not (lemma.get("writtenForm") or "").strip():
            continue
        ilis = [
            synset_ili[s.get("synset")] for s in e.iter("Sense") if s.get("synset") in synset_ili
        ]
        entries.append(
            (e.get("id"), lemma.get("writtenForm").strip(), lemma.get("partOfSpeech"), ilis)
        )
    return {
        "id": lex.get("id"),
        "label": lex.get("label") or lex.get("id"),
        "language": lex.get("language"),
        "license": lex.get("license"),
        "version": lex.get("version"),
        "citation": (lex.get("citation") or "").strip() or None,
        "url": lex.get("url"),
        "entries": entries,
        "definitions": definitions,
    }


def import_omw(
    conn: psycopg.Connection,
    packages: list[Path],
    glottolog: Glottolog,
    part1: dict[str, str],
    version: str,
) -> dict:
    targets = canonical_targets(conn)

    def language_for(code: str) -> str | None:
        iso = part1.get(code, code)
        iso = MACROLANGUAGE_MEMBER.get(iso, iso)
        gc = glottolog.language_of(glottolog.by_iso.get(iso))
        return targets.get(gc or "")

    lexicons = []
    for pkg in packages:
        for _name, xml in lmf_documents(pkg):
            lexicons.append((pkg, parse_lexicon(xml)))
    # English first: its definitions and lemmas label the shared concepts
    lexicons.sort(key=lambda x: x[1]["language"] != "en")

    stats: dict[str, int] = {"lexicons": 0, "unmapped_lexicons": 0}
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({p.name: sha256_file(p) for p in packages}),
                psycopg.types.json.Jsonb(
                    [
                        "WN-LMF lexicons: one word per lexical entry, in its language",
                        "Senses -> lexeme_concept with interlingual concepts ili:<id>",
                        "Concept labels: English lemmas; definitions: English synsets",
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

        concept_label: dict[str, str] = {}
        concept_def: dict[str, str] = {}
        lexemes, links = [], set()
        for _pkg, lx in lexicons:
            lang = language_for(lx["language"] or "")
            if not lang:
                stats["unmapped_lexicons"] += 1
                continue
            stats["lexicons"] += 1
            source = f"omw-{lx['id']}"
            cur.execute(
                "INSERT INTO source (id, title, url, version_or_release, licence_name,"
                " reuse_status, attribution_text, dataset_id) VALUES (%s, %s, %s, %s, %s,"
                " 'attribution_required', %s, %s) ON CONFLICT (id) DO UPDATE SET"
                " title = EXCLUDED.title, licence_name = EXCLUDED.licence_name,"
                " attribution_text = EXCLUDED.attribution_text",
                (
                    source,
                    lx["label"],
                    lx["url"],
                    lx["version"],
                    lx["license"],
                    lx["citation"] or f"{lx['label']} (via the Open Multilingual Wordnet)",
                    DATASET,
                ),
            )
            if lx["language"] == "en":
                concept_def.update(lx["definitions"])
            for entry_id, form, pos, ilis in lx["entries"]:
                if lx["language"] == "en":
                    for ili in ilis:
                        concept_label.setdefault(ili, form)
                lid = lexeme_id(DATASET, f"{lx['id']}:{entry_id}")
                lexemes.append(
                    (
                        lid,
                        lang,
                        form,
                        normalize_form(form),
                        lexeme_search_key(form, lang),
                        "; ".join(
                            dict.fromkeys(concept_label[i] for i in ilis[:3] if i in concept_label)
                        )
                        or None,
                        form_kind(form).value,
                        ReconstructionStatus.attested.value,
                        [f"pos:{pos}"] if pos else None,
                        DATASET,
                        source,
                        entry_id,
                        f"{lx['label']}, entry {entry_id}",
                        batch,
                    )
                )
                links.update((lid, f"ili:{ili}", source) for ili in ilis)
        used = {c for _, c, _ in links}
        cur.executemany(
            "INSERT INTO concept (id, label, definition, source_id) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label,"
            " definition = EXCLUDED.definition",
            [
                (c, concept_label.get(c[4:], c), concept_def.get(c[4:]), "omw-omw-en")
                if concept_label.get(c[4:])
                else (c, c, concept_def.get(c[4:]), None)
                for c in sorted(used)
            ],
        )
        copy_rows(cur, "lexeme", LEXEME_COLS, lexemes)
        copy_rows(cur, "lexeme_concept", ("lexeme_id", "concept_id", "source_id"), sorted(links))
        stats.update(lexemes=len(lexemes), senses=len(links), concepts=len(used))
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
