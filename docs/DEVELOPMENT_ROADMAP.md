# Development Roadmap — Language Similarity Graph

## 1. Plan overview

This is a six-week MVP plan for a solo developer or a small team. It assumes the core deliverable is a polished word-search and graph-exploration experience, not sentence analysis or historical text search.

The schedule is a planning baseline. Re-estimate after the Week 1 source-data audit because source coverage and licensing can change implementation scope.

## 2. Week-by-week plan

### Week 1 — Source audit and foundation

**Objectives**

- inspect candidate datasets and their schemas;
- verify language coverage and source-level reuse terms;
- agree on relationship vocabulary and database identifiers;
- create a minimal working application skeleton.

**Tasks**

1. Review Jambu's public data repository, documentation, conversion scripts, and source metadata.
2. Inspect Glottolog release files for the selected languages and classification metadata.
3. Create a language coverage report: lexical forms, concepts, historical edges, transliterations, pronunciations, and source status.
4. Create `source_manifest.csv` and classify sources as approved, attribution-required, permission-required, unknown, or excluded.
5. Finalize the first data slice and entity schema.
6. Create Git repository, frontend/backend skeletons, linting, tests, and local environment configuration.

**Deliverables**

- source inventory and licence audit;
- language coverage report;
- database schema draft;
- project setup that runs locally.

**Exit criteria**

A small dataset slice has a defensible reuse basis and enough evidence to demonstrate the intended graph. If not, reduce the dataset or rely on source links rather than redistributing restricted records.

### Week 2 — Import pipeline and database

**Objectives**

Build a repeatable, validated path from upstream source files to local database records.

**Tasks**

1. Implement source-specific/CLDF import adapters.
2. Preserve source IDs, citations, versions, and licensing metadata.
3. Normalize search strings while preserving raw forms.
4. Implement stable internal IDs and relation-type mapping.
5. Add database migrations and indexes.
6. Add schema, referential integrity, duplicate, and provenance checks.
7. Generate an automated coverage report after import.

**Deliverables**

- import command;
- database migrations;
- reproducible seed data for approved records;
- validation report.

**Exit criteria**

A clean database can be recreated from the versioned inputs/configuration, and documented edges retain their source links.

### Week 3 — Search API and retrieval

**Objectives**

Provide reliable lookup and useful candidate retrieval.

**Tasks**

1. Implement Unicode normalization and script detection.
2. Add direct normalized-form, alias, and language-filtered queries.
3. Add fuzzy spelling retrieval using edit/trigram similarity.
4. Add phonetic ranking only where a credible phonetic representation is present.
5. Retrieve documented relationships separately from computed candidates.
6. Implement bounded graph assembly and relationship filters.
7. Write tests for exact, ambiguous, unknown, reconstructed, and homonymous inputs.

**Deliverables**

- search, lexeme, relationship, and graph endpoints;
- API schema and sample responses;
- automated API test suite.

**Exit criteria**

Core queries return stable results with the relation type, status, and evidence metadata intact.

### Week 4 — Interactive web experience

**Objectives**

Deliver the core end-user workflow.

**Tasks**

1. Build the search page, language picker, and query examples.
2. Integrate Cytoscape.js for graph rendering and interaction.
3. Implement edge legend, filters, expansion/collapse, and graph limits.
4. Implement lexeme detail and evidence panels.
5. Add clear states for loading, no result, ambiguity, disputed evidence, and backend error.
6. Test layout across desktop/mobile widths and supported scripts.
7. Add keyboard navigation and a list/table fallback for graph information.

**Deliverables**

- end-to-end search-to-graph interaction;
- responsive layout;
- evidence panel and legend.

**Exit criteria**

A user can search a supported word, explore relevant connections, and inspect the reason/source for a documented relation.

### Week 5 — Evaluation and refinement

**Objectives**

Test reliability rather than relying on visual impressions.

**Tasks**

1. Build manually reviewed positive, negative, and ambiguous test pairs.
2. Measure exact lookup and alias/transliteration success.
3. Measure spelling and phonetic candidate precision separately.
4. Audit source traceability and directionality.
5. Review false positives and adjust retrieval thresholds.
6. Profile API latency and graph render time.
7. Conduct a small usability test focused on whether users understand uncertainty.

**Deliverables**

- benchmark dataset with permitted content;
- evaluation report;
- bug list and fixes;
- documented limitations.

**Exit criteria**

Metrics and known failure modes are reported honestly, and algorithmic candidates cannot be mistaken for documented historical facts.

### Week 6 — Deployment and portfolio packaging

**Objectives**

Publish a reproducible, polished demo.

**Tasks**

1. Deploy the React frontend.
2. Containerize and deploy FastAPI.
3. Configure managed PostgreSQL, migrations, and approved data seed.
4. Set environment variables and CORS rules; keep secrets out of Git.
5. Add basic logging and error handling.
6. Verify production data-source restrictions and attributions.
7. Prepare README, architecture diagram, screenshots, and a short demo script/video.
8. Add sample searches with known data coverage and explain their expected result types.

**Deliverables**

- public demo URL;
- setup instructions;
- source and licence manifest;
- benchmark summary;
- portfolio screenshots/demo video;
- known limitations section.

**Exit criteria**

A reviewer can open the demo, complete the main workflow, understand the relationships, and reproduce the core development environment from the repository instructions.

## 3. Milestone gates

| Gate | Must be true before continuing |
|---|---|
| Data gate | Source-level reuse basis understood; coverage and gaps reported |
| API gate | Exact lookup, provenance retrieval, and graph responses tested |
| UX gate | Graph edges are typed; evidence is accessible; uncertainty is visible |
| Evaluation gate | Benchmark includes hard negatives and ambiguous forms |
| Release gate | Public data slice is approved, deployment reproducible, and limitations documented |

Do not compensate for weak data by adding a larger model. Fix coverage, provenance, and normalization first.

## 4. Suggested weekly task tracking

For each task, track:

- ID;
- description;
- owner;
- priority;
- status;
- dependency;
- acceptance test;
- link to pull request or artifact;
- notes/blockers.

Keep data ingestion/licensing tasks visible in the same tracker as implementation. They are release-critical, not optional administrative work.

## 5. What to defer if time is constrained

Defer in this order:

1. semantic embeddings and learned ranking;
2. advanced language identification;
3. broad dialect expansion;
4. audio pronunciation;
5. historical text search;
6. sentence analysis.

Do not defer source traceability, clear relationship types, unknown-result handling, or basic evaluation. Those are central to the product's credibility.
