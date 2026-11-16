# Technical Architecture

How Linguistic DNA is built. For why the design is the way it is, see [`WRITEUP.md`](WRITEUP.md); for the data flow and commands, [`DATA_PIPELINE.md`](DATA_PIPELINE.md). This page describes the system as it stands, not the original proposal ([`PROJECT_SPECIFICATION.md`](PROJECT_SPECIFICATION.md) and [`DEVELOPMENT_ROADMAP.md`](DEVELOPMENT_ROADMAP.md) keep that).

## 1. Stack

| Layer | Choice | Role |
|---|---|---|
| Front end | React 19, TypeScript, Vite, Tailwind CSS | Search, graph interaction, evidence, methodology pages |
| Graph | Cytoscape.js | Drawing only; graph shaping is a separate, unit-tested module |
| API | Python 3.12+, FastAPI, Pydantic | Search, graph assembly, evidence, citations, language profiles |
| Database | PostgreSQL 16 with `pg_trgm` | Words, links, evidence, sources, the licence audit, indexed search |
| Schema | SQLAlchemy models and Alembic migrations (0001 to 0007) | Reproducible schema |
| Import and checks | Python importers and a CLI (`python -m app.cli`) | Reproducible ingestion from pinned inputs, validation, public seed |
| Tests | pytest against PostgreSQL (374), Vitest (42), a 22-case relationship benchmark | Correctness and regression |
| Deployment | Docker API image plus a static site; or everything on one Linux machine | See [`DEPLOYMENT.md`](DEPLOYMENT.md) |

No microservices and no graph database: every query pattern so far is served by indexed PostgreSQL tables.

## 2. Components

```mermaid
flowchart TD
    U[User] --> FE[React + TypeScript UI]
    FE -->|/api/v1| API[FastAPI]
    API --> RET[services/retrieval.py<br/>search, graph, evidence, citations]
    RET --> DB[(PostgreSQL 16 + pg_trgm)]
    RET --> TR[services/transliterate.py<br/>ISO 15919 romaniser]
    FETCH[scripts/fetch_data.py<br/>pinned downloads] --> RAW[(data/raw, git-ignored)]
    RAW --> IMP[importers/*<br/>typed links + evidence]
    AUD[dataset_audit.csv] -. gates .-> IMP
    IMP --> DB
    DB --> VAL[pipeline/validate.py<br/>33 checks]
    DB --> SEED[pipeline/public_seed.py<br/>approved rows only]
    DB --> LAY[layers/*<br/>inferred, candidate, keys, hub]
    LAY -. separate schema .-> DB
    RET --> LAY
```

## 3. Repository layout

```text
backend/app/
  main.py, config.py        FastAPI app and settings (DATABASE_URL, CORS_ORIGINS)
  api/                      routes.py (the endpoints below), health.py
  db/                       engine, session, dependencies
  models/                   SQLAlchemy models and the enums (relationship types, statuses)
  schemas/api.py            Pydantic response models
  schemas/layers.py         response models of the layered and technique routes
  services/                 retrieval.py (queries), transliterate.py, normalize.py (search keys and
                            the shared cleaning of stored text), ids.py
  importers/                one module per source; common.py (COPY helpers), manifest.py, audit.py,
                            headwords.py (shared writer for plain word lists)
  pipeline/                 validate.py, languages.py (refresh-languages), public_seed.py,
                            coverage.py, benchmark.py
  layers/                   the derived layers and their idempotent *.sql files (inferred, candidate,
                            keys, romanise, sound_key, hub, lineage, verify, verify_sources)
  cli.py                    every import and pipeline command
backend/migrations/         Alembic revisions 0001 to 0007
backend/tests/              pytest suites; synthetic fixtures under tests/fixtures/
frontend/src/
  app/                      App, Layout, hash router
  pages/                    HomePage, ExplorePage, MethodologyPage
  components/               GraphCanvas, GraphLegend, DetailsPanel, graphModel.ts (pure graph shaping),
                            edgeStyles.ts, graphExport.ts (JSON, SVG and PNG downloads),
                            sourceLabels.ts (plain-English source labels)
  api/client.ts, types/     typed API client
data/                       config, manifests (audit, sources, pinned downloads), public_seed, benchmark
scripts/                    fetch_data.py, fetch_valyrian.py, coverage_chart.py, build_fixture.py
```

## 4. Database model

All tables carry the dataset they came from, so the licence audit can be applied to any query.

