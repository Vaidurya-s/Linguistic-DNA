"""Import a CLDF StructureDataset (WALS, PHOIBLE) as language profiles.

Each value row (``values.csv``: Language_ID, Parameter_ID, Value, Code_ID) becomes a
``language_profile`` row for the language its doculect's glottocode resolves to: a configured
language, or the ``gl-<glottocode>`` record from ``app.cli refresh-languages``. Feature names
come from ``parameters.csv`` and value labels from ``codes.csv``. Profiles describe a language
as a whole; they never create word relationships.
"""

from collections import defaultdict
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, read_csv
from app.pipeline.languages import canonical_targets

COLS = (
    "language_id",
    "dataset",
    "feature_id",
    "feature_name",
    "value",
    "source_record_id",
    "citation",
)


def import_cldf_structure(conn: psycopg.Connection, cldf_dir: Path, dataset: str) -> dict:
    targets = canonical_targets(conn)
    doculects = {
        r["ID"]: targets.get(r["Glottocode"])
        for r in read_csv(cldf_dir / "languages.csv", ("ID", "Glottocode"))
    }
    params = {}
    segment_class = {}  # PHOIBLE: parameters are segments, grouped by class
    for r in read_csv(cldf_dir / "parameters.csv", ("ID", "Name")):
        params[r["ID"]] = r["Name"]
        if r.get("SegmentClass"):
            segment_class[r["ID"]] = r["SegmentClass"]
    codes = {}
    if (cldf_dir / "codes.csv").exists():
        codes = {r["ID"]: r["Name"] for r in read_csv(cldf_dir / "codes.csv", ("ID", "Name"))}
    rows: dict[tuple, tuple] = {}
    unmapped: set[str] = set()
    per_language: dict[str, int] = defaultdict(int)
    for r in read_csv(cldf_dir / "values.csv", ("ID", "Language_ID", "Parameter_ID", "Value")):
        lang = doculects.get(r["Language_ID"])
        if not lang:
            unmapped.add(r["Language_ID"])
            continue
        value = codes.get(r.get("Code_ID") or "", "") or r["Value"]
        if not value:
            continue
        if r["Parameter_ID"] in segment_class:
            cls = segment_class[r["Parameter_ID"]]
            feature_id, feature_name = f"segment:{cls}", f"{cls.capitalize()}s"
        else:
            feature_id = r["Parameter_ID"]
            feature_name = params.get(feature_id, feature_id)
        key = (lang, feature_id, value)
        if key in rows:
            continue
        rows[key] = (
            lang,
            dataset,
            feature_id,
            feature_name,
            value,
            r["ID"],
            r.get("Source") or None,
        )
        per_language[lang] += 1
    with conn.cursor() as cur:
        cur.execute("DELETE FROM language_profile WHERE dataset = %s", (dataset,))
        copy_rows(cur, "language_profile", COLS, rows.values())
    return {
        "profile_rows": len(rows),
        "languages": len(per_language),
        "doculects_unmapped": len(unmapped),
    }
