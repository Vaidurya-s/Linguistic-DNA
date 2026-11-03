"""Import the Kurdish Lexicographical Resources (Ahmadi et al.; CC BY-NC-SA 4.0, research use).

Four Ontolex-Lemon Turtle files: Sorani, Kurmanji, Hawrami (the KurdishLex project) and
Southern Kurdish. Each Kurdish ``:lex_<code>_<id>`` entry becomes a word of its language; its
short gloss is the label of the translation entry (English if there is one) that its sense is
linked to. The dictionaries state no word-to-word relationships, so none are created.

The files use a regular subset of Turtle, read here directly: blank-line-separated statements,
``rdfs:label "..."@tag`` and ``vartrans:source`` / ``vartrans:target`` pairs. Southern Kurdish
entries carry both Arabic- and Latin-script labels; the Arabic-script one is the word, the Latin
one is kept as a tag.
"""

import re
from pathlib import Path

import psycopg

from app.importers.common import sha256_file
from app.importers.headwords import Headword, language_by_iso, write_headwords

DATASET = "kurdish-lexicography"
FILES = {
    "ckb": "Sorani.ttl",
    "kmr": "Kurmanji.ttl",
    "hac": "Hawrami.ttl",
    "sdh": "Southern_Kurdish.ttl",
}
NAMES = {"ckb": "Sorani", "kmr": "Kurmanji", "hac": "Hawrami", "sdh": "Southern Kurdish"}
_BLOCK = re.compile(r"\n\s*\n")
_SUBJECT = re.compile(r"^\s*:(\S+)\s+a\s+([^;.]+)")
_LABEL = re.compile(r'"((?:[^"\\]|\\.)*)"@([A-Za-z-]+)')
_SENSES = re.compile(r"ontolex:sense\s+([^.;]+)")
_SOURCE = re.compile(r"vartrans:source\s+:(\S+)")
_TARGET = re.compile(r"vartrans:target\s+:(\S+)")
_POS = re.compile(r"lexinfo:partOfSpeech\s+lexinfo:(\w+)")
_REP = re.compile(r'ontolex:writtenRep\s+"((?:[^"\\]|\\.)*)"@([A-Za-z-]+)')


def parse_ttl(path: Path, iso: str) -> list[dict]:
    """Headwords of one file: record id, label(s), part of speech and translation labels."""
    text = path.read_text(encoding="utf-8")
    heads: dict[str, dict] = {}  # entry id (e.g. ckb_1483878033) -> entry
    sense_owner: dict[str, str] = {}  # sense id -> entry id
    others: dict[str, tuple[str, str]] = {}  # translation-side sense id -> (label, lang tag)
    trans: list[tuple[str, str]] = []
    prefix = f"lex_{iso}_"
    for block in _BLOCK.split(text):
        m = _SUBJECT.match(block)
        if not m:
            continue
        subject, types = m.group(1), m.group(2)
        if "ontolex:LexicalEntry" in types:
            labels = (
                _LABEL.findall(block.split("rdfs:label", 1)[1]) if "rdfs:label" in block else []
            )
            if subject.startswith(prefix):
                entry = subject[len("lex_") :]
                e = heads.setdefault(entry, {"id": entry, "labels": [], "pos": None})
                e["labels"] += labels
                for part in _SENSES.findall(block):
                    for sense in part.split(","):
                        sense_owner[sense.strip().lstrip(":")] = entry
            elif labels:  # an entry of another language: its sense carries the label
                for part in _SENSES.findall(block):
                    for sense in part.split(","):
                        others[sense.strip().lstrip(":")] = labels[0]
        elif "ontolex:Form" in types and subject.startswith(f"form_{iso}_"):
            entry = subject[len("form_") :]
            e = heads.setdefault(entry, {"id": entry, "labels": [], "pos": None})
            if pos := _POS.search(block):
                e["pos"] = pos.group(1)
            for rep in _REP.findall(block):
                e["labels"].append(rep)
            for part in _SENSES.findall(block):
                for sense in part.split(","):
                    sense_owner[sense.strip().lstrip(":")] = entry
        elif "vartrans:Translation" in types:
            src, tgt = _SOURCE.search(block), _TARGET.search(block)
            if src and tgt:
                trans.append((src.group(1), tgt.group(1)))
    glosses: dict[str, list[tuple[str, str]]] = {}
    for src, tgt in trans:
        owner = sense_owner.get(src) or sense_owner.get(re.sub(r"_sense$", "", src))
        label = others.get(tgt)
        if owner and label:
            glosses.setdefault(owner, []).append(label)
    out = []
    for entry, e in heads.items():
        if not e["labels"]:
            continue
        e["glosses"] = glosses.get(entry, [])
        out.append(e)
    return out


def gloss_of(translations: list[tuple[str, str]]) -> str | None:
    """English translations if any, else the first translations with their language tag."""
    english = [t for t, lang in translations if lang.split("-")[0] == "en"]
    if english:
        return "; ".join(dict.fromkeys(english))
    other = [f"{lang.split('-')[0]}: {t}" for t, lang in translations[:2]]
    return "; ".join(dict.fromkeys(other)) or None


def headwords(path: Path, iso: str, language_id: str) -> list[Headword]:
    out = []
    for e in parse_ttl(path, iso):
        by_script = {tag.split("-", 1)[1] if "-" in tag else "": t for t, tag in e["labels"]}
        arabic = next((t for tag, t in by_script.items() if tag.startswith("arab")), None)
        latin = next((t for tag, t in by_script.items() if tag.startswith("latn")), None)
        form = arabic or latin or e["labels"][0][0]
        tags = [f"dialect:{NAMES[iso]}"]
        if e["pos"]:
            tags.append(f"pos:{e['pos']}")
        if arabic and latin:
            tags.append(f"latin:{latin}")
        out.append(
            Headword(
                record_id=e["id"],
                language_id=language_id,
                form=form,
                gloss=gloss_of(e["glosses"]),
                tags=tags,
                citation=f"Kurdish Lexicographical Resources, {NAMES[iso]} dictionary, "
                f"entry {e['id']}",
            )
        )
    return out


def import_kurdish(conn: psycopg.Connection, directory: Path, version: str) -> dict:
    entries: list[Headword] = []
    checksums = {}
    with conn.cursor() as cur:
        for iso, name in FILES.items():
            path = directory / name
            if not path.exists():
                continue
            checksums[name] = sha256_file(path)
            entries += headwords(path, iso, language_by_iso(cur, iso))
    return write_headwords(
        conn,
        dataset=DATASET,
        source_id=DATASET,
        version=version,
        checksums=checksums,
        transformations=[
            "Ontolex-Lemon Turtle: one word per Kurdish lexical entry, in its dialect's language",
            "Gloss: the label of the linked translation entry (English preferred)",
            "No relationships (the dictionaries state none)",
        ],
        entries=entries,
        default_citation="Kurdish Lexicographical Resources",
    )