| Table | Holds |
|---|---|
| `language` | One record per language: name, ISO 639-3, glottocode, family, `role`, `is_proto`, `is_enabled` (searchable) and `metadata_json`. `refresh-languages` makes one record per Glottolog language and merges the source-specific ones into it. |
| `language_family`, `language_alias`, `language_script`, `script`, `variety` | Classification (Glottolog), alternative names and codes, scripts, and dialect or doculect records |
| `language_stats` | Words and linked words per language, also counted for open datasets only; refreshed after imports so `/languages` needs no scan |
| `language_profile` | WALS features and PHOIBLE inventories, cited per value |
| `lexeme` | A word: `form`, `normalized_form`, `native_form`, `search_key`, `gloss`, `reconstruction_status` (`attested`, `reconstructed`, `uncertain`, `unknown`), `form_kind` (word, stem, affix, root, compound, phrase), `dataset`, `source_id`, `source_record_id`, `source_citation` |
| `concept`, `lexeme_concept` | Shared meanings (Concepticon, wordnet interlingual index) and the word-to-concept links; meaning is never drawn as a relationship |
| `relationship` | A directed or undirected link between two words: `type_id`, `direction`, `status` (documented, disputed, candidate, rejected), `original_label` (the source's own label), `dataset`, `source_record_id` |
| `evidence` | The citation, locator and note behind each documented relationship |
| `relationship_type` | The controlled vocabulary (below) |
| `source` | A cited work or dataset: licence, reuse status, attribution, `dataset_id`, and a parent source for works cited through a dataset |
| `dataset_audit` | The machine-readable licence audit loaded from `data/manifests/dataset_audit.csv` |
| `import_batch` | One row per import: dataset, version, input checksums, transformations and counts |
| `transliteration_alias` | Native and romanised spelling pairs (Dakshina, Aksharantar) for romanised search |
| `layers.*` (schema `layers`) | Computed tables, never mixed into the tables above: `inferred_pair`, `candidate_pair`, `candidate_calibration`, `gloss_token`, `word_key`, `sound_key`, `cognate_component`, `edge_hub_flag`, `source_lineage` and the build records. Created by migration 0007 or `init-layers`; filled by the layer builders (`docs/DATA_PIPELINE.md` § 6). |
| `translation_link` | Reserved for direct word-to-word translation pairs, kept apart from descent. Empty today: words meet through shared concepts instead |

Indexes: `pg_trgm` GIN indexes on the normalised form and the search key for fuzzy spelling retrieval, plus B-tree indexes on language, native form and the relationship endpoints. IDs are deterministic (`lx_`/`rel_` plus a hash of dataset and source record), so a re-import keeps them.

## 5. Relationship types

| Type | Namespace | Direction |
|---|---|---|
| `inherited_form`, `derived_form`, `borrowed_from`, `calque_or_loan_translation`, `etymon`, `has_component`, `variant_of`, `contact_influence`, `reconstructed_ancestor_of` | lexical | directed |
| `cognate` | lexical | undirected |
| `related_form` | lexical | directed (DPD) / unstated (Jambu) |
| `semantic_equivalent` | semantic | undirected |
| `orthographic_similarity_candidate`, `phonetic_similarity_candidate`, `semantic_relatedness_candidate` | similarity | undirected |
| `language_classification_parent` | classification | directed |

Six of the 16 types are reserved and unused: `language_classification_parent`, `orthographic_similarity_candidate`, `phonetic_similarity_candidate`, `semantic_relatedness_candidate`, `reconstructed_ancestor_of` and `semantic_equivalent`.

`etymon` is a link whose source does not say whether the word was inherited or borrowed. Candidate and classification types are never mixed into the word-relationship graph. Each source's own label is stored beside the normalised type. Where a source only groups words (Jambu's CDIAL reflexes under a PIE form) or Wiktionary gives an unmarked `{{desc}}` line, the link is `etymon` or yields to a better statement, never a guessed `inherited_form`.

## 6. API

Everything is under `/api/v1`; interactive docs are at `/docs`.

