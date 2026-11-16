"""Source checks for the datasets that do not come from a CLDF table.

`app.layers.verify` re-reads CLDF files. This module adds the other seven datasets. A link is
checked against the dataset's own raw file under data/raw, never against the database alone.

wiktionary         A one-pass index of the wiktextract dump (``build_wiktionary_index``) maps each
                   entry's record key to a byte range in a reduced copy of the dump (the fields the
                   importer reads). A link is checked with a lookup and a seek: the page exists,
                   one of its etymology templates (or its descendants list, or the entry text for
                   a retyped link) names the stored target word in the stored language, the
                   importer's own functions (``template_edges``, ``descendant_edges``,
                   ``borrowed_donor`` ...) give the stored relationship id and type, and the
                   evidence points at the page.
wikidata-lexemes   A one-pass index of the lexeme dump: the statement id, its property, the target
                   lexeme, the statement's rank and reference, and both lemmas are compared.
cdsl-mw, dpd, jambu, starling, valyrian
                   The raw files are small enough to run the dataset's importer on them in memory
                   (copy calls captured, no database write). Every stored link must then appear in
                   the result with the same ids, type, record, label, evidence and word forms.

Checks that cannot be made are never counted as a pass. A dataset whose raw file differs from the
file the database was imported from (sha256 recorded in import_batch) is reported as unsupported
with that reason: the stored links were not made from this file.

The checks share the importer's parsing rules. They show that the database says what the source
file says under those rules; they do not test that the rules read the source correctly.
"""

from __future__ import annotations

import bz2
import hashlib
import importlib
import json
import os
import pickle
import re
import sqlite3
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from multiprocessing import Pool
from pathlib import Path
from unittest import mock

from app.config import REPO_ROOT
from app.layers.verify import VerifyResult
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import clean_form, is_placeholder_form, normalize_form

SCRATCH_ENV = "LSG_VERIFY_SCRATCH"
SUPPORTED = ("wiktionary", "wikidata-lexemes", "cdsl-mw", "dpd", "jambu", "starling", "valyrian")
DERIVED = {"cdsl-mw": "cdsl", "dpd": "dpd", "jambu": "jambu", "starling": "starling"}


def scratch_root() -> Path:
    """Where the big indexes live: ``$LSG_VERIFY_SCRATCH`` or <repo>/logs (git-ignored, never
    docs: the Wiktionary text is CC BY-SA and the research-use data must not be published)."""
    env = os.environ.get(SCRATCH_ENV)
    return Path(env) if env else REPO_ROOT / "logs"


# ---------------------------------------------------------------------------- source files


def _stamp(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def file_sha256(path: Path, cache: Path | None = None) -> str:
    """sha256 of a file; large files are hashed once and remembered by size and mtime."""
    cache = cache or scratch_root() / "d2_checksums.json"
    try:
        known = json.loads(cache.read_text())
    except (OSError, ValueError):
        known = {}
    size, mtime = _stamp(path)
    hit = known.get(str(path))
    if hit and hit[:2] == [size, mtime]:
        return hit[2]
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    known[str(path)] = [size, mtime, h.hexdigest()]
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(known))
    except OSError:
        pass
    return h.hexdigest()


def source_files(dataset: str, raw: Path) -> dict[str, Path]:
    """The raw files a dataset's importer read, by the name import_batch records for them."""
    if dataset == "wiktionary":
        return {p.name: p for p in sorted((raw / "wiktionary").glob("*.jsonl*"))}
    if dataset == "wikidata-lexemes":
        return {p.name: p for p in sorted((raw / "wikidata").glob("*lexemes*.json*"))}
    if dataset == "cdsl-mw":
        return {"mw.txt": raw / "cdsl" / "mw.txt"}
    if dataset == "dpd":
        return {"dpd.db.tar.xz": raw / "dpd" / "dpd.db.tar.xz"}
    if dataset == "starling":
        d = raw / "starling"
        if not d.is_dir():
            return {}
        return {p.name: p for p in sorted(d.iterdir()) if p.suffix.lower() in (".exe", ".zip")}
    if dataset == "jambu":
        out = {p.name: p for p in sorted((raw / "jambu" / "cldf").glob("*.csv"))}
        out["forms.csv"] = raw / "jambu-lfs" / "forms.csv"
        return out
    if dataset == "valyrian":
        return {"manifest.json": raw / "valyrian" / "manifest.json"}
    return {}


