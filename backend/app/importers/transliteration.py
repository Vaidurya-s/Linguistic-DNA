"""Import transliteration aliases (native spelling <-> romanisation).

Dakshina lexicons are read straight from the release tarball. Aksharantar is filtered by the
``source`` field on every record so only audit-approved components are kept: manually
collected pairs (CC-BY) and pairs taken from Wikidata (CC0). Its Dakshina-sourced pairs are
skipped because Dakshina itself is imported, and its mined and unnamed parts are BLOCKED.
"""

import io
import json
import tarfile
import zipfile
from collections import Counter
from pathlib import Path

import psycopg

from app.importers.common import copy_rows, sha256_file
from app.services.normalize import normalize_form, search_key

DAKSHINA_LANGUAGES = {
    "hi": "hin",
    "bn": "ben",
    "gu": "guj",
    "kn": "kan",
    "ml": "mal",
    "mr": "mar",
    "pa": "pan",
    "ta": "tam",
    "te": "tel",
}
AKSHARANTAR_LANGUAGES = {
    "asm": "asm",
    "ben": "ben",
    "guj": "guj",
    "hin": "hin",
    "kan": "kan",
    "mal": "mal",
    "mar": "mar",
    "ori": "ory",
    "pan": "pan",
    "san": "san",
    "tam": "tam",
    "tel": "tel",
    "nep": "nep",
    "mai": "mai",
    "doi": "doi",
    "brx": "brx",
    "kok": "gom",
}
AKSHARANTAR_COMPONENTS = {  # record source -> dataset_audit id
    "AK-Freq": "aksharantar-manual",
    "AK-NEI": "aksharantar-manual",
    "AK-NEF": "aksharantar-manual",
    "Wikidata": "aksharantar-wikidata",
}
COLS = ("language_id", "native", "roman", "roman_key", "dataset", "weight", "import_batch_id")


def _batch(cur, dataset: str, version: str, checksums: dict, steps: list[str]) -> int:
    cur.execute(
        "INSERT INTO import_batch (dataset, version, input_checksums, transformations, stats)"
        " VALUES (%s, %s, %s, %s, '{}') RETURNING id",
        (dataset, version, psycopg.types.json.Jsonb(checksums), psycopg.types.json.Jsonb(steps)),
    )
    return cur.fetchone()[0]


def _store(cur, pairs: Counter, batch: int) -> int:
    rows = [
        (lang, native, roman, search_key(roman), dataset, weight or None, batch)
        for (lang, native, roman, dataset), weight in sorted(pairs.items())
        if native and roman
    ]
    copy_rows(cur, "transliteration_alias", COLS, rows)
    return len(rows)


def import_dakshina(conn: psycopg.Connection, tarball: Path, version: str = "v1.0") -> dict:
    pairs: Counter = Counter()
    with tarfile.open(tarball) as tar:
        for member in tar:
            parts = member.name.split("/")
            if (
                len(parts) == 4
                and parts[2] == "lexicons"
                and parts[3].endswith(".tsv")
                and ".translit.sampled." in parts[3]
                and parts[1] in DAKSHINA_LANGUAGES
            ):
                lang = DAKSHINA_LANGUAGES[parts[1]]
                fh = io.TextIOWrapper(tar.extractfile(member), encoding="utf-8")
                for line in fh:
                    native, roman, *count = line.rstrip("\n").split("\t")
                    key = (lang, normalize_form(native), roman.strip().lower(), "dakshina")
                    pairs[key] += int(count[0]) if count and count[0].isdigit() else 1
    with conn.cursor() as cur:
        cur.execute("DELETE FROM transliteration_alias WHERE dataset = 'dakshina'")
        batch = _batch(
            cur,
            "dakshina",
            version,
            {tarball.name: sha256_file(tarball)},
            [
                "lexicons/*.translit.sampled.{train,dev,test}.tsv for target languages",
                "romanisation lower-cased; counts summed across splits",
            ],
        )
        n = _store(cur, pairs, batch)
    return {"aliases": n, "languages": len({k[0] for k in pairs})}


def import_aksharantar(
    conn: psycopg.Connection, directory: Path, revision: str = "e418c1f"
) -> dict:
    pairs: Counter = Counter()
    skipped: Counter = Counter()
    checksums = {}
    for code, lang in AKSHARANTAR_LANGUAGES.items():
        path = directory / f"{code}.zip"
        if not path.exists():
            continue
        checksums[path.name] = sha256_file(path)
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                with zf.open(name) as raw:
                    for line in io.TextIOWrapper(raw, encoding="utf-8"):
                        if not line.strip():
                            continue
                        rec = json.loads(line)
                        dataset = AKSHARANTAR_COMPONENTS.get(rec["source"])
                        if not dataset:
                            skipped[rec["source"]] += 1
                            continue
                        key = (
                            lang,
                            normalize_form(rec["native word"]),
                            rec["english word"].strip().lower(),
                            dataset,
                        )
                        pairs[key] += 1
    datasets = sorted(set(AKSHARANTAR_COMPONENTS.values()))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM transliteration_alias WHERE dataset = ANY(%s)", (datasets,))
        batch = _batch(
            cur,
            "aksharantar",
            revision,
            checksums,
            [
                "records kept only for source in AK-Freq, AK-NEI, AK-NEF, Wikidata",
                "Dakshina-sourced records skipped (Dakshina imported directly)",
                "IndicCorp, Samanantar and Existing records skipped (BLOCKED)",
            ],
        )
        n = _store(cur, pairs, batch)
    return {"aliases": n, "skipped_by_source": dict(skipped)}
