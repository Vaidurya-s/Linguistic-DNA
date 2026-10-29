"""Import a Lexibank-style CLDF wordlist (used for LSI and ASJP).

Only doculects whose glottocode maps to a configured language are kept; each doculect becomes
a ``variety`` of that language. Forms are linked to Concepticon concepts. These datasets carry
no cognate judgments for our languages, so no historical relationships are created; a
dataset's ``Loan`` flag is kept as a tag because it names no donor.
"""

from pathlib import Path

import psycopg

from app.importers.common import copy_rows, read_csv, sha256_file
from app.importers.concepticon import ensure_concept
from app.importers.jambu import LANGUAGE_CONFIG, TargetLanguage, load_languages
from app.models.enums import ReconstructionStatus
from app.services.ids import lexeme_id
from app.services.normalize import form_kind, normalize_form, search_key

FORM_COLUMNS = ("ID", "Language_ID", "Parameter_ID", "Value", "Form", "Source", "Loan")
LANGUAGE_COLUMNS = ("ID", "Name", "Glottocode")
PARAMETER_COLUMNS = ("ID", "Name", "Concepticon_ID", "Concepticon_Gloss")

LEXEME_COLS = (
    "id",
    "language_id",
    "variety_id",
    "form",
    "normalized_form",
    "search_key",
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
) -> dict:
    """Import one dataset. ``transcription`` names a phonetic code the forms are written in
    (e.g. ASJPcode); such forms are stored as transcriptions, not as orthography."""
    targets = by_glottocode(load_languages(language_config))
    files = ("forms.csv", "languages.csv", "parameters.csv")
    checksums = {name: sha256_file(cldf_dir / name) for name in files}
    doculects = {
        r["ID"]: (targets[r["Glottocode"]], r["Name"])
        for r in read_csv(cldf_dir / "languages.csv", LANGUAGE_COLUMNS)
        if r["Glottocode"] in targets
    }
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
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (dataset,))
        cur.execute("DELETE FROM variety WHERE id LIKE %s", (f"{dataset}:%",))
        for doc_id, (lang, name) in doculects.items():
            cur.execute(
                "INSERT INTO variety (id, language_id, name, source_id) VALUES (%s, %s, %s, %s)",
                (f"{dataset}:{doc_id}", lang.id, name, dataset),
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
            lang, _ = doc
            param = params.get(f["Parameter_ID"], {})
            raw = f["Value"] if transcription else (f["Form"] or f["Value"])
            lid = lexeme_id(dataset, f["ID"])
            page = param.get("PageNumber")
            citation = f"{f['Source'] or dataset}" + (f"[p. {page}]" if page else "")
            rows.append(
                (
                    lid,
                    lang.id,
                    f"{dataset}:{f['Language_ID']}",
                    raw,
                    normalize_form(raw),
                    search_key(raw),
                    None if transcription else raw,
                    raw if transcription else None,
                    param.get("Name"),
                    form_kind(raw).value,
                    ReconstructionStatus.attested.value,
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
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch_id),
        )
    return {"batch_id": batch_id, **stats}
