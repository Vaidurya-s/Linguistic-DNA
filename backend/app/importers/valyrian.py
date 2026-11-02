"""Import the Valyrian languages (David J. Peterson's High Valyrian and its Low Valyrian
descendants) from pages of The Languages of David J. Peterson wiki, saved by
scripts/fetch_valyrian.py into data/raw/valyrian/ (research use, never redistributed).

These are **constructed, fictional languages** (created for HBO's Game of Thrones and House of
the Dragon). They get their own family, "Valyrian languages (constructed, fictional)", are never
merged with or linked to natural languages, and every record says so in its citation.

- The dictionary pages (a table of every term with its definition) give the words and glosses.
- Each saved word page adds, per language section: the headword, up to three definitions,
  the Etymology (a term in the same language: ``has_component`` when the etymology combines
  terms with "+", otherwise ``derived_form``; a term in another Valyrian language:
  ``inherited_form``, or ``borrowed_from`` when the text says borrowed) and the Descendants list
  (each descendant ``inherited_form`` from the word).

Every relationship cites the wiki page and, when the saved page records it, its revision.
"""

import html
import json
import re
import urllib.parse
from pathlib import Path

import psycopg

from app.importers.common import copy_rows
from app.models.enums import ReconstructionStatus
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "valyrian"
SOURCE_ID = "languageinvention-valyrian"
BASE = "https://wiki.languageinvention.com"
FAMILY_ID = "conlang-valyrian"
FAMILY_NAME = "Valyrian languages (constructed, fictional)"
GROUP = "Valyrian (constructed)"
NAMES = {
    "hval": "High Valyrian",
    "asta": "Astapori Valyrian",
    "meer": "Meereenese Valyrian",
    "vola": "Volantene Valyrian",
}
CODE_OF = {v: k for k, v in NAMES.items()}
MIN_WORDS = 200  # like natural languages: searchable from 200 words

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

_TAG = re.compile(r"<[^>]+>")
_H2 = re.compile(r'<div class="mw-heading mw-heading2"><h2 id="[^"]*">(.*?)</h2></div>', re.S)
_HEADING = re.compile(
    r'<div class="mw-heading mw-heading(\d)"><h\d id="([^"]*)">(.*?)</h\d></div>', re.S
)
_HEADWORD = re.compile(r'<strong class="[^"]*headword" lang="(\w+)">(.*?)</strong>', re.S)
_MENTION = re.compile(
    r'<(?:i|span) class="[^"]*" lang="(\w+)"><a href="([^"]+)"[^>]*>(.*?)</a></(?:i|span)>'
    r'(?:\s*<span class="mention-gloss-paren[^>]*>\(</span>'
    r'<span class="mention-gloss-double-quote">“</span><span class="mention-gloss">(.*?)</span>)?',
    re.S,
)
_ROW = re.compile(
    r'<td><b><a href="([^"]+)" title="([^"]+)">(.*?)</a></b><span id="([^"]*)"></span></td>'
    r"\s*<td>(.*?)</td>",
    re.S,
)
_OLDID = re.compile(r"oldid=(\d+)")


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub("", fragment))).strip()


def page_title(href: str) -> str:
    """Wiki page title from a link: /Hepagon#High_Valyrian or /index.php?title=-vo&..."""
    if href.startswith("/index.php?"):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(href)).query)
        return query.get("title", [""])[0]
    return urllib.parse.unquote(href.lstrip("/").split("#")[0]).replace("_", " ")


def parse_dictionary(page: str) -> list[tuple[str, str, str]]:
    """(page title, lemma, definition) for every row of a dictionary table. The table shows
    terms capitalised; the row anchor has the lemma's spelling in lower case."""
    out = []
    for _href, title, _shown, anchor, definition in _ROW.findall(page):
        out.append((html.unescape(title), html.unescape(anchor), text(definition)[:300]))
    return out


