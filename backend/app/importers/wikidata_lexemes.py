"""Import Wikidata Lexemes (CC0) for the configured languages from a JSON dump.

Two passes over the dump: (1) lexemes in a target language, collecting the lexemes their
"derived from" (P5191) and "combines lexemes" (P5238) statements point to; (2) those referenced
lexemes in any language. Only lemmas and English glosses are taken; inflected forms are not.

P5191 does not say whether a word was inherited or borrowed, so it maps to the ``etymon``
type. Every edge cites its Wikidata statement ID; statements without a reference say so.
"""

import bz2
import csv
import gzip
import json
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import psycopg

from app.config import REPO_ROOT
from app.importers.common import copy_rows, sha256_file
from app.models.enums import Direction, ReconstructionStatus, RelationshipStatus
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "wikidata-lexemes"
SOURCE_ID = "wikidata-lexemes"
LANGUAGE_NAMES = REPO_ROOT / "data" / "config" / "wikidata_languages.csv"

# Hindi lexemes are mostly filed under Hindustani (Q11051); keep those with a Hindi lemma.
HINDUSTANI = ("Q11051", "hin", "hi")


def target_languages() -> dict[str, tuple[str, str | None]]:
    """Wikidata language item -> (configured language id, lemma code to require or None)."""
    from app.importers.jambu import load_languages

    out = {
        t.wikidata_qid: (t.id, t.wikidata_lemma or None) for t in load_languages() if t.wikidata_qid
    }
    out[HINDUSTANI[0]] = (HINDUSTANI[1], HINDUSTANI[2])
    return out


PROPERTY_LABELS = {"P5191": "derived from lexeme", "P5238": "combines lexemes"}

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
    "dataset",
    "source_id",
    "source_record_id",
    "source_citation",
    "import_batch_id",
)
REL_COLS = (
    "id",
    "source_lexeme_id",
    "target_lexeme_id",
    "type_id",
    "direction",
    "status",
    "source_id",
    "source_record_id",
    "original_label",
    "rank",
    "notes",
    "dataset",
    "import_batch_id",
)
EVIDENCE_COLS = ("relationship_id", "source_id", "citation", "locator", "evidence_note")


def iter_dump(path: Path) -> Iterator[dict]:
    opener = bz2.open if path.suffix == ".bz2" else gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip().rstrip(",")
            if line.startswith("{"):
                yield json.loads(line)


def lemma_of(entity: dict, prefer: str | None) -> str | None:
    lemmas = entity.get("lemmas", {})
    if prefer and prefer in lemmas:
        return lemmas[prefer]["value"]
    if prefer:  # e.g. Hindustani lexemes with only an Urdu lemma are not Hindi records
        return None
    return next(iter(lemmas.values()))["value"] if lemmas else None


def english_gloss(entity: dict) -> str | None:
    glosses = [
        s["glosses"]["en"]["value"]
        for s in entity.get("senses", [])
        if "en" in s.get("glosses", {})
    ]
    return "; ".join(dict.fromkeys(glosses[:3])) or None


def statement_targets(entity: dict, prop: str) -> Iterator[tuple[str, dict]]:
    for st in entity.get("claims", {}).get(prop, []):
        snak = st.get("mainsnak", {})
        if snak.get("snaktype") == "value":
            yield snak["datavalue"]["value"]["id"], st


def reference_note(statement: dict) -> tuple[str | None, str]:
    """('stated in Q…, p. …', note) from a statement's first reference, if any."""
    refs = statement.get("references") or []
    if not refs:
        return None, "Wikidata statement has no reference."
    snaks = refs[0].get("snaks", {})
    parts = []
    for prop, label in (("P248", "stated in"), ("P304", "p."), ("P854", "URL")):
        for s in snaks.get(prop, []):
            v = s.get("datavalue", {}).get("value")
            parts.append(f"{label} {v['id'] if isinstance(v, dict) else v}")
    return (", ".join(parts) or None), "Reference recorded on the Wikidata statement."


def load_language_names(path: Path = LANGUAGE_NAMES) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["qid"]: r["name"] for r in csv.DictReader(fh)}


