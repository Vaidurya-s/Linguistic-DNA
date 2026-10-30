"""Import a Jambu (moli-mandala/data) CLDF snapshot.

Scope: every form in a configured target language, plus every form reachable from those by
following ``edges.csv`` towards parents (etyma, proto-forms, donors, components). Edges and
comparisons are kept when both ends are in scope.

Never imported: the ``Etymology`` column of ``forms.csv`` and ``entry-texts.csv`` (verbatim
dictionary text), and the free-text ``Evidence`` column of ``comparisons.csv``.
See docs/DATASET_AUDIT.md.
"""

import html
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from app.config import REPO_ROOT
from app.importers.common import Citation, copy_rows, parse_citations, read_csv, sha256_file
from app.importers.concepticon import concept_id
from app.models.enums import (
    Direction,
    NativeFormOrigin,
    ReconstructionStatus,
    RelationshipStatus,
    ReuseStatus,
    SourceConfidence,
)
from app.services.ids import lexeme_id, relationship_id
from app.services.normalize import form_kind, lexeme_search_key, normalize_form

DATASET = "jambu"
AGGREGATE_SOURCE = "jambu"
LANGUAGE_CONFIG = REPO_ROOT / "data" / "config" / "languages.csv"
SOURCE_MAP = REPO_ROOT / "data" / "manifests" / "jambu_source_map.csv"

FORM_COLUMNS = (
    "ID",
    "Language_ID",
    "Form",
    "Gloss",
    "Native",
    "Phonemic",
    "Tags",
    "Source",
    "Status",
)
EDGE_COLUMNS = ("Child_ID", "Parent_ID", "Kind", "Rank", "Source", "Note")
COMPARISON_COLUMNS = (
    "Entry_ID",
    "Compared_Entry_ID",
    "Relation",
    "Direction",
    "Confidence",
    "Source",
)
LANGUAGE_COLUMNS = ("ID", "Name", "Glottocode", "Clade")

EDGE_TYPES = {
    "reflex": "inherited_form",
    "derived": "derived_form",
    "borrowed": "borrowed_from",
    "variant": "variant_of",
    "component": "has_component",
}
COMPARISON_TYPES = {
    "related": "related_form",
    "loan": "borrowed_from",
    "influence": "contact_influence",
}

TRANSFORMATIONS = [
    "Scope: target-language forms plus their ancestors/donors/components via edges.csv",
    "normalized_form = NFC, control characters removed, whitespace collapsed; raw form kept",
    "reconstruction_status: '*' prefix or Proto- language -> reconstructed; '√' roots and "
    "affixes -> uncertain; other forms of configured languages -> attested; else unknown",
    "Form in a native script (Indic, Arabic, Tibetan, ...) with empty Native -> native_form",
    "Gloss: inline HTML markup stripped and entities unescaped",
    "edges.csv Child->Parent mapped to relationship source->target; kinds mapped to the "
    "controlled vocabulary, original kind kept in original_label",
    "Edges without their own Source inherit the child form's citations, preferring those of "
    "the parent's source (noted in evidence)",
    "Excluded: forms.Etymology, entry-texts.csv, comparisons.Evidence (verbatim text)",
]


@dataclass
class TargetLanguage:
    id: str
    jambu_id: str
    name: str
    role: str
    group: str
    primary_script: str
    glottocode: str
    extra_glottocodes: str = ""  # ';'-separated codes other datasets use for the language
    wikidata_qid: str = ""
    wikidata_lemma: str = ""  # lemma spelling code to prefer, e.g. 'hi'
    wiktionary_codes: str = ""  # ';'-separated Wiktionary language codes, e.g. 'hi'

    @property
    def glottocodes(self) -> list[str]:
        return [c for c in [self.glottocode, *self.extra_glottocodes.split(";")] if c]


@dataclass
class ImportStats:
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] += n


def load_languages(path: Path = LANGUAGE_CONFIG) -> list[TargetLanguage]:
    """All configured target languages (data/config/languages.csv)."""
    rows = read_csv(
        path, ("id", "jambu_id", "name", "role", "group", "primary_script", "glottocode")
    )
    return [TargetLanguage(**r) for r in rows]


def load_language_config(path: Path = LANGUAGE_CONFIG) -> dict[str, TargetLanguage]:
    """Configured languages that Jambu has, keyed by Jambu language ID."""
    return {t.jambu_id: t for t in load_languages(path) if t.jambu_id}


