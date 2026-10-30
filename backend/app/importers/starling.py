"""Import the StarLing ("Tower of Babel") etymological databases (research use).

The downloadable archives (https://starlingdb.org/downl.php, e.g. IE.exe, ALTAIC.exe) are
self-extracting ZIP files of StarLing databases. Each database is a dBase III ``.dbf`` with
fixed-width records; text fields are 6-byte pointers (uint32 offset, uint16 length) into a
``.var`` file, and an ``.inf`` file names the fields (``field_alias[HITT] = \\1:Hittite``) and
the databases their number fields link to (``slav = \\data\\ie\\vasmer``). Text is in
StarLing's own encoding (``app.importers.starling_charset``).

What becomes what (data/config/starling.csv says which database is which):

- an etymology record -> a reconstructed word in the database's proto-language;
- each reflex field (Hittite, Old Indian, Gothic ...) -> one word per ``;``-separated
  segment, linked to the proto-form as ``etymon`` ("from"; StarLing gives reflexes, not
  whether a word was inherited or borrowed). Field names and the abbreviations that start a
  segment in mixed fields ("Other Iranian") resolve to languages through
  data/config/starling_languages.csv; anything unresolved is reported, not guessed;
- a number field linking a subordinate database to its main one (germet -> piet) -> an
  ``etymon`` link from the subordinate proto-form to the main one; links within the
  Altaic databases carry a note that the Altaic family is a contested hypothesis;
- Vasmer's dictionary -> Russian headwords (stress kept in ``native_form``), linked to the
  PIE root that cites them; Pokorny's dictionary -> page references for the PIE links.

Dictionary prose (Vasmer's and Trubachev's articles, Pokorny's material, comments) is not
stored: only forms, short glosses and page references, each cited to its database.
"""

import csv
import re
import struct
import unicodedata
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import psycopg

from app.config import REPO_ROOT
from app.importers.common import copy_rows, sha256_file
from app.importers.starling_charset import ESCAPED, GREEK, OCS, SINGLE
from app.models.enums import ReconstructionStatus
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "starling"
CONFIG = REPO_ROOT / "data" / "config" / "starling.csv"
LANGUAGES = REPO_ROOT / "data" / "config" / "starling_languages.csv"
CONTESTED_NOTE = "Altaic hypothesis (contested); StarLing links these as one family."

# ---------------------------------------------------------------- encoding

# Greek codes that stand for an accent only (drawn on an alpha in Brouwer's table)
_GREEK_ACCENTS = {
    0x90,
    0x91,
    0x92,
    0x93,
    0x9A,
    0x9B,
    0x9C,
    0x9D,
    0xA0,
    0xA1,
    0xA3,
    0xC0,
    0xC1,
    0xDC,
}
_MARKUP = re.compile(r"\\[A-Za-z]")


def _greek(b: int) -> str | None:
    ch = GREEK.get(b)
    if ch and b in _GREEK_ACCENTS:
        return unicodedata.normalize("NFD", ch)[1:]
    return ch


def decode_starling(raw: bytes, misses: Counter | None = None) -> str:
    """StarLing bytes -> Unicode (NFC), markup such as \\I...\\i removed."""
    out: list[str] = []
    i, n, double = 0, len(raw), False
    while i < n:
        b = raw[i]
        nxt = raw[i + 1] if i + 1 < n else None
        if b == 0x01:  # double-byte mode until the next ASCII byte
            double = True
            i += 1
            continue
        if b == 0x7F:
            i += 1
            continue
        if b < 0x80:
            double = False
            if b == 0x1D and nxt is not None:  # escape: the next byte is a special symbol
                out.append(ESCAPED.get(nxt, "�"))
                if nxt not in ESCAPED and misses is not None:
                    misses[f"escape 0x{nxt:02x}"] += 1
                i += 2
                continue
            if b in SINGLE:  # ^ and ~ are combining accents
                out.append(SINGLE[b])
            elif b in (0x0A, 0x0D, 0x15, 0x09):
                out.append(" ")
            elif b >= 0x20:
                out.append(chr(b))
            i += 1
            continue
        # Greek and OCS pairs; outside double-byte mode only where the second byte cannot
        # be Cyrillic (so that "Где" stays Russian)
        if double and 0xA1 <= b <= 0xF9 and nxt is not None and 0x40 <= nxt <= 0x7E:
            try:  # Big5 (Chinese characters); its second byte may be in the ASCII range
                out.append(bytes((b, nxt)).decode("big5"))
                i += 2
                continue
            except UnicodeDecodeError:
                pass
        if nxt is not None and nxt >= 0x80 and (double or 0xB0 <= nxt <= 0xDF):
            pair = None
            if b == 0x83:
                pair = _greek(nxt)
            elif b == 0x85 and nxt == 0xAF:
                pair = "ϝ"  # digamma
            elif b == 0x87:
                pair = OCS.get(nxt)
            elif b == 0x88:
                pair = {0x81: "ѵ", 0x83: "ѧ"}.get(nxt)
            elif double and 0xA1 <= b <= 0xF9:
                try:
                    pair = bytes((b, nxt)).decode("big5")
                except UnicodeDecodeError:
                    pair = None
            if pair is not None:
                out.append(pair)
                i += 2
                continue
            if double:
                if misses is not None:
                    misses[f"pair 0x{b:02x}{nxt:02x}"] += 1
                out.append("�")
                i += 2
                continue
        if b in SINGLE:
            out.append(SINGLE[b])
        elif b <= 0xAF or 0xE0 <= b <= 0xEF:
            out.append(bytes((b,)).decode("cp866"))
        else:
            out.append("�")
            if misses is not None:
                misses[f"byte 0x{b:02x}"] += 1
        i += 1
    text = _MARKUP.sub("", "".join(out))
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text)).strip()