def sections(page: str) -> list[tuple[str, str]]:
    """(language name, HTML) for each level-2 language section of a word page."""
    parts = _H2.split(page)
    return [(text(parts[i]), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def subsections(body: str) -> list[tuple[str, str]]:
    """(heading id, HTML up to the next heading) within a language section."""
    parts = _HEADING.split(body)
    return [(parts[i + 1], parts[i + 3]) for i in range(1, len(parts) - 3, 4)]


def definitions(fragment: str) -> list[str]:
    ol = re.search(r"<ol>(.*?)</ol>", fragment, re.S)
    if not ol:
        return []
    items = re.findall(r"<li>(.*?)(?:<dl>|</li>)", ol.group(1), re.S)
    return [t for t in (text(i) for i in items) if t][:3]


def parse_page(page: str) -> list[dict]:
    """One dict per language section: code, headword, glosses, etymology mentions and text,
    descendants."""
    out = []
    for lang_name, body in sections(page):
        code = CODE_OF.get(lang_name)
        hw = _HEADWORD.search(body)
        if not code and hw:
            code = hw.group(1)
        if not code or not hw:
            continue
        entry = {
            "code": code,
            "headword": text(hw.group(2)),
            "glosses": definitions(body[hw.end() :]),
            "etymology": [],
            "descendants": [],
        }
        for heading, chunk in subsections(body):
            if heading.startswith("Etymology"):
                para = re.search(r"<p>(.*?)</p>", chunk, re.S)
                if para:
                    entry["etymology"].append(
                        (
                            text(para.group(1)),
                            [
                                (m_code, page_title(href), text(form), text(gloss or ""))
                                for m_code, href, form, gloss in _MENTION.findall(para.group(1))
                            ],
                        )
                    )
            elif heading.startswith("Descendants"):
                for li in re.findall(r"<li>(.*?)</li>", chunk, re.S):
                    for m_code, href, form, _gloss in _MENTION.findall(li):
                        entry["descendants"].append(
                            (m_code, page_title(href), text(form), "borrow" in li.lower())
                        )
        out.append(entry)
    return out


def import_valyrian(conn: psycopg.Connection, raw: Path, version: str) -> dict:
    stats: dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        stats[k] = stats.get(k, 0) + n

    def key(code: str, form: str) -> str:
        return f"{code}:{normalize_form(form).lower()}"

    lexemes: dict[str, dict] = {}  # key -> code, form, gloss, page, is_entry
    rels: dict[str, tuple] = {}
    evidence: list[tuple] = []
    codes: set[str] = set()

    def add(code, form, gloss, page, is_entry) -> str:
        k = key(code, form)
        codes.add(code)
        cur = lexemes.get(k)
        if cur is None or (is_entry and not cur["is_entry"]):
            lexemes[k] = {
                "code": code,
                "form": form,
                "gloss": gloss or (cur or {}).get("gloss"),
                "page": page,
                "is_entry": is_entry,
            }
        elif not cur["gloss"] and gloss:
            cur["gloss"] = gloss
        return k

    def cite(page: str, oldid: str | None) -> tuple[str, str]:
        title = page.replace(" ", "_")
        url = (
            f"{BASE}/index.php?title={urllib.parse.quote(title)}&oldid={oldid}"
            if oldid
            else f"{BASE}/{urllib.parse.quote(title)}"
        )
        return (
            f"The Languages of David J. Peterson (wiki), “{page}” "
            "(constructed language, fictional)",
            url,
        )

    def link(child: str, parent: str, type_id: str, label: str, page: str, oldid, rank) -> None:
        if child == parent:
            return
        rid = relationship_id(DATASET, type_id, child, parent)
        if rid in rels:
            return
        citation, locator = cite(page, oldid)
        rels[rid] = (
            rid,
            lexeme_id(DATASET, child),
            lexeme_id(DATASET, parent),
            type_id,
            "directed",
            "documented",
            SOURCE_ID,
            f"{page}#{label}",
            label,
            rank,
            "constructed language",
            DATASET,
        )
        evidence.append((rid, SOURCE_ID, citation, locator, None))
        bump(type_id)

    # dictionaries: every term and its definition
    for path in sorted(raw.glob("*_Dictionary.html")):
        lang_name = path.stem.replace("_Dictionary", "").replace("_", " ")
        code = CODE_OF.get(lang_name)
        if not code:
            continue
        for title, lemma, definition in parse_dictionary(path.read_text(encoding="utf-8")):
            add(code, lemma, definition, title, True)
            bump(f"dictionary:{code}")

    # word pages: headwords, etymologies and descendants
    for path in sorted((raw / "pages").glob("*.html")):
        page = path.read_text(encoding="utf-8")
        title = urllib.parse.unquote(path.stem).replace("_", " ")
        oldid_m = _OLDID.search(page)
        oldid = oldid_m.group(1) if oldid_m else None
        bump("pages")
        for entry in parse_page(page):
            code = entry["code"]
            gloss = "; ".join(entry["glosses"]) or None
            # the page's headword gives the true spelling (capitals of proper nouns)
            k = key(code, entry["headword"])
            if k in lexemes:
                lexemes[k]["form"] = entry["headword"]
                lexemes[k]["page"] = title
            this = add(code, entry["headword"], gloss, title, True)
            for rank, (etext, mentions) in enumerate(entry["etymology"], start=1):
                combined = "+" in etext
                borrowed = "borrow" in etext.lower()
                for m_code, m_page, m_form, m_gloss in mentions:
                    if not m_form or m_code == "en":
                        continue
                    other = add(m_code, m_form, m_gloss or None, m_page, False)
                    if m_code != code:
                        type_id = "borrowed_from" if borrowed else "inherited_form"
                    else:
                        type_id = "has_component" if combined else "derived_form"
                    link(this, other, type_id, "Etymology", title, oldid, rank)
            for rank, (d_code, d_page, d_form, borrowed) in enumerate(
                entry["descendants"], start=1
            ):
                if not d_form or d_code == code:
                    continue
                desc = add(d_code, d_form, None, d_page, False)
                link(
                    desc,
                    this,
                    "borrowed_from" if borrowed else "inherited_form",
                    "Descendants",
                    title,
                    oldid,
                    rank,
                )

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb(
                    json.loads((raw / "manifest.json").read_text())
                    if (raw / "manifest.json").exists()
                    else {}
                ),
                psycopg.types.json.Jsonb(
                    [
                        "Dictionary tables -> terms with definitions",
                        "Word pages -> headwords, etymologies (components, derivations, "
                        "inheritance from High Valyrian) and descendants",
                        "Constructed, fictional languages in their own family; never merged "
                        "with natural languages",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))
        cur.execute(
            "INSERT INTO language_family (id, name, level, source_id) VALUES (%s, %s, 'family',"
            " %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
            (FAMILY_ID, FAMILY_NAME, SOURCE_ID),
        )
        per_language: dict[str, int] = {}
        for lx in lexemes.values():
            per_language[lx["code"]] = per_language.get(lx["code"], 0) + 1
        for code in sorted(codes):
            cur.execute(
                "INSERT INTO language (id, name, family_id, role, is_proto, is_enabled,"
                " metadata_json) VALUES (%s, %s, %s, 'other', false, %s, %s)"
                " ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name,"
                " family_id = EXCLUDED.family_id, is_enabled = EXCLUDED.is_enabled,"
                " metadata_json = EXCLUDED.metadata_json",
                (
                    f"conlang-{code}",
                    NAMES.get(code, f"Valyrian ({code})"),
                    FAMILY_ID,
                    per_language.get(code, 0) >= MIN_WORDS,
                    psycopg.types.json.Jsonb(
                        {
                            "group": GROUP,
                            "constructed": True,
                            "fictional": True,
                            "creator": "David J. Peterson",
                            "wiki_code": code,
                        }
                    ),
                ),
            )
        rows = []
        for k, lx in lexemes.items():
            lang = f"conlang-{lx['code']}"
            form = lx["form"]
            citation, _ = cite(lx["page"], None)
            rows.append(
                (
                    lexeme_id(DATASET, k),
                    lang,
                    form,
                    normalize_form(form),
                    lexeme_search_key(form, lang),
                    form,
                    "source",
                    lx["gloss"],
                    form_kind(form, False).value,
                    (
                        ReconstructionStatus.attested
                        if lx["is_entry"]
                        else ReconstructionStatus.unknown
                    ).value,
                    DATASET,
                    SOURCE_ID,
                    k,
                    citation,
                    batch,
                )
            )
        copy_rows(cur, "lexeme", LEXEME_COLS, rows)
        copy_rows(cur, "relationship", REL_COLS, (r + (batch,) for r in rels.values()))
        copy_rows(cur, "evidence", EVIDENCE_COLS, evidence)
        stats.update(lexemes=len(rows), relationships=len(rels))
        stats.update({f"words:{c}": n for c, n in per_language.items()})
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(stats), batch),
        )
    return {"batch_id": batch, **stats}