def source_state(conn, dataset: str, raw: Path) -> tuple[bool, str]:
    """(usable, reason). Usable when the raw files exist and are the files the latest import
    recorded (sha256; for Valyrian the manifest of downloaded pages)."""
    files = {n: p for n, p in source_files(dataset, raw).items() if p.exists()}
    if not files:
        return False, f"raw source for {dataset} not found under data/raw"
    if dataset == "dpd" and not (raw / "dpd" / "x" / "dpd.db").exists():
        return False, "unpacked dpd.db not found under data/raw/dpd/x"
    row = conn.execute(
        "SELECT input_checksums FROM import_batch WHERE dataset = %s ORDER BY id DESC LIMIT 1",
        (dataset,),
    ).fetchone()
    recorded = row[0] if row else None
    if not recorded:
        return False, "no import_batch with checksums for this dataset"
    if dataset == "valyrian":
        try:
            same = json.loads(files["manifest.json"].read_text()) == recorded
        except (OSError, ValueError):
            same = False
        return (same, "" if same else "raw manifest differs from the one imported")
    shared = [n for n in recorded if n in files and len(str(recorded[n])) == 64]
    if not shared:
        return False, "raw file is not one the import recorded a sha256 for"
    for name in shared:
        if file_sha256(files[name]) != recorded[name]:
            return False, f"raw file {name} differs from the imported file (sha256)"
    return True, ""


# ---------------------------------------------------------------------------- Wiktionary

DUMP_NAME = "raw-wiktextract-data.jsonl.gz"
_MARKERS = (b'"etymology_templates"', b'"descendants"', b'"etymology_text"')
_KEEP_DESC = ("word", "lang_code", "roman", "tags", "raw_tags")
_LANG_PAIR = re.compile(rb'"lang": ?"([^"]+)", ?"lang_code": ?"([^"]+)"')


def _prune_descendants(items: list) -> list:
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        d = {k: it[k] for k in _KEEP_DESC if k in it}
        if it.get("descendants"):
            d["descendants"] = _prune_descendants(it["descendants"])
        out.append(d)
    return out