# ---------------------------------------------------------------- files


@dataclass
class Field:
    name: str
    kind: str  # dBase type: C (text pointer), N (number) ...
    length: int


@dataclass
class Database:
    name: str
    fields: list[Field]
    records: list[dict[str, bytes | str]]  # text fields as raw bytes, numbers as str
    aliases: dict[str, str]  # field -> English alias
    links: dict[str, str]  # link key (lower case) -> database name
    checksum: str


def read_dbf(dbf: bytes, var: bytes) -> tuple[list[Field], list[dict]]:
    nrec, hlen, rlen = struct.unpack("<IHH", dbf[4:12])
    fields, off = [], 32
    while off < hlen and dbf[off] != 0x0D:
        name = dbf[off : off + 11].split(b"\0")[0].decode("latin-1")
        fields.append(Field(name, chr(dbf[off + 11]), dbf[off + 16]))
        off += 32
    records = []
    for i in range(nrec):
        row = dbf[hlen + i * rlen : hlen + (i + 1) * rlen]
        if not row or row[:1] == b"*":  # deleted
            continue
        rec, p = {}, 1
        for f in fields:
            cell = row[p : p + f.length]
            p += f.length
            if f.kind == "C" and f.length == 6:
                if cell.strip(b" \0"):
                    o, ln = struct.unpack("<IH", cell)
                    rec[f.name] = var[o : o + ln]
                else:
                    rec[f.name] = b""
            else:
                rec[f.name] = cell.decode("latin-1").strip()
        records.append(rec)
    return fields, records


_ALIAS = re.compile(r"field_alias\[(\w+)\]\s*=\s*(.*)")
_LINK = re.compile(r"^(\w+)\s*=\s*\S*?([\w-]+)(?:\.dbf)?\s*$", re.I)


def read_inf(inf: bytes) -> tuple[dict[str, str], dict[str, str]]:
    """(field -> English alias, link key -> database name) from a .inf file."""
    aliases, links = {}, {}
    for line in inf.decode("cp866", "replace").splitlines():
        line = line.strip()
        if m := _ALIAS.match(line):
            value = m.group(2)
            english = re.search(r"\\1:([^\\]*)", value)
            aliases[m.group(1).upper()] = (english.group(1) if english else value).strip()
        elif (m := _LINK.match(line)) and ("\\" in line or "/" in line):
            links[m.group(1).lower()] = m.group(2).lower()
    return aliases, links


def open_archives(paths: Iterable[Path]) -> dict[str, Database]:
    """Every database (by lower-case name) in the given archives (.exe or .zip)."""
    out = {}
    for path in paths:
        checksum = sha256_file(path)
        with zipfile.ZipFile(path) as z:
            members = {m.lower(): m for m in z.namelist() if "lexstat/" not in m.lower()}
            for member in members:
                if not member.endswith(".dbf"):
                    continue
                name = Path(member).stem
                var = (
                    z.read(members[f"{member[:-4]}.var"])
                    if f"{member[:-4]}.var" in members
                    else b""
                )
                fields, records = read_dbf(z.read(members[member]), var)
                inf = members.get(f"{member[:-4]}.inf")
                aliases, links = read_inf(z.read(inf)) if inf else ({}, {})
                out[name] = Database(name, fields, records, aliases, links, checksum)
    return out


