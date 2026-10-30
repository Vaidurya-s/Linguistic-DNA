"""Import a Lexibank-style CLDF wordlist (LSI, ASJP, and cognate-coded sets such as IE-CoR).

Doculects whose glottocode maps to a configured language are kept; each doculect becomes a
``variety`` of that language. With ``all_languages``, other doculects are kept too, under a
disabled language ``gl-<glottocode>`` shared by every CLDF dataset, ready to be enabled by
adding the glottocode to the config. Forms are linked to Concepticon concepts.

When the dataset has a cognate table (``cognates.csv``), forms in the same cognate set are
linked by undirected ``cognate`` relationships citing the dataset and the set, as long as at
least one of the two forms is in a configured language. A ``Loan`` flag is kept as a tag
because it names no donor.
"""

from collections import defaultdict
from itertools import combinations
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, read_csv, sha256_file
from app.importers.concepticon import ensure_concept
from app.importers.jambu import (
    LANGUAGE_CONFIG,
    TargetLanguage,
    has_native_script,
    load_languages,
)
from app.models.enums import Direction, ReconstructionStatus, RelationshipStatus
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form, search_key

FORM_COLUMNS = ("ID", "Language_ID", "Parameter_ID", "Value", "Form", "Source", "Loan")
LANGUAGE_COLUMNS = ("ID", "Name", "Glottocode")
COGNATE_COLUMNS = ("Form_ID", "Cognateset_ID")
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
    "notes",
    "dataset",
    "import_batch_id",
)
EVIDENCE_COLS = ("relationship_id", "source_id", "citation", "locator", "evidence_note")
PARAMETER_COLUMNS = ("ID", "Name", "Concepticon_ID", "Concepticon_Gloss")

LEXEME_COLS = (
    "id",
    "language_id",
    "variety_id",
    "form",
    "normalized_form",
    "search_key",
    "native_form",
    "native_form_origin",
    "transliteration",
    "phonemic",
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


def by_glottocode(targets: list[TargetLanguage]) -> dict[str, TargetLanguage]:
    """Glottocode -> configured language, preferring real languages over reference layers."""
    out: dict[str, TargetLanguage] = {}
    for t in targets:
        for code in t.glottocodes:
            if code not in out or out[code].role == "reference":
                out[code] = t
    return out


def import_cldf_wordlist(
    conn: psycopg.Connection,
    cldf_dir: Path,
    dataset: str,
    version: str,
    transcription: str | None = None,
    language_config: Path = LANGUAGE_CONFIG,
    all_languages: bool = False,
) -> dict:
    """Import one dataset. ``transcription`` names a phonetic code the forms are written in
    (e.g. ASJPcode); such forms are stored as transcriptions, not as orthography."""
    targets = by_glottocode(load_languages(language_config))
    files = [
        f
        for f in ("forms.csv", "languages.csv", "parameters.csv", "cognates.csv")
        if (cldf_dir / f).exists()
    ]
    checksums = {name: sha256_file(cldf_dir / name) for name in files}
    doculects: dict[str, tuple[str, str]] = {}  # doculect id -> (language id, name)
    configured: set[str] = {t.id for t in targets.values()}
    other_languages: dict[str, str] = {}  # gl-<glottocode> -> a doculect name
    for r in read_csv(cldf_dir / "languages.csv", LANGUAGE_COLUMNS):
        if r["Glottocode"] in targets:
            doculects[r["ID"]] = (targets[r["Glottocode"]].id, r["Name"])
        elif all_languages and r["Glottocode"]:
            lid = f"gl-{r['Glottocode']}"
            doculects[r["ID"]] = (lid, r["Name"])
            other_languages.setdefault(lid, r["Name"])
    params = {r["ID"]: r for r in read_csv(cldf_dir / "parameters.csv", PARAMETER_COLUMNS)}
    stats: dict[str, int] = {"doculects": len(doculects)}

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                dataset,
                version,
                psycopg.types.json.Jsonb(checksums),
                psycopg.types.json.Jsonb(
                    [
                        "Doculects mapped to configured languages by glottocode; others skipped",
                        "Each doculect stored as a variety of its language",
                        "Forms linked to Concepticon concepts via parameters.Concepticon_ID",
                        "Loan flag kept as tag 'loan' (no donor given, so no relationship)",
                        f"Transcription scheme: {transcription or 'source romanisation'}",
                    ]
                ),
            ),
        )
        batch_id = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (dataset,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (dataset,))
        cur.execute("DELETE FROM variety WHERE id LIKE %s", (f"{dataset}:%",))
        for lid, name in other_languages.items():
            cur.execute(
                "INSERT INTO language (id, name, glottocode, role, is_proto, is_enabled,"
                " metadata_json) VALUES (%s, %s, %s, 'other', false, false, %s)"
                " ON CONFLICT (id) DO NOTHING",
                (lid, name, lid[3:], psycopg.types.json.Jsonb({"from_dataset": dataset})),
            )
        for doc_id, (lang_id, name) in doculects.items():
            cur.execute(
                "INSERT INTO variety (id, language_id, name, source_id) VALUES (%s, %s, %s, %s)",
                (f"{dataset}:{doc_id}", lang_id, name, dataset),
            )

        rows, links = [], []
        concept_of: dict[str, str | None] = {}
        for p in params.values():
            concept_of[p["ID"]] = (
                ensure_concept(cur, p["Concepticon_ID"], p["Concepticon_Gloss"])
                if p["Concepticon_ID"]
                else None
            )
        for f in read_csv(cldf_dir / "forms.csv", FORM_COLUMNS):
            doc = doculects.get(f["Language_ID"])
            if not doc:
                continue
            lang_id, _ = doc
            param = params.get(f["Parameter_ID"], {})
            raw, native, phonemic = spellings(f, transcription)
            lid = lexeme_id(dataset, f["ID"])
            page = param.get("PageNumber")
            citation = f"{f['Source'] or dataset}" + (f"[p. {page}]" if page else "")
            rows.append(
                (
                    lid,
                    lang_id,
                    f"{dataset}:{f['Language_ID']}",
                    raw,
                    normalize_form(raw),
                    search_key(raw) if transcription else lexeme_search_key(raw, lang_id),
                    native,
                    "source" if native else None,
                    None if transcription or raw == native else raw,
                    raw if transcription else phonemic,
                    param.get("Name"),
                    form_kind(raw).value,
                    (
                        ReconstructionStatus.reconstructed
                        if raw.startswith("*")
                        else ReconstructionStatus.attested
                    ).value,
                    ["loan"] if f["Loan"].lower() == "true" else None,
                    dataset,
                    dataset,
                    f["ID"],
                    citation,
                    batch_id,
                )
            )
            if concept_of.get(f["Parameter_ID"]):
                links.append((lid, concept_of[f["Parameter_ID"]], dataset))
            stats["loan_flags"] = stats.get("loan_flags", 0) + (f["Loan"].lower() == "true")
        copy_rows(cur, "lexeme", LEXEME_COLS, rows)
        copy_rows(
            cur, "lexeme_concept", ("lexeme_id", "concept_id", "source_id"), sorted(set(links))
        )
        stats.update(lexemes=len(rows), concept_links=len(set(links)))
        if (cldf_dir / "cognates.csv").exists():
            language_of = {r[0]: r[1] for r in rows}
            rels, evidence = cognate_rows(
                cldf_dir / "cognates.csv", language_of, configured, dataset, batch_id
            )
            copy_rows(cur, "relationship", REL_COLS, rels)
            copy_rows(cur, "evidence", EVIDENCE_COLS, evidence)
            stats["cognate_relationships"] = len(rels)
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch_id),
        )
    return {"batch_id": batch_id, **stats}


