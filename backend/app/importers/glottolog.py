"""Attach Glottolog classification to languages that carry a glottocode.

The family hierarchy goes into ``language_family`` and is never mixed with word relationships
(docs/TECHNICAL_ARCHITECTURE.md §6).
"""

import json
from pathlib import Path

import psycopg

from app.importers.common import read_csv

SOURCE_ID = "glottolog"


def import_glottolog(conn: psycopg.Connection, cldf_dir: Path) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT id, glottocode FROM language WHERE glottocode IS NOT NULL")
        wanted = dict(cur.fetchall())
    codes = set(wanted.values())

    paths: dict[str, list[str]] = {}
    for r in read_csv(cldf_dir / "values.csv", ("Language_ID", "Parameter_ID", "Value")):
        if r["Parameter_ID"] == "classification" and r["Language_ID"] in codes:
            paths[r["Language_ID"]] = r["Value"].split("/")
    nodes = {c for p in paths.values() for c in p}

    languoids = {}
    for r in read_csv(cldf_dir / "languages.csv", ("ID", "Name", "Level", "ISO639P3code")):
        if r["ID"] in nodes or r["ID"] in codes:
            languoids[r["ID"]] = r

    with conn.cursor() as cur:
        for path in paths.values():
            parent = None
            for code in path:
                info = languoids.get(code, {"Name": code, "Level": None})
                cur.execute(
                    "INSERT INTO language_family (id, name, level, parent_id, source_id)"
                    " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET"
                    " name = EXCLUDED.name, level = EXCLUDED.level, parent_id = EXCLUDED.parent_id",
                    (code, info["Name"], info["Level"], parent, SOURCE_ID),
                )
                parent = code
        updated = 0
        for lang_id, code in wanted.items():
            path = paths.get(code)
            info = languoids.get(code)
            if info and not path and info["Level"] == "family":
                # e.g. a proto-language mapped to its family's root glottocode
                cur.execute(
                    "INSERT INTO language_family (id, name, level, source_id)"
                    " VALUES (%s, %s, 'family', %s) ON CONFLICT (id) DO NOTHING",
                    (code, info["Name"], SOURCE_ID),
                )
                path = [code]
            if not path or not info:
                continue
            cur.execute(
                "UPDATE language SET family_id = %s, classification_parent_id = %s,"
                " iso_code = COALESCE(iso_code, %s),"
                " metadata_json = metadata_json || jsonb_build_object("
                "   'glottolog_name', %s::text, 'classification_path', %s::jsonb)"
                " WHERE id = %s",
                (
                    path[0],
                    path[-1],
                    info["ISO639P3code"] or None,
                    info["Name"],
                    json.dumps(path),
                    lang_id,
                ),
            )
            cur.execute(
                "INSERT INTO language_alias (language_id, scheme, value) VALUES (%s, 'glottocode',"
                " %s) ON CONFLICT DO NOTHING",
                (lang_id, code),
            )
            if info["ISO639P3code"]:
                cur.execute(
                    "INSERT INTO language_alias (language_id, scheme, value) VALUES"
                    " (%s, 'iso639-3', %s) ON CONFLICT DO NOTHING",
                    (lang_id, info["ISO639P3code"]),
                )
            updated += 1
    return {
        "families": len(nodes),
        "languages_classified": updated,
        "languages_without_classification": len(wanted) - updated,
    }