# ---------------------------------------------------------------- configuration


@dataclass
class DbConfig:
    db: str
    archive: str
    kind: str  # etymology | dictionary | vasmer | pokorny | skip
    code: str  # Wiktionary code of the proto-language (or the dictionary's language)
    parent: str
    contested: bool
    title: str
    compilers: str


def load_config(path: Path = CONFIG) -> dict[str, DbConfig]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {
            r["db"]: DbConfig(
                r["db"],
                r["archive"],
                r["kind"],
                r["code"],
                r["parent"],
                r["contested"] == "yes",
                r["title"],
                r["compilers"],
            )
            for r in csv.DictReader(fh)
        }


def load_language_names(path: Path = LANGUAGES) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["name_or_abbreviation"]: r["wiktionary_code"] for r in csv.DictReader(fh)}


# ---------------------------------------------------------------- parsing

# Fields that are not reflexes: numbering, meanings, references, comments, prose.
_NOT_REFLEX = re.compile(
    r"NUMBER|MEAN|REFER|^REF|COMMENT|NOTE|PAGE|EDITOR|TRUBACH|ORIGIN|GENERAL|MATERIAL|"
    r"GRAMMAR|DERIVAT|SEEALSO|LITERAT|SOURCE|AUTHOR|DATE",
    re.I,
)
_GLOSS = re.compile(r"[`'‘\"«“]([^'’\"»”`]{1,120})['’\"»”]")
_GRAMMAR = {"m", "f", "n", "nt", "adj", "adv", "v", "vb", "sg", "pl", "du", "pf", "ipf", "c"}