def spellings(f: dict, transcription: str | None) -> tuple[str, str | None, str | None]:
    """(form to show, native-script spelling, phonetic form) for one CLDF form row.

    Datasets differ: NorthEuraLex puts the native spelling in Value and IPA in Form; IE-CoR
    has a romanised Form plus native_script and phon_form columns; LSI has romanised forms
    only. A ``transcription`` dataset (ASJP) keeps its phonetic code as the form."""
    value, form = f["Value"], f["Form"]
    if transcription:
        return value, None, None
    native = f.get("native_script") or (value if has_native_script(value) else None)
    phonemic = f.get("phon_form") or f.get("Phonemic") or None
    if native and value == native:  # Value is the spelling; Form is a phonetic rendering
        return native, native, phonemic or (form if form != value else None)
    return form or value, native, phonemic


def cognate_rows(
    path: Path, language_of: dict[str, str], configured: set[str], dataset: str, batch_id: int
) -> tuple[list[tuple], list[tuple]]:
    """Undirected cognate pairs within each cognate set, kept when either form is in a
    configured language (the set can be large; pairs among other languages add no value yet)."""
    sets: dict[str, set[str]] = defaultdict(set)
    for r in read_csv(path, COGNATE_COLUMNS):
        lid = lexeme_id(dataset, r["Form_ID"])
        if lid in language_of and r["Cognateset_ID"]:
            sets[r["Cognateset_ID"]].add(lid)
    rels, evidence = [], []
    for set_id, members in sorted(sets.items()):
        for a, b in combinations(sorted(members), 2):
            if language_of[a] not in configured and language_of[b] not in configured:
                continue
            if language_of[a] == language_of[b]:
                continue  # two variants of one language are not a cross-language cognate
            rid = relationship_id(dataset, "cognate", a, b)
            rels.append(
                (
                    rid,
                    a,
                    b,
                    "cognate",
                    Direction.undirected.value,
                    RelationshipStatus.documented.value,
                    dataset,
                    f"cognateset:{set_id}",
                    "cognate set",
                    None,
                    dataset,
                    batch_id,
                )
            )
            evidence.append((rid, dataset, f"{dataset}, cognate set {set_id}", set_id, None))
    return rels, evidence