def import_wikidata_lexemes(
    conn: psycopg.Connection,
    dump: Path,
    version: str,
    lemma_code_languages: dict[str, str] | None = None,
) -> dict:
    """lemma_code_languages: further languages to import, keyed by lemma spelling code
    (e.g. "ru" -> the Russian record). A language item not in the config is taken on when
    its lexemes' lemmas use one of these codes; the mapping is learned from the dump, so no
    network lookup is needed."""
    names = load_language_names()
    targets_cfg = target_languages()
    extra = lemma_code_languages or {}
    stats: dict[str, int] = {}
    targets: dict[str, dict] = {}
    wanted: set[str] = set()
    for e in iter_dump(dump):
        qid = e.get("language")
        if qid not in targets_cfg and extra:
            code = next((c for c in e.get("lemmas", {}) if c in extra), None)
            if code:
                targets_cfg[qid] = (extra[code], code)
                stats[f"language_from_lemma_code:{code}={qid}"] = 1
        lang = targets_cfg.get(qid)
        if not lang or not lemma_of(e, lang[1]):
            continue
        targets[e["id"]] = e
        for prop in ("P5191", "P5238"):
            wanted.update(t for t, _ in statement_targets(e, prop))
    referenced = {}
    for e in iter_dump(dump):
        if e["id"] in wanted and e["id"] not in targets:
            referenced[e["id"]] = e

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({dump.name: sha256_file(dump)}),
                psycopg.types.json.Jsonb(
                    [
                        "Lexemes in configured languages (by Wikidata language item), lemma only",
                        "Target languages from data/config/languages.csv (wikidata_qid column)",
                        "Hindustani (Q11051) lexemes kept only when they have a Hindi lemma",
                        "Lexemes referenced by P5191/P5238 imported from any language",
                        "P5191 derived from -> etymon; P5238 combines lexemes -> has_component",
                        "Gloss: up to three English sense glosses",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))

        unknown_langs = set()
        lexemes = []
        for lid, e in {**referenced, **targets}.items():
            target = targets_cfg.get(e.get("language"))
            if lid in targets:
                language_id, prefer = target
            else:
                qid = e.get("language", "Q0")
                language_id = target[0] if target else f"wd-{qid.lower()}"
                prefer = target[1] if target else None
                if not target:
                    unknown_langs.add(qid)
            lemma = lemma_of(e, prefer) or lemma_of(e, None)
            if not lemma:
                continue
            lang_name = names.get(e.get("language", ""), "")
            proto = lang_name.startswith("Proto-")
            status = (
                ReconstructionStatus.reconstructed
                if proto or lemma.startswith("*")
                else ReconstructionStatus.attested
                if lid in targets
                else ReconstructionStatus.unknown
            )
            lexemes.append(
                (
                    lexeme_id(DATASET, lid),
                    language_id,
                    lemma,
                    normalize_form(lemma),
                    lexeme_search_key(lemma, language_id),
                    lemma,
                    "source",
                    english_gloss(e),
                    form_kind(lemma, bool(e.get("claims", {}).get("P5238"))).value,
                    status.value,
                    DATASET,
                    SOURCE_ID,
                    lid,
                    f"Wikidata {lid}",
                    batch,
                )
            )
        for qid in sorted(unknown_langs):
            name = names.get(qid, f"Wikidata language {qid}")
            cur.execute(
                "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
                " VALUES (%s, %s, 'other', %s, false, %s) ON CONFLICT (id) DO UPDATE SET"
                " name = EXCLUDED.name, is_proto = EXCLUDED.is_proto",
                (
                    f"wd-{qid.lower()}",
                    name,
                    name.startswith("Proto-"),
                    psycopg.types.json.Jsonb({"wikidata": qid}),
                ),
            )
            cur.execute(
                "INSERT INTO language_alias (language_id, scheme, value) VALUES (%s, 'wikidata',"
                " %s) ON CONFLICT DO NOTHING",
                (f"wd-{qid.lower()}", qid),
            )
        copy_rows(cur, "lexeme", LEXEME_COLS, lexemes)
        present = {row[12] for row in lexemes}

        rels, evidence = {}, []
        for lid, e in targets.items():
            if lid not in present:
                continue
            for prop, type_id in (("P5191", "etymon"), ("P5238", "has_component")):
                for rank, (other, st) in enumerate(statement_targets(e, prop), start=1):
                    if other not in present or other == lid:
                        stats[f"{prop}_target_missing"] = stats.get(f"{prop}_target_missing", 0) + 1
                        continue
                    rid = relationship_id(DATASET, st["id"])
                    locator, note = reference_note(st)
                    rels[rid] = (
                        rid,
                        lexeme_id(DATASET, lid),
                        lexeme_id(DATASET, other),
                        type_id,
                        Direction.directed.value,
                        RelationshipStatus.documented.value,
                        SOURCE_ID,
                        st["id"],
                        f"{prop} {PROPERTY_LABELS[prop]}",
                        rank,
                        None if st.get("references") else "unreferenced",
                        DATASET,
                        batch,
                    )
                    evidence.append((rid, SOURCE_ID, f"Wikidata {st['id']}", locator, note))
                    stats[type_id] = stats.get(type_id, 0) + 1
        copy_rows(cur, "relationship", REL_COLS, rels.values())
        copy_rows(cur, "evidence", EVIDENCE_COLS, evidence)
        stats.update(
            target_lexemes=len(targets),
            referenced_lexemes=len(referenced),
            lexemes=len(lexemes),
            relationships=len(rels),
            unnamed_languages=sum(1 for q in unknown_langs if q not in names),
        )
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats, "unknown_language_qids": sorted(unknown_langs)}


def fetch_language_names(qids: list[str], path: Path = LANGUAGE_NAMES) -> int:
    """One-off helper: look up English labels for language items and add them to the
    committed CSV, so later imports need no network access."""
    names = load_language_names(path)
    todo = [q for q in qids if q not in names]
    for i in range(0, len(todo), 50):
        url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(todo[i : i + 50]),
                "props": "labels",
                "languages": "en",
                "format": "json",
            }
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "LinguisticDNA/0.1 (https://github.com/Vaidurya-s/Linguistic-DNA)"
            },
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            for qid, ent in json.load(r).get("entities", {}).items():
                label = ent.get("labels", {}).get("en", {}).get("value")
                if label:
                    names[qid] = label
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["qid", "name"])
        w.writerows(sorted(names.items(), key=lambda kv: int(kv[0][1:])))
    return len(names)
