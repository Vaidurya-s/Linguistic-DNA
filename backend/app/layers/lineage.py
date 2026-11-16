"""Source lineage: which dataset is derived from which.

Agreement between two datasets that share a lineage is not independent evidence: when
Etymological WordNet is mined from Wiktionary, a link both hold was stated once. This module
records the derivations that a readme, a dataset metadata file or a paper states, and turns them
into lineage groups so that corroboration can be counted per independent group instead of per
dataset.

Rules for the seed (SEED below):
  * a row is verified only when a document says so; the note names the document;
  * a suspected link that no document confirms is stored as kind 'unknown', verified = false, and
    is never used by `groups` unless the caller asks for the unverified view;
  * 'derived' / 'contains': the dataset takes its records from derived_from (a dataset id or a
    named resource); 'shared_origin': two datasets come from one project or publication, so they
    are not independent although neither takes records from the other.

CLI: ``python -m app.cli seed-lineage``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SQL_FILE = Path(__file__).with_name("lineage.sql")
STRICT_KINDS = ("derived", "contains")
BROAD_KINDS = ("derived", "contains", "shared_origin")
# the sensitivity view: also the suspected links no document confirms (needs include_unverified)
HYPOTHETICAL_KINDS = BROAD_KINDS + ("unknown",)


@dataclass(frozen=True)
class Lineage:
    dataset: str
    derived_from: str
    kind: str
    evidence_note: str
    verified: bool


def _starostin(dataset: str, note: str, kind: str = "shared_origin") -> Lineage:
    return Lineage(dataset, "starling", kind, note, True)


SEED: tuple[Lineage, ...] = (
    # --- resources outside the database (listed so that the groups are complete)
    Lineage(
        "etymwn",
        "wiktionary",
        "derived",
        "data/raw/etymwn/readme.txt: 'mostly mined from the English version of Wiktionary, but "
        "also contains a number of manual additions'.",
        True,
    ),
    Lineage(
        "cognet",
        "etymwn",
        "derived",
        "Batsuren, Bella, Giunchiglia, CogNet, ACL 2019 (as summarised in the project's "
        "literature review, which is not in the repository): uses 94,832 cross-lingual "
        "relations of Etymological WordNet as direct evidence.",
        True,
    ),
    Lineage(
        "cognet",
        "wiktionary",
        "derived",
        "Transitive: cognet -> etymwn (ACL 2019, literature review P4) and etymwn -> wiktionary "
        "(etymwn readme). Other CogNet inputs (wordnets, similarity) are not Wiktionary.",
        True,
    ),
    Lineage(
        "etymdb",
        "wiktionary",
        "derived",
        "Sagot/Fourrier EtymDB 1.0 and 2.0 (LREC 2020, literature review P2/P3): relations "
        "extracted from Wiktionary dumps; docs/CANDIDATE_DATASETS.md Tier D: 'Built from "
        "Wiktionary dumps'.",
        True,
    ),
    # --- datasets of the database
    Lineage(
        "jambu",
        "lsi",
        "contains",
        "data/raw/jambu/README.md (section 'Linguistic Survey of India comparative vocabulary'): "
        "raw_data/grierson_lsi.py imports the Lexibank v1.0 retrostandardization of Grierson's "
        "Comparative Vocabulary into the Jambu forms; data/manifests/source_manifest.csv row "
        "grierson-lsi1928.",
        True,
    ),
    Lineage(
        "jambu",
        "dravlex",
        "contains",
        "data/raw/jambu/README.md (DravLex CLDF, 20260911-dravlex.csv, 2,127 records) and "
        "source_checklists/20260911-dravlex.md; data/manifests/source_manifest.csv row "
        "kolipakam2018dravlex.",
        True,
    ),
    Lineage(
        "jambu",
        "cdial",
        "contains",
        "data/manifests/dataset_audit.csv: cdial 'used through Jambu'; data/manifests/"
        "jambu_source_map.csv.",
        True,
    ),
    Lineage(
        "jambu",
        "dedr",
        "contains",
        "data/manifests/dataset_audit.csv: dedr 'used through Jambu'; data/manifests/"
        "jambu_source_map.csv.",
        True,
    ),
    _starostin(
        "starostinpie",
        "data/raw/lexibank/starostinpie/cldf/cldf-metadata.json and sources.bib: derived from "
        "Starostin's 'Indo-European files in DBF/VAR' (2005), 'The Tower of Babel', "
        "starling.rinet.ru/downl.php, the site the StarLing IE database comes from. The file "
        "named is the StarLing IE archive, not shown to be the same file, so only a shared "
        "origin is recorded.",
    ),
    _starostin(
        "starostinkaren",
        "cldf-metadata.json: identifier on starling.rinet.ru (The Global Lexicostatistical "
        "Database, Starostin 2017): same project site as the StarLing databases, a different "
        "database.",
    ),
    _starostin(
        "starostintujia",
        "cldf-metadata.json: citation URL starling.rinet.ru/new100/tuj.xls (Global "
        "Lexicostatistical Database, Starostin 2013).",
    ),
    _starostin(
        "saenkoromance",
        "cldf-metadata.json: Saenko 2015, in Starostin (ed.), The Global Lexicostatistical "
        "Database, starling.rinet.ru/new100.",
    ),
    _starostin(
        "zhivlovobugrian",
        "sources.bib: Zhivlov 2011 Ob-Ugrian Swadesh wordlists, url starling.rinet.ru/new100/"
        "oug.xls.",
    ),
    # --- suspected, no document found: open questions, not claims
    Lineage(
        "wikidata-lexemes",
        "wiktionary",
        "unknown",
        "Not verified as a dataset-level derivation. Wikidata lexemes are partly derived from "
        "Wiktionary, but only 0.67% of statements prove it; for the rest it cannot be "
        "determined. Raw dump wikidata-20261028: of 54,500 P5191 statements 33,656 (61.8%) "
        "carry a reference and 20,844 (38.2%) none; only 366 (0.67% of all, 1.1% of "
        "referenced) cite a Wiktionary edition; the other references are dictionaries (for "
        "example DLE 6,578, Concise Dictionary of Akkadian 5,229, OED 2,113, Dehkhoda 1,983, "
        "CDIAL 690). The 38% without a reference have unknown provenance. The overlap with "
        "Wiktionary is the same for unreferenced (66%), other-dictionary (65%) and "
        "Wiktionary-citing (57%) statements, so there is no sign of silent copying, but "
        "statistics cannot prove independence. Wikidata's own pages (Wikidata:Wiktionary, "
        "Property:P5191, the 2018 etymology property proposal) state no Wiktionary import of "
        "etymology; P5191 was proposed with etymological dictionaries and research as "
        "sources. Best estimate: mostly independent in stated provenance, partly derived "
        "(at least 0.7%, upper bound unknown). Kept as 'unknown', verified = false, so a "
        "dataset-level row does not merge all 54,500 statements into one lineage.",
        False,
    ),
    Lineage(
        "jambu",
        "cdsl-mw",
        "unknown",
        "Both cover Sanskrit; no file read states that Jambu ingests the Monier-Williams "
        "dictionary data used here. Not verified.",
        False,
    ),
    Lineage(
        "abvd",
        "acd",
        "unknown",
        "Both are Austronesian cognate resources; no metadata file read states that one is "
        "built from the other. Not verified.",
        False,
    ),
    Lineage(
        "peirosst",
        "starling",
        "unknown",
        "Peiros' Sino-Tibetan wordlists use the Starostin-1991 concept list; whether they were "
        "taken from a StarLing database is not stated in the files read. Not verified.",
        False,
    ),
)


def ensure_schema(conn) -> None:
    """Create the lineage table if it does not exist (idempotent)."""
    conn.execute(SQL_FILE.read_text(encoding="utf-8"))


def seed(conn, rows: Iterable[Lineage] = SEED) -> int:
    """Insert or refresh the seed rows (idempotent). Returns the number of rows written."""
    ensure_schema(conn)
    n = 0
    for r in rows:
        conn.execute(
            "insert into layers.source_lineage (dataset, derived_from, kind, evidence_note,"
            " verified) values (%s, %s, %s, %s, %s)"
            " on conflict (dataset, derived_from, kind) do update set"
            " evidence_note = excluded.evidence_note, verified = excluded.verified",
            (r.dataset, r.derived_from, r.kind, r.evidence_note, r.verified),
        )
        n += 1
    return n


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # the smaller name stays the label, so groups are named deterministically
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo


def group_map(
    edges: Iterable[tuple[str, str, str, bool]],
    kinds: Iterable[str] = STRICT_KINDS,
    include_unverified: bool = False,
) -> dict[str, str]:
    """dataset (or resource) -> lineage group label, from (dataset, derived_from, kind,
    verified) rows. Only the given kinds count, and unverified rows only on request.
    Names that appear in no counted row are not in the result: they are their own group."""
    kinds = set(kinds)
    uf = _UnionFind()
    for dataset, derived_from, kind, verified in edges:
        if kind in kinds and (verified or include_unverified):
            uf.union(dataset, derived_from)
    return {name: uf.find(name) for name in list(uf.parent)}


def load_edges(conn) -> list[tuple[str, str, str, bool]]:
    """The stored lineage rows as (dataset, derived_from, kind, verified); [] if no table."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass('layers.source_lineage')")
        if cur.fetchone()[0] is None:
            return []
        cur.execute("select dataset, derived_from, kind, verified from layers.source_lineage")
        return cur.fetchall()


def lineage_group(mapping: dict[str, str], dataset: str) -> str:
    return mapping.get(dataset, dataset)
