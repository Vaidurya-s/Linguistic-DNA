"""Rebuild backend/tests/fixtures/jambu_mini from a local Jambu snapshot.

Usage:
    python scripts/build_fixture.py data/raw/jambu/cldf data/raw/jambu-lfs/forms.csv \
        [data/raw/glottolog-cldf/cldf]

The fixture is a handful of records chosen to exercise the importer: a CDIAL etymon with
reflexes in several languages, a DEDR etymon with Dravidian reflexes, a Sanskrit loan in
Kannada, a starred reconstruction, a homonym pair and an unlinked form. Entry text is never
copied: the Etymology column holds a synthetic sentinel so tests can prove it is dropped.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(2**31 - 1)
FIXTURES = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
OUT = FIXTURES / "jambu_mini"
SENTINEL = "FIXTURE_SENTINEL_ETYMOLOGY_MUST_NOT_BE_STORED"
TARGETS = {"H", "B", "M", "G", "P", "Or", "A", "Tamil", "Telugu", "Kannada", "Malayalam"}

ETYMA = ["6152", "d1041"]  # CDIAL dánta 'tooth'; DEDR *ōṭu 'to flee'
EXTRA_FORMS = ["f_27fxniq4x3i6i"]  # Kannada sottu, borrowed from Sanskrit svatva-
PER_LANGUAGE = 2


def rows(path: Path):
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        yield from reader


def write(name: str, header: list[str], data: list[dict], out: Path = OUT) -> None:
    with (out / name).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(data)


def main(cldf: Path, forms_path: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    forms = {r["ID"]: r for r in rows(forms_path)}
    edges = list(rows(cldf / "edges.csv"))
    children = defaultdict(list)
    parents = defaultdict(list)
    for e in edges:
        children[e["Parent_ID"]].append(e)
        parents[e["Child_ID"]].append(e)

    keep: list[str] = []
    for etymon in ETYMA:
        keep.append(etymon)
        per_lang = defaultdict(int)
        for e in children[etymon]:
            lang = forms[e["Child_ID"]]["Language_ID"]
            if e["Kind"] == "reflex" and lang in TARGETS and per_lang[lang] < PER_LANGUAGE:
                per_lang[lang] += 1
                keep.append(e["Child_ID"])
    keep += EXTRA_FORMS

    # A homonym pair (same Hindi form, different glosses) and an unlinked Hindi form.
    by_form = defaultdict(list)
    for r in forms.values():
        if r["Language_ID"] == "H" and r["Gloss"] and parents.get(r["ID"]):
            by_form[r["Form"]].append(r["ID"])
    homonym = next(ids for f, ids in sorted(by_form.items()) if len(ids) == 2 and len(f) == 3)
    keep += homonym
    keep.append(next(r["ID"] for r in forms.values()
                     if r["Language_ID"] == "H" and r["Status"] == "unlinked" and r["Gloss"]))

    # Close over parents so every kept edge resolves.
    frontier = list(keep)
    while frontier:
        nxt = []
        for fid in frontier:
            for e in parents.get(fid, ()):
                if e["Parent_ID"] not in keep:
                    keep.append(e["Parent_ID"])
                    nxt.append(e["Parent_ID"])
        frontier = nxt
    kept = set(keep)

    form_header = list(next(iter(forms.values())).keys())
    out_forms = []
    for fid in dict.fromkeys(keep):
        r = dict(forms[fid])
        r["Etymology"] = SENTINEL
        out_forms.append(r)
    write("forms.csv", form_header, out_forms)
    write("edges.csv", list(edges[0].keys()),
          [e for e in edges if e["Child_ID"] in kept and e["Parent_ID"] in kept])

    comparisons = list(rows(cldf / "comparisons.csv"))
    write("comparisons.csv", list(comparisons[0].keys()),
          [{**c, "Evidence": SENTINEL} for c in comparisons
           if c["Entry_ID"] in kept and c["Compared_Entry_ID"] in kept])

    langs = {r["Language_ID"] for r in out_forms}
    language_rows = [r for r in rows(cldf / "languages.csv") if r["ID"] in langs]
    write("languages.csv", list(language_rows[0].keys()), language_rows)

    links = [r for r in rows(cldf / "form_concepts.csv") if r["Form_ID"] in kept]
    write("form_concepts.csv", ["Form_ID", "Concept_ID"], links)
    concept_ids = {r["Concept_ID"] for r in links}
    concepts = [r for r in rows(cldf / "concepts.csv") if r["ID"] in concept_ids]
    write("concepts.csv", ["ID", "Name", "Category"], concepts)

    keys = set()
    for r in out_forms:
        keys |= {p.split("[")[0].strip() for p in r["Source"].split(";") if p.strip()}
    refs = [r for r in rows(cldf / "references.csv") if r["ID"] in keys]
    write("references.csv", ["ID", "Short", "Source"], refs)
    print(f"{len(out_forms)} forms, {len(links)} concept links -> {OUT}")
    return {r["Glottocode"] for r in language_rows if r["Glottocode"]}


def glottolog_extract(glottolog: Path, codes: set[str]) -> None:
    """Copy the classification rows the fixture languages need (Glottolog is CC-BY-4.0)."""
    out = FIXTURES / "glottolog_mini"
    out.mkdir(parents=True, exist_ok=True)
    values = [r for r in rows(glottolog / "values.csv")
              if r["Parameter_ID"] == "classification" and r["Language_ID"] in codes]
    nodes = codes | {c for r in values for c in r["Value"].split("/")}
    languoids = [r for r in rows(glottolog / "languages.csv") if r["ID"] in nodes]
    write("values.csv", ["ID", "Language_ID", "Parameter_ID", "Value"], values, out)
    write("languages.csv", ["ID", "Name", "Level", "ISO639P3code"], languoids, out)
    print(f"{len(values)} classification rows, {len(languoids)} languoids -> {out}")


if __name__ == "__main__":
    glottocodes = main(Path(sys.argv[1]), Path(sys.argv[2]))
    if len(sys.argv) > 3:
        glottolog_extract(Path(sys.argv[3]), glottocodes)