def _reduce_entry(e: dict):
    """(key, title, bytes, language name, code) of a kept dump entry, else None. The key is the
    importer's own: ``term_key(lang_code, clean_form(word))``."""
    from app.importers.wiktionary import _CODE, term_key

    code, raw_word = e.get("lang_code"), e.get("word")
    word = clean_form(raw_word) if raw_word else ""
    if not word or not code or is_placeholder_form(word) or not _CODE.fullmatch(code):
        return None
    templates = [
        {"name": t.get("name", ""), "args": t.get("args") or {}}
        for t in e.get("etymology_templates") or []
    ]
    text = e.get("etymology_text") or ""
    desc = _prune_descendants(e.get("descendants") or [])
    if not (templates or desc or text):
        return None
    page = e.get("original_title") or raw_word
    rec = {"c": code, "w": raw_word, "t": text, "e": templates}
    if page != raw_word:
        rec["p"] = page
    if desc:
        rec["d"] = desc
    data = json.dumps(rec, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return term_key(code, word), normalize_form(clean_form(page)), data, e.get("lang"), code


def _wkt_work(batch: list[bytes]):
    """(lines read, kept rows, language names an entry gives itself, names only mentioned). The
    importer learns names from every line (first mention wins) and lets an entry's own win."""
    out, names, mentioned = [], {}, {}
    for line in batch:
        if not line.startswith(b"{"):
            continue
        for lang, code in _LANG_PAIR.findall(line):
            if not lang.endswith(b" script"):
                mentioned.setdefault(code.decode(), lang.decode())
        if not any(m in line for m in _MARKERS):
            continue
        try:
            r = _reduce_entry(json.loads(line))
        except ValueError:
            continue
        if r:
            out.append(r[:3])
            if r[3]:
                names[r[4]] = r[3]
    return len(batch), out, names, mentioned


def _batches(stream, size: int, limit: int | None) -> Iterator[list[bytes]]:
    buf = []
    for n, line in enumerate(stream, start=1):
        buf.append(line)
        if len(buf) >= size:
            yield buf
            buf = []
        if limit and n >= limit:
            break
    if buf:
        yield buf


def build_wiktionary_index(
    dump: Path,
    out: Path,
    workers: int = 8,
    limit: int = 0,
    log: Callable[[str], None] = lambda m: None,
) -> dict:
    """One pass over the gzipped JSONL dump. Writes ``extract.jsonl`` (one reduced line per entry
    that has an etymology text, templates or descendants) and ``index.sqlite`` (entry(key, title,
    off, len), names(code, name), meta) under ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    ext_path, db_path = out / "extract.jsonl", out / "index.sqlite"
    for p in (ext_path, db_path):
        p.unlink(missing_ok=True)
    db = sqlite3.connect(db_path)
    db.executescript(
        "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
        "CREATE TABLE entry (key TEXT, title TEXT, off INTEGER, len INTEGER);"
        "CREATE TABLE names (code TEXT PRIMARY KEY, name TEXT);"
        "CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);"
    )
    cmd = ["pigz", "-dc", str(dump)] if dump.suffix == ".gz" else ["cat", str(dump)]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1 << 22)
    except FileNotFoundError:  # no pigz
        proc = subprocess.Popen(["gzip", "-dc", str(dump)], stdout=subprocess.PIPE, bufsize=1 << 22)
    t0, lines, kept, off = time.time(), 0, 0, 0
    names: dict[str, str] = {}
    mentioned: dict[str, str] = {}
    with open(ext_path, "wb") as ext, Pool(workers) as pool:
        for n, rows, nm, mention in pool.imap(
            _wkt_work, _batches(proc.stdout, 4000, limit or None)
        ):
            lines += n
            names.update(nm)
            for code, lang in mention.items():
                mentioned.setdefault(code, lang)
            rec = []
            for key, title, data in rows:
                ext.write(data + b"\n")
                rec.append((key, title, off, len(data)))
                off += len(data) + 1
            kept += len(rec)
            db.executemany("INSERT INTO entry VALUES (?,?,?,?)", rec)
            if lines % 400_000 < 4000:
                log(f"{lines:,} lines, {kept:,} kept, {time.time() - t0:.0f}s")
    if limit:
        proc.kill()
    proc.wait()
    db.executemany("INSERT INTO names VALUES (?,?)", {**mentioned, **names}.items())
    meta = {
        "dump": dump.name,
        "dump_bytes": str(dump.stat().st_size),
        "dump_mtime": str(int(dump.stat().st_mtime)),
        "lines": str(lines),
        "kept": str(kept),
        "extract_bytes": str(off),
        "limit": str(limit),
    }
    db.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    db.execute("CREATE INDEX entry_key ON entry(key)")
    db.execute("CREATE INDEX entry_title ON entry(title)")
    db.commit()
    db.close()
    return meta


class WiktionaryIndex:
    """Lookups into the index written by ``build_wiktionary_index``."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.db = sqlite3.connect(f"file:{directory / 'index.sqlite'}?mode=ro", uri=True)
        self.ext = open(directory / "extract.jsonl", "rb")  # noqa: SIM115 - lives with the index
        self.meta = dict(self.db.execute("SELECT k, v FROM meta"))
        self.names = dict(self.db.execute("SELECT code, name FROM names"))

    def stale_reason(self, dump: Path) -> str | None:
        if not dump.exists():
            return None
        if self.meta.get("dump_bytes") != str(dump.stat().st_size):
            return "index was built from a dump of a different size"
        if self.meta.get("dump_mtime") != str(int(dump.stat().st_mtime)):
            return "index was built from a dump with a different modification time"
        return None

    def _read(self, rows) -> list[dict]:
        out = []
        for off, ln in rows:
            self.ext.seek(off)
            out.append({**json.loads(self.ext.read(ln)), "_off": off})
        return out

    def by_key(self, key: str) -> list[dict]:
        return self._read(
            self.db.execute("SELECT off, len FROM entry WHERE key = ? ORDER BY off", (key,))
        )

    def by_title(self, title: str) -> list[dict]:
        return self._read(
            self.db.execute("SELECT off, len FROM entry WHERE title = ? ORDER BY off", (title,))
        )

    def close(self) -> None:
        self.db.close()
        self.ext.close()


def wiktionary_index_dir(scratch: Path | None = None) -> Path:
    return (scratch or scratch_root()) / "d2_wkt"


def _rec_entry(rec: dict) -> dict:
    """The entry as the importer sees it after reading the dump line."""
    return {
        "word": rec.get("p") or rec["w"],
        "lang_code": rec["c"],
        "etymology_templates": rec["e"],
        "etymology_text": rec["t"],
        "descendants": rec.get("d") or [],
    }


def rec_edges(rec: dict) -> tuple[str, list]:
    """(entry key, [(Edge, Term)]) from one index line, by the importer's own functions."""
    from app.importers.wiktionary import descendant_edges, template_edges, term_key

    e = _rec_entry(rec)
    key = term_key(rec["c"], clean_form(rec["w"]))
    pairs = [
        *template_edges(e, key, rec["c"]),
        *descendant_edges(e["descendants"], key, e["word"]),
    ]
    return key, [(ed, o) for ed, o in pairs if ed.parent != ed.child]


def edge_rid(edge) -> tuple[str, str, str]:
    """(relationship id, first key, second key) the importer gives an edge before any retyping."""
    if edge.type_id == "cognate":
        a, b = sorted((edge.child, edge.parent))
    else:
        a, b = edge.child, edge.parent
    return relationship_id("wiktionary", edge.type_id, a, b), a, b


RETYPE_LABEL = " + entry etymology text"


def _text_flags(recs: list[dict]) -> tuple[bool, bool]:
    from app.importers.wiktionary import _BORROWED_TEXT, _INHERITED_TEXT

    per_line = any(
        bool(_BORROWED_TEXT.search(r["t"])) and not _INHERITED_TEXT.search(r["t"]) for r in recs
    )
    borrowed = any(_BORROWED_TEXT.search(r["t"]) for r in recs)
    inherited = any(_INHERITED_TEXT.search(r["t"]) for r in recs)
    return per_line or (borrowed and not inherited), inherited


def _retype_problem(
    ln: dict, edge, rec: dict, pairs: list, idx: WiktionaryIndex, names
) -> str | None:
    """None when the importer's etymology-text rule explains a borrowed_from link whose template
    says something else; otherwise the reason it does not."""
    from app.importers.wiktionary import (
        GENERIC_ETYMON,
        borrowed_donor,
        donor_language_matches,
        donor_prefix,
    )

    if ln["type"] != "borrowed_from":
        return f"type_differs:{ln['type']}!={edge.type_id}"
    if not (ln.get("label") or "").endswith(RETYPE_LABEL):
        return f"type_differs:{ln['type']}!={edge.type_id}"
    if edge.template == "desc":
        if edge.type_id != "inherited_form":
            return f"retyped_desc_link_was_{edge.type_id}"
        child = idx.by_key(edge.child)
        ok, _ = _text_flags(child)
        return None if ok else "retype_child_entry_text_does_not_say_borrowed"
    if edge.template in GENERIC_ETYMON:
        if edge.type_id != "etymon":
            return f"retyped_der_link_was_{edge.type_id}"
        if any(
            ed.type_id in ("borrowed_from", "inherited_form", "calque_or_loan_translation")
            for ed, _ in pairs
            if ed.template != "desc"
        ):
            return "retype_but_entry_has_a_firmer_template"
        donor = borrowed_donor(rec["t"])
        if not donor:
            return "retype_entry_text_names_no_donor"
        prefix = donor_prefix(donor, edge.shown)
        if prefix is None:
            return "retype_donor_in_text_is_not_the_target"
        _, other = next(
            ((ed, o) for ed, o in pairs if ed is edge), (None, None)
        )  # the term the edge points at
        if other is not None and not donor_language_matches(
            prefix, names, other.code, bool(edge.variety)
        ):
            return "retype_donor_language_differs_from_target"
        for ed, o in pairs:  # one donor per entry: the first fitting {{der}} line
            if ed.template in GENERIC_ETYMON and ed.type_id == "etymon":
                p = donor_prefix(donor, ed.shown)
                if p is not None and donor_language_matches(p, names, o.code, bool(ed.variety)):
                    if edge_rid(ed)[0] != edge_rid(edge)[0]:
                        return "retype_not_the_first_fitting_der_link"
                    break
        return None
    return f"type_differs:{ln['type']}!={edge.type_id}"


def _form_matches_key(form: str | None, key: str) -> bool:
    return normalize_form((form or "").lstrip("*")) == key.split(":", 1)[1]


_CITED_KIND = {
    "inherited_form": "inherited",
    "borrowed_from": "borrowed",
    "calque_or_loan_translation": "calque",
    "cognate": "cognate",
    "has_component": "word formation",
}


def _citation(page: str, template: str, type_id: str, retyped: bool) -> str:
    """evidence.citation as the importer words it (a descendants line, the entry text or the
    etymology section, by the stored type)."""
    if retyped:
        what = "etymology text (borrowing)"
    elif template == "desc":
        what = "descendants"
    else:
        what = f"etymology ({_CITED_KIND.get(type_id, 'derived')})"
    return f"Wiktionary, \u201c{page}\u201d, {what}"


class LexLookup:
    """Stored lexemes by id (language, form, record), looked up one at a time and remembered."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self.cache: dict[str, dict | None] = {}

    def __call__(self, lexeme: str) -> dict | None:
        if lexeme not in self.cache:
            row = self.conn.execute(
                "SELECT language_id, form, source_record_id FROM lexeme WHERE id = %s", (lexeme,)
            ).fetchone()
            self.cache[lexeme] = (
                dict(zip(("language", "form", "rec"), row, strict=True)) if row else None
            )
        return self.cache[lexeme]


def _side_problems(side: str, expected: str, ln: dict, lex: LexLookup | None, res) -> list[str]:
    """The stored lexeme on one side must be the word the dump names (``expected`` is the
    entry's record key). A language merge may have folded the lexeme into a same-language,
    same-spelling survivor (nb:bord into nn:bord); that is accepted and counted."""
    why: list[str] = []
    if not _form_matches_key(ln[side]["form"], expected):
        why.append(f"{side}_form_differs_from_the_word_in_the_dump")
    if ln[f"{side}_id"] == lexeme_id("wiktionary", expected):
        return why
    stored = lex(ln[f"{side}_id"]) if lex else None
    want = lex(lexeme_id("wiktionary", expected)) if lex else None
    if stored is None:
        why.append(f"{side}_lexeme_is_not_the_word_in_the_dump")
    elif want is not None and stored["language"] != want["language"]:
        why.append(f"{side}_lexeme_in_another_language_than_the_dump_word")
    else:
        res.detail[f"{side}_lexeme_merged_after_import"] = True
    return why


def check_wiktionary(
    ln: dict, idx: WiktionaryIndex, names: dict[str, str], lex: LexLookup | None = None
) -> VerifyResult:
    """Check one stored Wiktionary link against the dump index (see the module docstring).

    The link is found by the importer's own relationship id: an edge of the right page and
    template that the importer's functions turn into exactly the stored id. The stored words,
    type, rank, label and evidence must then agree with that edge."""
    from app.importers.wiktionary import COGNATE, page_url

    res = VerifyResult(ln["id"], "wiktionary")
    page_word, _, template = (ln["record"] or "").rpartition("#")
    if not page_word or not template:
        res.reasons = ["record_is_not_page#template"]
        return res
    src_key, tgt_key = ln["src"]["rec"] or "", ln["tgt"]["rec"] or ""
    if ":" not in src_key or ":" not in tgt_key:
        res.reasons = ["lexeme_record_is_not_a_wiktionary_key"]
        return res
    cognate = template in COGNATE
    keys = [tgt_key] if template == "desc" else [src_key, tgt_key] if cognate else [src_key]
    recs: dict[int, dict] = {}
    for k in keys:
        for r in idx.by_key(k):
            recs[r["_off"]] = r
    # the page's other entries: a nested descendant sits on the top ancestor's page, and a
    # lexeme merged into a same-spelling one is no longer under its own key
    for r in idx.by_title(normalize_form(clean_form(page_word))):
        recs.setdefault(r["_off"], r)
    if not recs:
        res.reasons = ["entry_not_in_dump"]
        return res
    matched, other_template, lang_differs = [], False, False
    for r in recs.values():
        _, pairs = rec_edges(r)
        for edge, _other in pairs:
            if edge.word != page_word:
                continue
            if edge_rid(edge)[0] == ln["id"]:
                if edge.template == template:
                    matched.append((edge, r, pairs))
                else:
                    other_template = True
            elif (
                edge.template == template
                and edge.parent.split(":", 1)[1] == tgt_key.split(":", 1)[1]
                and (cognate or edge.child == src_key)
            ):
                lang_differs = True
    if not matched:
        if other_template:
            res.reasons = ["template_differs_from_the_one_in_the_dump"]
        elif lang_differs:
            res.reasons = ["target_word_found_only_in_another_language"]
        else:
            res.reasons = ["target_word_not_in_entry_templates_or_descendants"]
        return res
    # The type is decided for the link as a whole: the importer retypes every copy of a link
    # (the same pair in several lines or templates) when one copy meets the text rule.
    retyped = (ln.get("label") or "").endswith(RETYPE_LABEL)
    type_problem: str | None = None
    if retyped or all(ln["type"] != e.type_id for e, _, _ in matched):
        problems = [_retype_problem(ln, e, r, p, idx, names) for e, r, p in matched]
        type_problem = None if None in problems else problems[0]
        if ln["type"] == matched[0][0].type_id and retyped:
            type_problem = "label_says_retyped_but_type_unchanged"
    best: list[str] | None = None
    for edge, _r, _pairs in matched:
        why: list[str] = []
        _, a, b = edge_rid(edge)
        probe = VerifyResult(ln["id"], "wiktionary")
        why += _side_problems("src", a, ln, lex, probe)
        why += _side_problems("tgt", b, ln, lex, probe)
        if type_problem:
            why.append(type_problem)
        if ln.get("rank") != edge.rank:
            why.append("rank_differs")
        expect = "{{" + template + "}}" + (f" ({edge.variety})" if edge.variety else "")
        if (ln.get("label") or "") != expect + (RETYPE_LABEL if retyped else ""):
            why.append("label_differs")
        locators = {loc for _, loc in ln["evidence"] if loc}
        if not ln["evidence"]:
            why.append("no_evidence_row")
        elif page_url(page_word) not in locators:
            why.append("evidence_locator_is_not_the_page")
        elif any(
            c != _citation(page_word, template, ln["type"], retyped) for c, _ in ln["evidence"]
        ):
            why.append("evidence_citation_differs")
        if best is None or len(why) < len(best):
            best = why
            res.detail = probe.detail
        if not why:
            break
    res.reasons = best or []
    res.status = "pass" if not res.reasons else "fail"
    if res.status == "pass":
        res.detail.update(page=page_word, template=template)
    return res


# ---------------------------------------------------------------------------- Wikidata

WD_PROPS = {"P5191": "etymon", "P5238": "has_component"}


def _wd_reduce(e: dict) -> tuple[str, bytes] | None:
    from app.importers.wikidata_lexemes import reference_note, statement_targets

    lemmas = {c: v["value"] for c, v in (e.get("lemmas") or {}).items()}
    claims = []
    for prop in WD_PROPS:
        for rank, (other, st) in enumerate(statement_targets(e, prop), start=1):
            locator, _ = reference_note(st)
            claims.append([prop, st["id"], other, rank, 1 if st.get("references") else 0, locator])
    if not lemmas and not claims:
        return None
    rec = {"l": lemmas, "c": claims}
    return e["id"], json.dumps(rec, ensure_ascii=False, separators=(",", ":")).encode()


def _wd_work(batch: list[bytes]):
    out = []
    for line in batch:
        line = line.strip().rstrip(b",")
        if not line.startswith(b"{"):
            continue
        try:
            r = _wd_reduce(json.loads(line))
        except (ValueError, KeyError):
            continue
        if r:
            out.append(r)
    return len(batch), out


def build_wikidata_index(
    dump: Path, out: Path, workers: int = 6, log: Callable[[str], None] = lambda m: None
) -> dict:
    """One pass over the lexeme dump (.json.bz2 or plain) into ``wikidata.sqlite``: one row per
    lexeme with its lemmas and its P5191 / P5238 statements (id, target, rank, reference)."""
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "wikidata.sqlite"
    db_path.unlink(missing_ok=True)
    db = sqlite3.connect(db_path)
    db.executescript(
        "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
        "CREATE TABLE lex (id TEXT PRIMARY KEY, data TEXT) WITHOUT ROWID;"
        "CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);"
    )
    opener = bz2.open if dump.suffix == ".bz2" else open
    t0, lines, kept = time.time(), 0, 0
    with opener(dump, "rb") as fh, Pool(workers) as pool:
        for n, rows in pool.imap(_wd_work, _batches(fh, 2000, None)):
            lines += n
            kept += len(rows)
            db.executemany(
                "INSERT OR REPLACE INTO lex VALUES (?,?)", [(i, d.decode()) for i, d in rows]
            )
            if lines % 200_000 < 2000:
                log(f"{lines:,} lines, {kept:,} kept, {time.time() - t0:.0f}s")
    meta = {
        "dump": dump.name,
        "dump_bytes": str(dump.stat().st_size),
        "dump_mtime": str(int(dump.stat().st_mtime)),
        "lines": str(lines),
        "kept": str(kept),
    }
    db.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    db.commit()
    db.close()
    return meta


class WikidataIndex:
    def __init__(self, directory: Path) -> None:
        self.db = sqlite3.connect(f"file:{directory / 'wikidata.sqlite'}?mode=ro", uri=True)
        self.meta = dict(self.db.execute("SELECT k, v FROM meta"))

    def get(self, lexeme: str) -> dict | None:
        row = self.db.execute("SELECT data FROM lex WHERE id = ?", (lexeme,)).fetchone()
        return json.loads(row[0]) if row else None

    def stale_reason(self, dump: Path) -> str | None:
        if dump.exists() and self.meta.get("dump_bytes") != str(dump.stat().st_size):
            return "index was built from a dump of a different size"
        return None

    def close(self) -> None:
        self.db.close()


def wikidata_index_dir(scratch: Path | None = None) -> Path:
    return (scratch or scratch_root()) / "d2_wikidata"


def check_wikidata(ln: dict, idx: WikidataIndex) -> VerifyResult:
    res = VerifyResult(ln["id"], "wikidata-lexemes")
    why: list[str] = []
    statement = ln["record"] or ""
    lex_id = statement.split("$", 1)[0]
    src, tgt = idx.get(lex_id), idx.get(ln["tgt"]["rec"] or "")
    if src is None:
        res.reasons = ["source_lexeme_not_in_dump"]
        return res
    claim = next((c for c in src["c"] if c[1] == statement), None)
    if claim is None:
        res.reasons = ["statement_not_on_the_source_lexeme"]
        return res
    prop, _, other, rank, refs, locator = claim
    if ln["src"]["rec"] != lex_id:
        why.append("source_lexeme_differs_from_the_statement_owner")
    if other != ln["tgt"]["rec"]:
        why.append("statement_points_to_another_lexeme")
    if WD_PROPS[prop] != ln["type"]:
        why.append(f"type_differs:{ln['type']}!={WD_PROPS[prop]}")
    if ln["id"] != relationship_id("wikidata-lexemes", statement):
        why.append("relationship_id_differs")
    if ln["src_id"] != lexeme_id("wikidata-lexemes", lex_id):
        why.append("source_lexeme_id_differs")
    if ln["tgt_id"] != lexeme_id("wikidata-lexemes", ln["tgt"]["rec"] or ""):
        why.append("target_lexeme_id_differs")
    if ln.get("rank") != rank:
        why.append("rank_differs")
    from app.importers.wikidata_lexemes import PROPERTY_LABELS

    if ln.get("label") != f"{prop} {PROPERTY_LABELS[prop]}":
        why.append("label_differs")
    if not ln["evidence"]:
        why.append("no_evidence_row")
    elif all((loc or None) != locator for _, loc in ln["evidence"]):
        why.append("evidence_reference_differs")
    elif any(c != f"Wikidata {statement}" for c, _ in ln["evidence"]):
        why.append("evidence_citation_differs")
    for side, rec in (("src", src), ("tgt", tgt)):
        if rec is None:
            why.append(f"{side}_lexeme_not_in_dump")
        elif ln[side]["form"] not in {clean_form(v) for v in rec["l"].values()}:
            why.append(f"{side}_form_is_not_a_lemma_of_the_lexeme")
    res.reasons = why
    res.status = "pass" if not why else "fail"
    if not why:
        res.detail.update(statement=statement, property=prop)
    return res


# ---------------------------------------------------------------------------- re-derivation


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *a, **k):
        return self

    def executemany(self, *a, **k):
        return self

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return []


class _CaptureConn:
    """Stands in for the database connection of an importer: nothing is written."""

    def cursor(self) -> _Cursor:
        return _Cursor()


def _run_importer(dataset: str, conn, raw: Path) -> dict[str, list[dict]]:
    """Run a dataset's importer on its raw files with COPY calls captured, so every lexeme,
    relationship and evidence row it would write is returned as a dict."""
    mod = importlib.import_module(f"app.importers.{DERIVED.get(dataset, dataset)}")
    captured: dict[str, list[dict]] = defaultdict(list)

    def capture(cur, table, columns, rows):
        captured[table].extend(dict(zip(columns, r, strict=False)) for r in rows)

    stub = _CaptureConn()
    with mock.patch.object(mod, "copy_rows", capture):
        if dataset == "cdsl-mw":
            mod.import_cdsl_mw(stub, raw / "cdsl" / "mw.txt", "d2")
        elif dataset == "dpd":
            mod.import_dpd(stub, raw / "dpd" / "x" / "dpd.db", None, "d2")
        elif dataset == "valyrian":
            mod.import_valyrian(stub, raw / "valyrian", "d2")
        elif dataset == "jambu":
            mod.JambuImporter(
                stub, raw / "jambu" / "cldf", raw / "jambu-lfs" / "forms.csv", "d2",
                all_languages=True,
            ).run()  # fmt: skip
        elif dataset == "starling":
            from app.importers.wiktionary import wiktionary_code_map
            from app.pipeline.languages import Glottolog

            gl = raw / "glottolog-cldf" / "cldf"
            names = mod.name_languages_from_glottolog(conn, Glottolog(gl)) if gl.exists() else {}
            archives = list(source_files("starling", raw).values())
            mod.import_starling(stub, archives, "d2", wiktionary_code_map(), names, None)
        else:
            raise ValueError(dataset)
    return captured


class Derived:
    """What an importer produces from the raw files: relationships by id, lexemes by id and
    evidence by relationship id."""

    def __init__(self, captured: dict[str, list[dict]]) -> None:
        self.rels = {
            r["id"]: (
                r["source_lexeme_id"], r["target_lexeme_id"], r["type_id"],
                r.get("source_record_id"), r.get("original_label"),
                None if r.get("rank") in (None, "") else str(r["rank"]),
            )
            for r in captured["relationship"]
        }  # fmt: skip
        self.lex = {x["id"]: (x["form"], x.get("source_record_id")) for x in captured["lexeme"]}
        ev: dict[str, list] = defaultdict(list)
        for e in captured["evidence"]:
            ev[e["relationship_id"]].append((e["citation"], e.get("locator") or None))
        self.evidence = {k: sorted(v, key=repr) for k, v in ev.items()}


def derived_for(dataset: str, conn, raw: Path, scratch: Path | None = None) -> Derived:
    """The re-derivation, cached on disk by the size and mtime of the raw files and importer."""
    base = scratch or scratch_root()
    mod_file = Path(
        importlib.import_module(f"app.importers.{DERIVED.get(dataset, dataset)}").__file__
    )
    files = [p for p in source_files(dataset, raw).values() if p.exists()]
    if dataset == "valyrian":
        files = [p for p in (raw / "valyrian").glob("*.html")][:50] + files
        files.append(raw / "valyrian" / "pages")
    elif dataset == "dpd":
        files.append(raw / "dpd" / "x" / "dpd.db")
    stamp = repr([(str(p), *_stamp(p)) for p in files if p.exists()] + [_stamp(mod_file)])
    stamp = hashlib.sha1(stamp.encode()).hexdigest()
    cache = base / "d2_derived" / f"{dataset}.pkl"
    try:
        with cache.open("rb") as fh:
            got = pickle.load(fh)
        if got[0] == stamp:
            return got[1]
    except (OSError, pickle.UnpicklingError, EOFError):
        pass
    derived = Derived(_run_importer(dataset, conn, raw))
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as fh:
            pickle.dump((stamp, derived), fh, protocol=pickle.HIGHEST_PROTOCOL)
    except OSError:
        pass
    return derived


def check_derived(ln: dict, d: Derived) -> VerifyResult:
    res = VerifyResult(ln["id"], ln["dataset"])
    got = d.rels.get(ln["id"])
    if got is None:
        res.reasons = ["link_not_produced_from_the_raw_file"]
        return res
    src_id, tgt_id, type_id, record, label, rank = got
    why: list[str] = []
    if ln["src_id"] != src_id:
        why.append("source_word_differs")
    if ln["tgt_id"] != tgt_id:
        why.append("target_word_differs")
    if ln["type"] != type_id:
        why.append(f"type_differs:{ln['type']}!={type_id}")
    if (ln["record"] or None) != (record or None):
        why.append("source_record_differs")
    if (ln.get("label") or None) != (label or None):
        why.append("label_differs")
    if rank is not None and str(ln.get("rank")) != rank:
        why.append("rank_differs")
    mine = sorted(((c, loc or None) for c, loc in ln["evidence"]), key=repr)
    if mine != d.evidence.get(ln["id"], []):
        why.append("evidence_differs")
    for side, lid in (("src", src_id), ("tgt", tgt_id)):
        form, rec = d.lex.get(lid, (None, None))
        if form is None:
            why.append(f"{side}_word_not_in_source")
        else:
            if ln[side]["form"] != form:
                why.append(f"{side}_form_differs")
            if ln[side]["rec"] != rec:
                why.append(f"{side}_record_differs")
    res.reasons = why
    res.status = "pass" if not why else "fail"
    if not why:
        res.detail.update(record=ln["record"], rederived_from="raw file")
    return res


# ---------------------------------------------------------------------------- dispatcher


def verify_group(
    conn, dataset: str, group: list[dict], raw: Path, scratch: Path | None = None
) -> dict[str, VerifyResult]:
    """Verify the links of one dataset from the raw files; every link gets a result."""

    def all_with(status: str, reason: str) -> dict[str, VerifyResult]:
        return {ln["id"]: VerifyResult(ln["id"], dataset, status, [reason]) for ln in group}

    usable, why = source_state(conn, dataset, raw)
    if not usable:
        return all_with("unsupported", why)
    base = scratch or scratch_root()
    if dataset == "wiktionary":
        d = wiktionary_index_dir(scratch)
        if not (d / "index.sqlite").exists():
            return all_with(
                "unsupported",
                "no Wiktionary index (build it with verify_sources.build_wiktionary_index)",
            )
        idx = WiktionaryIndex(d)
        try:
            stale = idx.stale_reason(next(iter(source_files(dataset, raw).values())))
            if stale:
                return all_with("unsupported", stale)
            from app.importers.wiktionary import load_iso_names

            iso = raw / "iso639" / "iso-639-3.tab"
            names = {**(load_iso_names(iso) if iso.exists() else {}), **idx.names}
            lex = LexLookup(conn)
            return {ln["id"]: check_wiktionary(ln, idx, names, lex) for ln in group}
        finally:
            idx.close()
    if dataset == "wikidata-lexemes":
        d = wikidata_index_dir(scratch)
        if not (d / "wikidata.sqlite").exists():
            return all_with("unsupported", "no Wikidata index (build_wikidata_index)")
        widx = WikidataIndex(d)
        try:
            stale = widx.stale_reason(next(iter(source_files(dataset, raw).values())))
            if stale:
                return all_with("unsupported", stale)
            return {ln["id"]: check_wikidata(ln, widx) for ln in group}
        finally:
            widx.close()
    try:
        derived = derived_for(dataset, conn, raw, base)
    except (OSError, sqlite3.Error) as exc:
        return all_with("unsupported", f"raw file needed to re-read {dataset} is missing: {exc}")
    return {ln["id"]: check_derived(ln, derived) for ln in group}


def summarise(results: dict[str, VerifyResult]) -> Counter:
    """Failure reasons over a batch, one count per reason."""
    c: Counter = Counter()
    for r in results.values():
        for why in r.reasons if r.status == "fail" else ():
            c[why.split(":", 1)[0]] += 1
    return c
