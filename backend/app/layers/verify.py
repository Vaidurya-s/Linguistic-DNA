"""Re-verify a stored link against the original source file.

`verify_link` reads the link, its two words and its evidence row from the database, then re-reads
the dataset's own CLDF files under data/raw and checks that the source says the same thing:

  cognate links      both Form_IDs exist in forms.csv, both are in the cognate set the evidence
                     cites (cognates.csv), the stored forms equal the source forms, and each word
                     is filed under the source's own doculect (variety);
  borrowing links    the borrowing row the evidence cites exists in borrowings.csv, its target
                     form is the stored borrowed word, its source form (or named source word) is
                     the stored donor word.

Datasets whose links do not come from a CLDF table (Wiktionary, Wikidata, Jambu, StarLing, the
dictionaries, Valyrian) are checked by ``app.layers.verify_sources`` (an index of
the raw dump, or the importer re-run on the raw file). Where that cannot be done (raw file
missing, a different file from the imported one, no index built) the link is reported as
``unsupported: <reason>``: no claim is made for it.

A check that cannot be made is never counted as a pass. Results carry a status (pass, fail,
unsupported) and the reasons of a failure, so a batch can be summarised by reason.

CLI: ``python -m app.cli verify-link <relationship_id>``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.config import REPO_ROOT
from app.importers.cldf_wordlist import spellings
from app.importers.common import read_csv
from app.services.ids import lexeme_id
from app.services.normalize import clean_form

RAW_ROOT = REPO_ROOT / "data" / "raw"
TRANSCRIPTION = {"asjp": "ASJPcode"}  # datasets whose forms are a phonetic code

UNSUPPORTED = {
    "wiktionary": "links are read from the Wiktionary (wiktextract) JSON extract, which is not "
    "kept per link",
    "wikidata-lexemes": "links are Wikidata statements in a JSON dump, not a CLDF table",
    "jambu": "links come from entry text and comparison sidecars of the Jambu database",
    "starling": "links come from StarLing database archives (.exe) that are not read back here",
    "cdsl-mw": "links come from the Monier-Williams dictionary text",
    "dpd": "links come from the Digital Pali Dictionary database",
    "dcs": "links come from the Digital Corpus of Sanskrit lexicon",
    "valyrian": "links come from wiki pages",
}


# Datasets checked by app.layers.verify_sources (index or re-derivation of the raw file). Their
# UNSUPPORTED entries stay as the reason given when that module cannot make the check.
SOURCE_CHECKED = frozenset(
    {"wiktionary", "wikidata-lexemes", "cdsl-mw", "dpd", "jambu", "starling", "valyrian"}
)


@dataclass
class VerifyResult:
    relationship_id: str
    dataset: str | None = None
    status: str = "fail"  # pass | fail | unsupported
    reasons: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def line(self) -> str:
        if self.status == "unsupported":
            return "unsupported: " + "; ".join(self.reasons)
        if self.status == "pass":
            return "pass: " + "; ".join(f"{k}={v}" for k, v in self.detail.items())
        return "fail: " + "; ".join(self.reasons)


def cldf_dir(dataset: str, raw_root: Path = RAW_ROOT) -> Path | None:
    """The CLDF directory of a dataset under data/raw, or None."""
    for p in (raw_root / dataset / "cldf", raw_root / "lexibank" / dataset / "cldf"):
        if (p / "forms.csv").exists() or (p / "forms.csv.zip").exists():
            return p
    return None


def _exists(path: Path) -> bool:
    return path.exists() or path.with_name(path.name + ".zip").exists()


class SourceTables:
    """The parts of one dataset's CLDF tables that a set of links needs, loaded once."""

    def __init__(self, dataset: str, directory: Path) -> None:
        self.dataset = dataset
        self.dir = directory
        self.transcription = TRANSCRIPTION.get(dataset)
        self.forms: dict[str, dict] = {}
        self.sets: dict[str, set[str]] = defaultdict(set)  # Form_ID -> cognate set ids
        self.borrowings: dict[str, dict] = {}
        self.has_cognates = _exists(directory / "cognates.csv")
        self.has_borrowings = _exists(directory / "borrowings.csv")

    def load(self, form_ids: set[str], borrowing_ids: set[str]) -> None:
        wanted = set(form_ids)
        if borrowing_ids and self.has_borrowings:
            for r in read_csv(self.dir / "borrowings.csv", ("ID", "Target_Form_ID")):
                if r["ID"] in borrowing_ids:
                    self.borrowings[r["ID"]] = r
                    wanted.add(r["Target_Form_ID"])
                    if r.get("Source_Form_ID"):
                        wanted.add(r["Source_Form_ID"])
        if self.has_cognates and form_ids:
            for r in read_csv(self.dir / "cognates.csv", ("Form_ID", "Cognateset_ID")):
                if r["Form_ID"] in form_ids and r["Cognateset_ID"]:
                    self.sets[r["Form_ID"]].add(r["Cognateset_ID"])
        for r in read_csv(self.dir / "forms.csv", ("ID", "Language_ID", "Value")):
            if r["ID"] in wanted:
                self.forms[r["ID"]] = r

    def stored_form(self, form_id: str) -> str:
        """The form text the importer stores for a source row (spellings, then clean_form)."""
        raw, _, _ = spellings(self.forms[form_id], self.transcription)
        return clean_form(raw)


