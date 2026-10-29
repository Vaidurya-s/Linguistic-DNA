# Linguistic DNA — Language Similarity Graph

An interactive, evidence-backed platform for exploring relationships between words across Indian languages: documented historical relationships, borrowing, orthographic and phonetic similarity, and semantic relations, presented as a navigable graph.

**Status:** a working local demo.

- **Weeks 1–2 (done):** source audit, schema, and a repeatable import of Jambu and Glottolog into PostgreSQL, with validation and coverage reports.
- **Weeks 3–4 (first version):**
  - search with exact, native-script and diacritic-insensitive matching; similar spellings are listed separately as candidates;
  - a word-relationship graph you can expand node by node;
  - an evidence panel showing each link's citations and licence status;
  - a table view of the same links.

The API serves `/api/v1/search`, `/lexemes/{id}`, `/graph/{id}`, `/relationships/{id}` and `/languages`. Interactive docs are at `http://localhost:8000/docs`.

There is no public dataset or deployment yet: most historical links come from sources whose reuse permission is still pending. See [`docs/DATASET_AUDIT.md`](docs/DATASET_AUDIT.md).

## Documentation

- [`docs/DATASET_AND_LICENSING_PLAN.md`](docs/DATASET_AND_LICENSING_PLAN.md) — sources, provenance and licence checks
- [`docs/TECHNICAL_ARCHITECTURE.md`](docs/TECHNICAL_ARCHITECTURE.md) — stack, database model and APIs
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
make setup
```

```bash
make db-up
```

```bash
make migrate test lint
```

To load the full development dataset, fetch the pinned inputs listed in [`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md), then:

```bash
make import-jambu import-glottolog validate coverage
```

Run the app locally:

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload
```

```bash
cd frontend && npm run dev
```

## Data sources and attribution

Language classification comes from [Glottolog](https://glottolog.org) (CC-BY-4.0): Hammarström, Harald & Forkel, Robert & Haspelmath, Martin & Bank, Sebastian. 2025. *Glottolog 5.2.1*. Leipzig: Max Planck Institute for Evolutionary Anthropology.

Lexical data comes from [Jambu](https://github.com/moli-mandala/data). Each source's licence status is tracked in [`data/manifests/source_manifest.csv`](data/manifests/source_manifest.csv).