def load_source_map(path: Path = SOURCE_MAP) -> dict[str, str]:
    return {r["jambu_key"]: r["source_id"] for r in read_csv(path, ("jambu_key", "source_id"))}


# Blocks of the native scripts found in Jambu (Arabic through Sinhala, Tibetan, Myanmar,
# Ol Chiki, Kharoshthi and Brahmi). Latin, IPA, Greek and modifier letters are not native.
_NATIVE_BLOCKS = (
    (0x0590, 0x0DFF),
    (0x0F00, 0x109F),
    (0x1C50, 0x1C7F),
    (0x10A00, 0x10A5F),
    (0x11000, 0x1107F),
)


def has_native_script(text: str) -> bool:
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in _NATIVE_BLOCKS)


_TAG = re.compile(r"<[^>]+>")


def plain_gloss(gloss: str) -> str | None:
    """Jambu glosses carry inline <i>/<b> markup; keep the text, drop the tags."""
    text = html.unescape(_TAG.sub("", gloss)).strip()
    return text or None


def reconstruction_status(form: str, is_proto: bool, configured: bool) -> ReconstructionStatus:
    if form.startswith("*") or is_proto:
        return ReconstructionStatus.reconstructed
    if form.startswith(("√", "-")):  # roots and affixes are analytical units, not words
        return ReconstructionStatus.uncertain
    return ReconstructionStatus.attested if configured else ReconstructionStatus.unknown


def inherited_citations(child_source: str, parent_source: str) -> list[Citation]:
    """Citations for an edge that has none: prefer the child's citations of the work the
    parent comes from (e.g. the CDIAL entry), else all of the child's citations."""
    child = parse_citations(child_source)
    parent_keys = {c.key for c in parse_citations(parent_source)}
    shared = [c for c in child if c.key in parent_keys]
    return shared or child


_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_URL = re.compile(r"https?://[^\s)\]]+")


def clean_reference(text: str) -> tuple[str, str | None]:
    """Jambu bibliography entries are Markdown; return (plain title, first URL)."""
    url_match = _URL.search(text)
    plain = _MD_LINK.sub(r"\1", text)
    plain = re.sub(r"\s*URL:\s*\S+", "", plain).replace("*", "")
    return re.sub(r"\s+", " ", plain).strip(" ."), url_match.group(0) if url_match else None


_SLUG = re.compile(r"[^a-z0-9]+")


def auto_language_id(jambu_id: str) -> str:
    return "jb-" + (_SLUG.sub("-", jambu_id.lower()).strip("-") or "x")