def _fetch_links(conn, ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with conn.cursor() as cur:
        for i in range(0, len(ids), 2000):
            cur.execute(
                "SELECT r.id, r.dataset, r.type_id, r.source_record_id, r.source_lexeme_id,"
                " r.target_lexeme_id, ls.source_record_id, ls.form, ls.variety_id,"
                " lt.source_record_id, lt.form, lt.variety_id, r.original_label, r.rank"
                " FROM relationship r JOIN lexeme ls ON ls.id = r.source_lexeme_id"
                " JOIN lexeme lt ON lt.id = r.target_lexeme_id WHERE r.id = ANY(%s)",
                (ids[i : i + 2000],),
            )
            for row in cur.fetchall():
                out[row[0]] = {
                    "id": row[0], "dataset": row[1], "type": row[2], "record": row[3],
                    "src_id": row[4], "tgt_id": row[5],
                    "src": {"rec": row[6], "form": row[7], "variety": row[8]},
                    "tgt": {"rec": row[9], "form": row[10], "variety": row[11]},
                    "label": row[12], "rank": row[13],
                    "evidence": [],
                }  # fmt: skip
        found = list(out)
        for i in range(0, len(found), 2000):
            cur.execute(
                "SELECT relationship_id, citation, locator FROM evidence"
                " WHERE relationship_id = ANY(%s) ORDER BY id",
                (found[i : i + 2000],),
            )
            for rid, citation, locator in cur.fetchall():
                out[rid]["evidence"].append((citation, locator))
    return out


def verify_links(
    conn, relationship_ids: Iterable[str], raw_root: Path = RAW_ROOT
) -> dict[str, VerifyResult]:
    """Verify many links at once; each dataset's source tables are read once per call."""
    ids = list(dict.fromkeys(relationship_ids))
    links = _fetch_links(conn, ids)
    results: dict[str, VerifyResult] = {}
    by_dataset: dict[str, list[dict]] = defaultdict(list)
    for rid in ids:
        if rid not in links:
            results[rid] = VerifyResult(rid, None, "fail", ["relationship_not_found"])
        else:
            by_dataset[links[rid]["dataset"]].append(links[rid])
    for dataset, group in by_dataset.items():
        if dataset in SOURCE_CHECKED:  # checks against the raw files of the non-CLDF datasets
            from app.layers import verify_sources

            results.update(verify_sources.verify_group(conn, dataset, group, raw_root))
            continue
        if dataset in UNSUPPORTED:
            for ln in group:
                results[ln["id"]] = VerifyResult(
                    ln["id"], dataset, "unsupported", [UNSUPPORTED[dataset]]
                )
            continue
        directory = cldf_dir(dataset, raw_root)
        if directory is None:
            for ln in group:
                results[ln["id"]] = VerifyResult(
                    ln["id"], dataset, "unsupported",
                    [f"no CLDF source table for dataset {dataset!r} under data/raw"],
                )  # fmt: skip
            continue
        tables = SourceTables(dataset, directory)
        form_ids = {ln[side]["rec"] for ln in group for side in ("src", "tgt")}
        bids = {
            ln["record"].split(":", 1)[1]
            for ln in group
            if ln["record"] and ln["record"].startswith("borrowing:")
        }
        tables.load(form_ids, bids)
        for ln in group:
            results[ln["id"]] = _check(ln, tables)
    return {rid: results[rid] for rid in ids}


def verify_link(conn, relationship_id: str, raw_root: Path = RAW_ROOT) -> VerifyResult:
    return verify_links(conn, [relationship_id], raw_root)[relationship_id]


def _check(ln: dict, t: SourceTables) -> VerifyResult:
    res = VerifyResult(ln["id"], ln["dataset"])
    why: list[str] = []
    record = ln["record"] or ""
    kind, _, key = record.partition(":")
    locators = {loc for _, loc in ln["evidence"] if loc}
    if not ln["evidence"]:
        why.append("no_evidence_row")
    elif key and key not in locators:
        why.append("evidence_locator_differs_from_link_record")

    if kind == "cognateset" and ln["type"] == "cognate":
        _check_cognate(ln, t, key, why, res)
    elif kind == "borrowing" and ln["type"] == "borrowed_from":
        _check_borrowing(ln, t, key, why, res)
    else:
        why.append(f"link_kind_not_checkable:{ln['type']}/{kind or 'no-record'}")
    res.reasons = why
    res.status = "pass" if not why else "fail"
    return res


def _check_word(side: str, ln: dict, t: SourceTables, why: list[str]) -> None:
    form_id = ln[side]["rec"]
    row = t.forms.get(form_id)
    if row is None:
        why.append(f"{side}_form_missing_in_source")
        return
    if t.stored_form(form_id) != ln[side]["form"]:
        why.append(f"{side}_form_text_differs")
    if ln[side]["variety"] != f"{t.dataset}:{row['Language_ID']}":
        why.append(f"{side}_variety_differs")


def _check_cognate(ln, t: SourceTables, set_id: str, why: list[str], res: VerifyResult) -> None:
    if not t.has_cognates:
        why.append("source_has_no_cognates_table")
        return
    for side in ("src", "tgt"):
        _check_word(side, ln, t, why)
        if set_id not in t.sets.get(ln[side]["rec"], ()):
            why.append(f"{side}_not_in_cited_cognate_set")
    res.detail.update(cognate_set=set_id, forms=f"{ln['src']['rec']},{ln['tgt']['rec']}")


def _check_borrowing(ln, t: SourceTables, bid: str, why: list[str], res: VerifyResult) -> None:
    row = t.borrowings.get(bid)
    if row is None:
        why.append("borrowing_row_missing_in_source")
        return
    # the stored link runs from the borrowed word (source side) to the donor word (target side)
    if ln["src"]["rec"] != row["Target_Form_ID"]:
        why.append("borrowed_word_differs_from_source_target_form")
    else:
        _check_word("src", ln, t, why)
    donor = (row.get("Source_Form_ID") or "").strip()
    raw_word = (row.get("Source_word") or "").strip()
    word = clean_form(raw_word)
    code = (row.get("Source_languoid_glottocode") or "").strip()
    if donor and ln["tgt"]["rec"] == donor:
        _check_word("tgt", ln, t, why)  # the donor is a form of the dataset itself
    elif word and ln["tgt_id"] == lexeme_id(t.dataset, f"borrowing-source:{code}:{raw_word}"):
        # a donor word the table only names: stored as its own record keyed by code and word
        if ln["tgt"]["form"] != word:
            why.append("donor_word_text_differs")
    else:
        why.append("donor_word_differs_from_source")
    res.detail.update(borrowing=bid)