def segments(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[;\n]", text) if s.strip()]


def parse_segment(seg: str, names: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    """(language code from a leading abbreviation or None, form, gloss) of one segment."""
    m = _GLOSS.search(seg)
    gloss = m.group(1).strip() if m else None
    head = seg[: m.start()] if m else seg
    head = re.sub(r"\([^)]*\)", " ", head)
    code, form = None, None
    tokens = head.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i].strip(",:")
        two = f"{tok} {tokens[i + 1].strip(',:')}" if i + 1 < len(tokens) else ""
        if two in names and form is None:  # "Toch. B"
            code = names[two]
            i += 2
            continue
        if tok in names and form is None:
            code = names[tok]
            i += 1
            continue
        bare = tok.rstrip(".")
        if tok.endswith(".") and len(tok) <= 6 or bare in _GRAMMAR:
            i += 1  # a grammatical abbreviation: gen., adj., n.
            continue
        if any(ch.isalpha() for ch in tok) and not tok.isdigit():
            form = tok.strip(".,:")
            break
        i += 1
    if code == "*":
        code = None
    return code, form or None, gloss


def unknown_abbreviation(seg: str, names: dict[str, str]) -> str | None:
    first = seg.split()[0].strip(",:") if seg.split() else ""
    if first.endswith(".") and first[:1].isupper() and first not in names:
        return first
    return None


def link_target(field: str, links: dict[str, str], databases: Iterable[str]) -> str | None:
    """The database a number field such as GERMNUM or SLAVNUM points to."""
    stem = field.lower()
    stem = stem[:-3] if stem.endswith("num") else stem
    candidates = [stem, "proto"] if stem == "pr" else [stem]
    for c in candidates:
        if c in links:
            return links[c]
    for db in sorted(databases):
        if stem and db.startswith(stem):
            return db
    return None


def first_line(text: str) -> str:
    return re.split(r"[;,]\s", text, maxsplit=1)[0].strip(" ,;")


def strip_stress(form: str) -> str:
    return unicodedata.normalize(
        "NFC",
        "".join(c for c in unicodedata.normalize("NFD", form) if c not in ("́", "̀")),
    )


# ---------------------------------------------------------------- import

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


def import_starling(
    conn: psycopg.Connection,
    archives: list[Path],
    version: str,
    code_map: dict[str, str] | None = None,
    name_languages: dict[str, str] | None = None,
    unmapped_report: Path | None = None,
) -> dict:
    """code_map: Wiktionary code -> configured language id (others become wkt-<code>).
    name_languages: further field names -> language id (e.g. from Glottolog names)."""
    code_map = code_map or {}
    name_languages = name_languages or {}
    config = load_config()
    names = load_language_names()
    full_names = {}
    for key, code in names.items():
        if code != "*" and not key.endswith(".") and len(key) > 3:
            full_names.setdefault(code, key)
    misses: Counter = Counter()
    unmapped: Counter = Counter()
    stats: Counter = Counter()
    dbs = open_archives(archives)
    languages: dict[str, tuple[str, bool]] = {}  # language id -> (name, is_proto)

    def language_of(code: str, name: str | None = None, proto: bool = False) -> str:
        lang = code_map.get(code) or f"wkt-{code.lower()}"
        languages.setdefault(lang, (name or full_names.get(code) or code, proto))
        return lang

    lexemes: dict[str, tuple] = {}
    rels: dict[str, tuple] = {}
    evidence: list[tuple] = []

    def add_lexeme(key, lang, form, gloss, status, source, citation, native=None) -> str:
        lid = lexeme_id(DATASET, key)
        if key not in lexemes:
            lexemes[key] = (
                lid,
                lang,
                form,
                normalize_form(form),
                lexeme_search_key(form, lang),
                native or form,
                "source",
                gloss,
                form_kind(form, False).value,
                status.value,
                DATASET,
                source,
                key,
                citation,
            )
        return lid

    def add_link(child, parent, label, source, record, citation, locator, note=None) -> None:
        if child == parent:
            return
        rid = relationship_id(DATASET, "etymon", child, parent)
        if rid in rels:
            return
        rels[rid] = (
            rid,
            child,
            parent,
            "etymon",
            "directed",
            "documented",
            source,
            record,
            label,
            None,
            note,
            DATASET,
        )
        evidence.append((rid, source, citation, locator, note))
        stats["links"] += 1

    def citation_of(cfg: DbConfig, number: str, extra: str = "") -> str:
        return f"StarLing, {cfg.title} ({cfg.compilers}), no. {number}" + (
            f", {extra}" if extra else ""
        )

    # Pokorny: page references only
    pokorny_pages: dict[str, str] = {}
    if "pokorny" in dbs:
        for r in dbs["pokorny"].records:
            pages = decode_starling(r.get("PAGES", b"") or b"", misses)
            if pages:
                pokorny_pages[r["NUMBER"]] = f"Pokorny IEW {pages}"

    # Vasmer: Russian headwords
    vasmer_ids: dict[str, str] = {}
    if "vasmer" in dbs and "vasmer" in config:
        cfg = config["vasmer"]
        lang = language_of(cfg.code)
        for r in dbs["vasmer"].records:
            stressed = decode_starling(r.get("WORD", b"") or b"", misses).strip(" ,")
            if not stressed or not any(c.isalpha() for c in stressed):
                continue
            form = strip_stress(stressed)
            general = decode_starling(r.get("GENERAL", b"") or b"", misses)
            m = _GLOSS.search(general)
            gloss = f"{m.group(1).strip()} (in Russian)" if m and m.start() < 40 else None
            pages = decode_starling(r.get("PAGES", b"") or b"", misses)
            vasmer_ids[r["NUMBER"]] = add_lexeme(
                f"ru:{normalize_form(form)}",
                lang,
                form,
                gloss,
                ReconstructionStatus.attested,
                "starling-vasmer",
                f"Vasmer, {pages}" if pages else citation_of(cfg, r["NUMBER"]),
                native=stressed,
            )
            stats["vasmer_words"] += 1

    # Etymology and dictionary databases
    proto_ids: dict[tuple[str, str], str] = {}
    missing: list[str] = []  # configured databases not in the archives given
    pending_links: list[tuple[str, dict, DbConfig, str]] = []
    for name, cfg in config.items():
        if cfg.kind not in ("etymology", "dictionary") or name not in dbs:
            if cfg.kind not in ("skip", "vasmer", "pokorny"):
                missing.append(name)
            continue
        db = dbs[name]
        text_fields = [f.name for f in db.fields if f.kind == "C" and f.length == 6]
        main = "PROTO" if "PROTO" in text_fields else ("WORD" if "WORD" in text_fields else None)
        main = main or next((f for f in text_fields if not _NOT_REFLEX.search(f)), None)
        if main is None:
            stats[f"no_form_field:{name}"] += 1
            continue
        alias_main = db.aliases.get(main, "")
        proto = cfg.kind == "etymology"
        if cfg.code:
            lang = language_of(cfg.code, alias_main if proto else None, proto)
        else:
            lang = f"starling-{name}"
            languages.setdefault(
                lang,
                (alias_main if alias_main.startswith("Proto") else f"Proto ({cfg.title})", proto),
            )
        source = f"starling-{name}"
        meaning_fields = [f for f in text_fields if "MEAN" in f]
        english = [f for f in meaning_fields if f in ("MEANING", "ENGMEAN", "EMEAN")]
        reflex_fields = [f for f in text_fields if f != main and not _NOT_REFLEX.search(f)]
        for r in db.records:
            number = r.get("NUMBER", "")
            form = first_line(decode_starling(r.get(main, b"") or b"", misses))
            if not form or not any(c.isalpha() for c in form):
                continue
            gloss = None
            for f in english + [f for f in meaning_fields if f not in english]:
                g = decode_starling(r.get(f, b"") or b"", misses)
                if g:
                    gloss = g if f in english else f"{g} (in Russian)"
                    break
            refer = decode_starling(r.get("REFER", b"") or b"", misses)
            status = (
                ReconstructionStatus.reconstructed
                if proto or form.startswith("*")
                else ReconstructionStatus.attested
            )
            if proto and not form.startswith("*"):
                form = "*" + form
            pid = add_lexeme(
                f"{name}:{number}",
                lang,
                form,
                gloss[:300] if gloss else None,
                status,
                source,
                citation_of(cfg, number),
            )
            proto_ids[(name, number)] = pid
            stats[f"records:{name}"] += 1
            locator = (
                "; ".join(x for x in (refer, pokorny_pages.get(r.get("REFERNUM", ""), "")) if x)
                or None
            )
            for field in reflex_fields:
                text = decode_starling(r.get(field, b"") or b"", misses)
                if not text:
                    continue
                alias = db.aliases.get(field, field)
                field_code = names.get(alias) or names.get(field.title())
                field_lang = name_languages.get(alias.lower()) if not field_code else None
                if not field_code and not field_lang:
                    unmapped[f"field {name}.{field} ({alias})"] += 1
                    continue
                for seg in segments(text):
                    code, rform, rgloss = parse_segment(seg, names)
                    if code is None and field_code == "*":
                        if abbr := unknown_abbreviation(seg, names):
                            unmapped[f"abbreviation {abbr} (in {name}.{field})"] += 1
                        stats["segments_without_language"] += 1
                        continue
                    if not rform:
                        continue
                    if code:
                        rlang = language_of(code)
                    elif field_lang:
                        rlang = field_lang
                    else:
                        rlang = language_of(field_code)
                    rcode = code or field_code or ""
                    rstatus = (
                        ReconstructionStatus.reconstructed
                        if rform.startswith("*") or rcode.endswith("-pro")
                        else ReconstructionStatus.attested
                    )
                    rid = add_lexeme(
                        f"{rlang}:{normalize_form(rform)}",
                        rlang,
                        rform,
                        rgloss,
                        rstatus,
                        source,
                        citation_of(cfg, number, alias),
                    )
                    add_link(
                        rid,
                        pid,
                        f"reflex ({alias})",
                        source,
                        f"{name}:{number}#{field}",
                        citation_of(cfg, number, f"{form}, {alias}"),
                        locator,
                    )
                    stats["reflexes"] += 1
            for f in db.fields:
                if f.kind == "N" and f.name != "NUMBER" and r.get(f.name, "") not in ("", "0"):
                    pending_links.append((name, r, cfg, f.name))

    # Links between databases
    for name, r, cfg, field in pending_links:
        target = link_target(field, dbs[name].links, set(config))
        tcfg = config.get(target or "")
        number, other = r.get("NUMBER", ""), r[field]
        this = proto_ids.get((name, number))
        if not tcfg or not this:
            stats[f"link_unresolved:{name}.{field}"] += 1
            continue
        contested = cfg.contested or tcfg.contested
        note = CONTESTED_NOTE if contested else None
        cite = citation_of(cfg, number, f"link {field} to {tcfg.title} no. {other}")
        locator = pokorny_pages.get(r.get("REFERNUM", ""))
        if tcfg.kind == "pokorny":
            continue  # used for page references
        if tcfg.kind == "vasmer":
            if other in vasmer_ids:
                add_link(
                    vasmer_ids[other],
                    this,
                    f"{field} (Vasmer)",
                    f"starling-{name}",
                    f"{name}:{number}#{field}",
                    cite,
                    locator,
                )
            continue
        that = proto_ids.get((target, other))
        if not that:
            stats[f"link_target_missing:{name}.{field}"] += 1
            continue
        if tcfg.parent == name:  # the target is a subordinate etymology of this record
            child, parent = that, this
        elif cfg.parent == target:
            child, parent = this, that
        else:
            stats[f"link_not_parent_child:{name}.{field}"] += 1
            continue
        add_link(
            child,
            parent,
            f"{field} link",
            f"starling-{name}",
            f"{name}:{number}#{field}",
            cite,
            locator,
            note,
        )

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
            " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
            (
                DATASET,
                version,
                psycopg.types.json.Jsonb({p.name: sha256_file(p) for p in archives}),
                psycopg.types.json.Jsonb(
                    [
                        "StarLing DBF/VAR databases decoded from the StarLing character set",
                        "Etymology records -> reconstructed proto-forms",
                        "Reflex fields -> words linked to the proto-form (etymon)",
                        "Number fields -> links from subordinate to main etymologies",
                        "Vasmer -> Russian headwords; Pokorny -> page references only",
                        "No dictionary prose stored",
                    ]
                ),
            ),
        )
        batch = cur.fetchone()[0]
        cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
        cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))
        cur.execute(
            "INSERT INTO source (id, title, url, reuse_status, attribution_text, dataset_id)"
            " VALUES ('starling', 'StarLing: The Tower of Babel', 'https://starlingdb.org/',"
            " 'permission_required', %s, %s) ON CONFLICT (id) DO NOTHING",
            (
                "Starostin, S. A., G. S. Starostin et al. The Tower of Babel: An Etymological "
                "Database Project. https://starlingdb.org/",
                DATASET,
            ),
        )
        for name, cfg in config.items():
            cur.execute(
                "INSERT INTO source (id, title, author_or_editor, url, reuse_status,"
                " attribution_text, parent_source_id, dataset_id) VALUES (%s, %s, %s,"
                " 'https://starlingdb.org/', 'permission_required', %s, 'starling', %s)"
                " ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title,"
                " author_or_editor = EXCLUDED.author_or_editor,"
                " attribution_text = EXCLUDED.attribution_text",
                (
                    f"starling-{name}",
                    f"StarLing: {cfg.title}",
                    cfg.compilers,
                    f"{cfg.compilers}. {cfg.title}. In: The Tower of Babel (StarLing), "
                    "https://starlingdb.org/",
                    DATASET,
                ),
            )
        for lang, (lname, is_proto) in sorted(languages.items()):
            cur.execute(
                "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
                " VALUES (%s, %s, 'other', %s, false, %s) ON CONFLICT (id) DO NOTHING",
                (lang, lname, is_proto, psycopg.types.json.Jsonb({"starling": True})),
            )
        copy_rows(cur, "lexeme", LEXEME_COLS, (row + (batch,) for row in lexemes.values()))
        copy_rows(cur, "relationship", REL_COLS, (row + (batch,) for row in rels.values()))
        copy_rows(cur, "evidence", EVIDENCE_COLS, evidence)
        stats.update(lexemes=len(lexemes), relationships=len(rels))
        stats["encoding_misses"] = sum(misses.values())
        stats["unmapped"] = sum(unmapped.values())
        cur.execute(
            "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
            (psycopg.types.json.Jsonb(dict(stats)), batch),
        )
    if unmapped_report is not None:
        unmapped_report.parent.mkdir(parents=True, exist_ok=True)
        with unmapped_report.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["what", "occurrences"])
            w.writerows(unmapped.most_common())
            w.writerows((f"encoding {k}", v) for k, v in misses.most_common())
    return {
        "batch_id": batch,
        **dict(stats),
        "top_unmapped": dict(unmapped.most_common(15)),
        "databases_found": sorted(dbs),
        "databases_missing": missing,
    }


def name_languages_from_glottolog(conn: psycopg.Connection, glottolog) -> dict[str, str]:
    """Lower-case Glottolog language name -> language id, for field names the CSV lacks."""
    from app.pipeline.languages import canonical_targets

    targets = canonical_targets(conn)
    out = defaultdict(set)
    for gc, row in glottolog.languoids.items():
        if row.get("Level") == "language" and gc in targets:
            out[row["Name"].lower()].add(targets[gc])
    return {k: next(iter(v)) for k, v in out.items() if len(v) == 1}