class JambuImporter:
    def __init__(
        self,
        conn: psycopg.Connection,
        cldf_dir: Path,
        forms_path: Path | None = None,
        version: str = "unknown",
        languages: dict[str, TargetLanguage] | None = None,
        all_languages: bool = False,
    ):
        self.conn = conn
        # False: only the configured languages and their ancestors. True: every Jambu form,
        # so that chains through unconfigured languages stay whole; those languages are
        # created disabled (role "other") and are enabled later by adding them to the config.
        self.all_languages = all_languages
        self.cldf = cldf_dir
        self.forms_path = forms_path or cldf_dir / "forms.csv"
        self.version = version
        self.targets = languages or load_language_config()
        self.source_map = load_source_map()
        self.stats = ImportStats()
        self.references: dict[str, str] = {}
        self.sources_used: set[str] = set()

    # -- helpers -----------------------------------------------------------------------
    def source_for(self, key: str) -> str:
        sid = self.source_map.get(key) or f"jambu-ref:{key}"
        self.sources_used.add(key)
        return sid

    # -- pipeline ----------------------------------------------------------------------
    def run(self) -> dict:
        paths = {
            "forms.csv": self.forms_path,
            "edges.csv": self.cldf / "edges.csv",
            "comparisons.csv": self.cldf / "comparisons.csv",
            "languages.csv": self.cldf / "languages.csv",
            "references.csv": self.cldf / "references.csv",
            "concepts.csv": self.cldf / "concepts.csv",
            "form_concepts.csv": self.cldf / "form_concepts.csv",
        }
        checksums = {name: sha256_file(p) for name, p in paths.items() if p.exists()}
        jambu_languages = {r["ID"]: r for r in read_csv(paths["languages.csv"], LANGUAGE_COLUMNS)}
        if paths["references.csv"].exists():
            self.references = {
                r["ID"]: r["Source"].replace("\\", "")
                for r in read_csv(paths["references.csv"], ("ID", "Source"))
            }

        keep = self._scope(paths["forms.csv"], paths["edges.csv"])
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO import_batch (dataset, version, input_checksums, transformations,"
                " stats) VALUES (%s, %s, %s, %s, '{}') RETURNING id",
                (
                    DATASET,
                    self.version,
                    psycopg.types.json.Jsonb(checksums),
                    psycopg.types.json.Jsonb(TRANSFORMATIONS),
                ),
            )
            batch_id = cur.fetchone()[0]
            cur.execute("DELETE FROM relationship WHERE dataset = %s", (DATASET,))
            cur.execute("DELETE FROM lexeme WHERE dataset = %s", (DATASET,))
            # Concepts used to be keyed "jambu:<id>"; they are Concepticon IDs now.
            cur.execute("DELETE FROM concept WHERE id LIKE 'jambu:%%'")

            forms = self._read_forms(paths["forms.csv"], keep)
            self._upsert_languages(cur, jambu_languages, {f["Language_ID"] for f in forms.values()})
            lexemes = self._lexeme_rows(forms, jambu_languages, batch_id)
            rels, evidence = self._edge_rows(paths["edges.csv"], forms, batch_id)
            c_rels, c_evidence = self._comparison_rows(paths["comparisons.csv"], forms, batch_id)
            rels.update(c_rels)
            evidence.extend(c_evidence)
            self._upsert_sources(cur)

            copy_rows(cur, "lexeme", LEXEME_COLS, lexemes)
            copy_rows(cur, "relationship", REL_COLS, rels.values())
            copy_rows(cur, "evidence", EVIDENCE_COLS, evidence)
            self._import_concepts(cur, paths["concepts.csv"], paths["form_concepts.csv"], forms)

            self.stats.add("lexemes", len(lexemes))
            self.stats.add("relationships", len(rels))
            self.stats.add("evidence", len(evidence))
            cur.execute(
                "UPDATE import_batch SET stats = %s, finished_at = now() WHERE id = %s",
                (psycopg.types.json.Jsonb(dict(self.stats.counts)), batch_id),
            )
        return {"batch_id": batch_id, **self.stats.counts}

    def _scope(self, forms_path: Path, edges_path: Path) -> set[str]:
        keep = {
            r["ID"]
            for r in read_csv(forms_path, FORM_COLUMNS)
            if self.all_languages or r["Language_ID"] in self.targets
        }
        parents: dict[str, list[str]] = defaultdict(list)
        self.compounds: set[str] = set()
        for e in read_csv(edges_path, EDGE_COLUMNS):
            parents[e["Child_ID"]].append(e["Parent_ID"])
            if e["Kind"] == "component":
                self.compounds.add(e["Child_ID"])
        frontier = list(keep)
        while frontier:
            nxt = []
            for child in frontier:
                for p in parents.get(child, ()):
                    if p not in keep:
                        keep.add(p)
                        nxt.append(p)
            frontier = nxt
        return keep

    def _read_forms(self, path: Path, keep: set[str]) -> dict[str, dict[str, str]]:
        forms = {}
        for r in read_csv(path, FORM_COLUMNS):
            if r["ID"] in keep:
                r.pop("Etymology", None)  # verbatim entry text: never retained
                r.pop("Description", None)
                forms[r["ID"]] = r
        return forms

    def _upsert_languages(self, cur, jambu_languages: dict[str, dict], used: set[str]) -> None:
        self.language_ids: dict[str, str] = {}
        self.proto: set[str] = set()
        for jid in sorted(used):
            meta = jambu_languages.get(jid, {"Name": jid, "Glottocode": "", "Clade": ""})
            target = self.targets.get(jid)
            is_proto = meta["Name"].startswith("Proto-")
            if is_proto:
                self.proto.add(jid)
            lid = target.id if target else auto_language_id(jid)
            self.language_ids[jid] = lid
            role = target.role if target else ("reference" if is_proto else "other")
            cur.execute(
                """
                INSERT INTO language (id, name, glottocode, role, is_proto, is_enabled,
                    metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name,
                    glottocode = EXCLUDED.glottocode, role = EXCLUDED.role,
                    is_proto = EXCLUDED.is_proto, is_enabled = EXCLUDED.is_enabled,
                    metadata_json = language.metadata_json || EXCLUDED.metadata_json
                """,
                (
                    lid,
                    target.name if target else meta["Name"],
                    (target.glottocode if target else meta["Glottocode"]) or None,
                    role,
                    is_proto,
                    bool(target),
                    psycopg.types.json.Jsonb(
                        {"jambu_clade": meta["Clade"], "group": target.group if target else None}
                    ),
                ),
            )
            cur.execute(
                "INSERT INTO language_alias (language_id, scheme, value) VALUES (%s, 'jambu', %s)"
                " ON CONFLICT DO NOTHING",
                (lid, jid),
            )
            if target:
                cur.execute(
                    "INSERT INTO language_script (language_id, script_id, is_primary)"
                    " VALUES (%s, %s, true) ON CONFLICT DO NOTHING",
                    (lid, target.primary_script),
                )

    def _lexeme_rows(self, forms, jambu_languages, batch_id) -> list[tuple]:
        rows = []
        for fid, r in forms.items():
            jid = r["Language_ID"]
            form = r["Form"]
            native = r["Native"] or None
            origin = NativeFormOrigin.source.value if native else None
            translit = form
            if not native and has_native_script(form):
                native, origin, translit = form, NativeFormOrigin.source.value, None
            cites = parse_citations(r["Source"])
            primary = self.source_for(cites[0].key) if cites else AGGREGATE_SOURCE
            status = reconstruction_status(form, jid in self.proto, jid in self.targets)
            if status is ReconstructionStatus.reconstructed:
                self.stats.add("reconstructed")
            if r.get("Redirect"):
                self.stats.add("redirect_rows")
            rows.append(
                (
                    lexeme_id(DATASET, fid),
                    self.language_ids[jid],
                    form,
                    normalize_form(form),
                    lexeme_search_key(form, self.language_ids[jid]),
                    native,
                    origin,
                    translit,
                    r["Phonemic"] or None,
                    plain_gloss(r["Gloss"]),
                    form_kind(form, fid in self.compounds).value,
                    status.value,
                    r["Status"] or None,
                    r["Tags"].split() or None,
                    DATASET,
                    primary,
                    fid,
                    r["Source"] or None,
                    batch_id,
                )
            )
        return rows

    def _edge_rows(self, path: Path, forms, batch_id):
        rels: dict[str, tuple] = {}
        evidence: list[tuple] = []
        for e in read_csv(path, EDGE_COLUMNS):
            child, parent = e["Child_ID"], e["Parent_ID"]
            if child not in forms or parent not in forms:
                self.stats.add("edges_out_of_scope")
                continue
            if child == parent:
                self.stats.add("edges_self_loop_skipped")
                continue
            type_id = EDGE_TYPES.get(e["Kind"])
            if not type_id:
                self.stats.add(f"edges_unknown_kind:{e['Kind']}")
                continue
            rid = relationship_id(DATASET, "edge", child, parent, e["Kind"])
            if rid in rels:
                self.stats.add("edges_duplicate")
                continue
            cites = parse_citations(e["Source"])
            note = None
            if not cites:
                cites = inherited_citations(forms[child]["Source"], forms[parent]["Source"])
                note = "Citation taken from the child form's record; the edge has no own source."
            if not cites:
                cites = [Citation(AGGREGATE_SOURCE, None)]
                note = "No citation in Jambu for this edge or its child form."
            source_ids = [self._cite_source(c) for c in cites]
            rels[rid] = (
                rid,
                lexeme_id(DATASET, child),
                lexeme_id(DATASET, parent),
                type_id,
                Direction.directed.value,
                RelationshipStatus.documented.value,
                source_ids[0],
                f"edge:{child}->{parent}",
                e["Kind"],
                None,
                e["Rank"] or None,
                e["Note"] or None,
                DATASET,
                batch_id,
            )
            for c, sid in zip(cites, source_ids, strict=True):
                evidence.append((rid, sid, c.key, c.locator or f"Jambu form {parent}", note))
            self.stats.add(f"edges:{type_id}")
        return rels, evidence

    def _comparison_rows(self, path: Path, forms, batch_id):
        rels: dict[str, tuple] = {}
        evidence: list[tuple] = []
        if not path.exists():
            return rels, evidence
        for c in read_csv(path, COMPARISON_COLUMNS):
            a, b = c["Entry_ID"], c["Compared_Entry_ID"]
            if a not in forms or b not in forms or a == b:
                self.stats.add("comparisons_out_of_scope")
                continue
            type_id = COMPARISON_TYPES.get(c["Relation"])
            if not type_id:
                self.stats.add(f"comparisons_unknown_relation:{c['Relation']}")
                continue
            direction = Direction.directed
            if c["Direction"] == "compared-from-entry":
                a, b = b, a
            elif c["Direction"] != "entry-from-compared":
                direction = Direction.unknown
            rid = relationship_id(DATASET, "comparison", c.get("ID", ""), a, b, c["Relation"])
            if rid in rels:
                continue
            cites = parse_citations(c["Source"]) or [Citation(AGGREGATE_SOURCE, None)]
            source_ids = [self._cite_source(x) for x in cites]
            confidence = (
                c["Confidence"] if c["Confidence"] in SourceConfidence.__members__ else None
            )
            rels[rid] = (
                rid,
                lexeme_id(DATASET, a),
                lexeme_id(DATASET, b),
                type_id,
                direction.value,
                RelationshipStatus.documented.value,
                source_ids[0],
                f"comparison:{c.get('ID', '')}",
                c["Relation"],
                confidence,
                None,
                None,
                DATASET,
                batch_id,
            )
            for x, sid in zip(cites, source_ids, strict=True):
                evidence.append((rid, sid, x.key, x.locator, None))
            self.stats.add(f"comparisons:{type_id}")
        return rels, evidence

    def _cite_source(self, c: Citation) -> str:
        return AGGREGATE_SOURCE if c.key == AGGREGATE_SOURCE else self.source_for(c.key)

    def _upsert_sources(self, cur) -> None:
        cur.execute("SELECT id FROM source")
        existing = {r[0] for r in cur.fetchall()}
        created = 0
        if AGGREGATE_SOURCE not in existing:
            cur.execute(
                "INSERT INTO source (id, title, reuse_status, dataset_id) VALUES (%s, %s, %s, %s)",
                (AGGREGATE_SOURCE, "Jambu CLDF database", ReuseStatus.unknown.value, DATASET),
            )
        for key in sorted(self.sources_used):
            sid = self.source_map.get(key) or f"jambu-ref:{key}"
            if sid in existing and not sid.startswith("jambu-ref:"):
                continue  # manifest sources are curated by hand; never overwrite them
            created += sid not in existing
            existing.add(sid)
            title, url = clean_reference(self.references.get(key) or key)
            cur.execute(
                "INSERT INTO source (id, title, url, reuse_status, parent_source_id, notes,"
                " dataset_id) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, url = EXCLUDED.url,"
                " dataset_id = EXCLUDED.dataset_id",
                (
                    sid,
                    title or key,
                    url,
                    ReuseStatus.unknown.value,
                    AGGREGATE_SOURCE,
                    f"Jambu reference key '{key}'; not yet licence-reviewed",
                    DATASET,
                ),
            )
        self.stats.add("sources_auto_created", created)

    def _import_concepts(self, cur, concepts_path: Path, links_path: Path, forms) -> None:
        if not links_path.exists():
            return
        links = [
            (lexeme_id(DATASET, r["Form_ID"]), r["Concept_ID"])
            for r in read_csv(links_path, ("Form_ID", "Concept_ID"))
            if r["Form_ID"] in forms
        ]
        used = {cid for _, cid in links}
        rows = [
            # Jambu concept IDs are Concepticon IDs (verified: all 3,321 match ID and gloss).
            (concept_id(r["ID"]), r["Name"], "concepticon")
            for r in read_csv(concepts_path, ("ID", "Name"))
            if r["ID"] in used
        ]
        cur.executemany(
            "INSERT INTO concept (id, label, source_id) VALUES (%s, %s, %s)"
            " ON CONFLICT (id) DO NOTHING",
            rows,
        )
        known = {r[0] for r in rows}
        copy_rows(
            cur,
            "lexeme_concept",
            ("lexeme_id", "concept_id", "source_id"),
            sorted(
                {(lx, concept_id(c), AGGREGATE_SOURCE) for lx, c in links if concept_id(c) in known}
            ),
        )
        self.stats.add("lexeme_concepts", len(links))


LEXEME_COLS = (
    "id",
    "language_id",
    "form",
    "normalized_form",
    "search_key",
    "native_form",
    "native_form_origin",
    "transliteration",
    "phonemic",
    "gloss",
    "form_kind",
    "reconstruction_status",
    "source_status",
    "tags",
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
    "source_confidence",
    "rank",
    "notes",
    "dataset",
    "import_batch_id",
)
EVIDENCE_COLS = ("relationship_id", "source_id", "citation", "locator", "evidence_note")
