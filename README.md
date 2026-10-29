# Linguistic DNA — Language Similarity Graph

An interactive, evidence-backed platform for exploring relationships between words across Indian languages: documented historical relationships, borrowing, orthographic and phonetic similarity, and semantic relations, presented as a navigable graph.

**Status:** Phase 1 (data correctness and licensing) of the [revised roadmap](#roadmap). A working local demo exists, and the public dataset is being assembled from audit-approved sources only.

The API serves `/api/v1/search`, `/lexemes/{id}`, `/graph/{id}`, `/relationships/{id}` and `/languages`; interactive docs are at `http://localhost:8000/docs`.

## Roadmap

1. **Phase 1, data correctness and licensing (current).**
   - Licence audit of the shortlisted datasets.
   - Imports of Glottolog, Concepticon, LSI, ASJP and Wikidata Lexemes, with provenance.
   - Exact matches separated from stems and compounds.
   - A public seed built only from approved data.
   - A seed benchmark awaiting human review.
2. **Phase 2, script support and graph.** Transliteration aliases from Dakshina and the approved Aksharantar components, native-script search across all languages, and graph clutter control.
3. **Phase 3, portfolio polish.** Landing page, methodology page, public demo, write-up.
4. **Phase 4, expansion.** Starts only after the release gate below is met.

**Release gate before Phase 4:**
- every deployed dataset component has documented reuse permission;
- native-script and romanised searches pass a multilingual regression suite;
- exact matches are not confused with compounds or approximate matches;
- every documented historical relationship has traceable evidence;
- the graph stays usable for dense results and on small screens;
- the demo and repository explain their sources and limitations.

Current status of each condition is tracked in [`docs/DATASET_LICENCE_AUDIT.md`](docs/DATASET_LICENCE_AUDIT.md) §7.

## Documentation

- [`docs/DATASET_AND_LICENSING_PLAN.md`](docs/DATASET_AND_LICENSING_PLAN.md) — sources, provenance and licence checks
- [`docs/TECHNICAL_ARCHITECTURE.md`](docs/TECHNICAL_ARCHITECTURE.md) — stack, database model and APIs
- [`docs/DATASET_LICENCE_AUDIT.md`](docs/DATASET_LICENCE_AUDIT.md) — which datasets may be published, and why (authoritative)
- [`docs/DATASET_AUDIT.md`](docs/DATASET_AUDIT.md) — audit of Jambu: coverage, schema fit, licences
- [`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md) — how to rebuild the database from pinned inputs
- [`docs/README.md`](docs/README.md) — full documentation map

## Repository layout

```text
backend/    FastAPI app, SQLAlchemy models, Alembic migrations, importers, tests
frontend/   React + TypeScript + Vite + Tailwind
data/       config/ (target languages), manifests/ (source licences); raw/ is git-ignored
scripts/    audit and fixture helpers
docs/       specification, architecture, data plan, audit, pipeline
```

## Quick start

Requires Python 3.12+, Node 22 and Docker (or your own PostgreSQL 16).

```bash
make setup db-up migrate
```

**Option A: load the committed public seed.** No downloads needed.

```bash
make load-public-seed
```

**Option B: rebuild from the upstream sources.** All inputs are pinned by commit or checksum in `data/manifests/downloads.json`.

```bash
make fetch-data import-open validate
```

For the local research database, which also includes the restricted Jambu data and is never deployed:

```bash
make fetch-dev-data import-jambu
```

Run the app:

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload
```

```bash
cd frontend && npm run dev
```

## Data sources and attribution

The public seed contains only datasets the licence audit approves. Their attributions are generated into [`data/public_seed/ATTRIBUTION.md`](data/public_seed/ATTRIBUTION.md):

- Glottolog (CC-BY-4.0)
- Concepticon (CC-BY-4.0)
- the Linguistic Survey of India CLDF dataset (CC-BY-4.0)
- ASJP (CC-BY-4.0)
- Wikidata Lexemes (CC0)

Jambu, CDIAL and DEDR are used only in local development databases and are never redistributed. See [`docs/DATASET_LICENCE_AUDIT.md`](docs/DATASET_LICENCE_AUDIT.md).