| Endpoint | Parameters | Returns |
|---|---|---|
| `GET /search` | `q` (1 to 64 characters), `language_id`, `limit` (1 to 50, default 10), `open_only` | Whole-word matches with how each was found, related forms (stems, affixes, roots, phrases), documented compounds, and spelling candidates, in separate fields |
| `GET /lexemes/{id}` | `open_only` | A word with its source, citation and status. With `open_only=true`, 404 for a word of a research-use or blocked dataset |
| `GET /lexemes/{id}/related` | `layers` (comma list of `documented`, `inferred`, `candidate`; default all three), `open_only`, `limit` (1 to 100, default 20), `candidate_gate` (`gloss` or `concept`) | The relatives of a word in three separate blocks. Each item states its evidence kind (below) |
| `GET /graph/{id}` | `depth` (1 or 2), `relationship_types`, `language_ids`, `limit_nodes` (up to 150, default 50), `open_only` | The neighbourhood of a word: nodes, typed edges, and whether it was truncated. `restricted` and `message` say when `open_only` emptied the graph because the root word is research-use |
| `GET /relationships/{id}` | `open_only` | A link with its direction, status, and every evidence row. With `open_only=true`, 404 for a link of a research-use or blocked dataset |
| `GET /search/fuzzy` | `q`, `language_id` (required), `threshold`, `limit`, `open_only` | Trigram-similar spellings inside one language |
| `GET /search/concept` | `q`, `concept_id` (repeatable) or `from_lexeme_id`, `language_ids`, `limit`, `open_only` | Words that share a concept with the query, ranked by spelling |
| `GET /search/keys` | `q`, `language_id` (required), `limit`, `open_only` | The same word in another script or spelling, found by rule through the word keys |
| `GET /search/sound` | `q`, `level` (`exact`, `cons`, `prefix`), `language_ids`, `exclude_language`, `limit`, `open_only` | Words in the same sound-class bucket, ranked by alignment |
| `GET /languages` | | Searchable languages with family, word and linked-word counts (open-only counts too) |
| `GET /languages/{id}/profile` | | WALS and PHOIBLE values for a language |
| `GET /citations` | | Every dataset with its audit decision and required citation, and every cited work with record counts |
| `GET /health` | | Liveness |

`open_only=true` hides every dataset the audit does not approve for redistribution. It works on every route that takes it: search, the graph, `related` (documented items, inferred chains and the candidate pool), the technique searches, and, on `/lexemes/{id}` and `/relationships/{id}`, it answers 404 for a record of such a dataset. `open_only` defaults to false everywhere.

**Evidence kinds.** Every item of `related` says how it is known:

| `evidence_kind` | Layer | Carries |
|---|---|---|
| `documented` | `documented` | The relationship a source states: dataset, type, and its evidence rows (citation, locator). The only kind shown as a cited fact. |
| `inferred` | `inferred` | A chain of documented ancestry relationships (ids, datasets, citations) that puts two words under one ancestor, and the rule version. A proof over cited steps, not a new claim. |
| `computed` | `candidate` | A method, its parameters, a score, the gate that made the words comparable and a calibrated precision. No citation. |

The blocks are never merged or re-ordered into one list. If a layer's tables are not built, its block has `status: unavailable` and the others are still returned. A technique search says in `technique` how its matches were found.

## 7. Query pipeline

1. Validate the query (length, control characters) and normalise it to NFC, keeping the original.
2. Detect the script and the languages that use it; apply the optional `language_id`.
3. Find exact matches on the normalised form and the native form.
4. For a native-script query, romanise it with the rule-based ISO 15919 converter, trying the readings the script leaves open (inherent vowels, anusvara). For a romanised query, look up the transliteration aliases to get native spellings, which take the same path.
5. Keep whole words apart from stems, affixes and compounds.
6. Retrieve spelling candidates separately, with `pg_trgm`; they are returned in their own field and never drawn as relationships.
7. Build a bounded subgraph around the chosen word: documented relationships only, deduplicated, with direction kept.

`/lexemes/{id}/related` and the technique searches are separate paths. They read the documented links for the first block and the `layers` schema (or compute on request) for the others; they never write to `public`.

## 8. Front end

Hash routes (`#/`, `#/explore?q=…&lang=…`, `#/methodology`), so the build is a static site. `graphModel.ts` merges duplicate records, applies the type and language filters, caps neighbours ("show all" lifts the cap) and writes the sentence for each edge. `GraphCanvas.tsx` only draws. Download JSON, SVG and PNG buttons above the graph save the words and links shown (`graphExport.ts`). `sourceLabels.ts` shows plain-English source labels, so a reader sees "Wiktionary descendants list" rather than `{{desc}}`; the stored data is unchanged. A table beside the canvas is the accessible fallback and stays in step with the selection. Research-use records show a "Research use, not redistributed" note with the citation; the *Open data only* switch sends `open_only=true`.

## 9. Security and operations

- The browser never sees database credentials or source files; the API validates and bounds its parameters (query length, `limit`, `depth`, `limit_nodes`).
- CORS allows only the origins in `CORS_ORIGINS`.
- Restricted data stays out of images, downloads and seeds: the audit decides what the seed builder exports, `validate --public-seed` fails on anything else, and `data/raw/`, `data/research_dump/` and `reports/` are git-ignored.
- A site serving the research database serves research-use data: keep it on a private network, or share it only with people the research-use terms allow.
- Migrations and import manifests are in version control; every input is pinned by commit or SHA-256 in `data/manifests/downloads.json`.
