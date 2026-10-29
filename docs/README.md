# Language Similarity Graph

An interactive, evidence-backed platform for exploring relationships between words across Indian languages. Users enter a word in a supported native script or transliteration and explore documented historical relationships, borrowing, orthographic similarity, phonetic similarity, and semantic relationships in a navigable graph.

## Documentation map

- [`PROJECT_SPECIFICATION.md`](PROJECT_SPECIFICATION.md) — vision, scope, functional requirements, and acceptance criteria.
- [`TECHNICAL_ARCHITECTURE.md`](TECHNICAL_ARCHITECTURE.md) — frontend/backend architecture, APIs, database model, deployment, and security.
- [`DATASET_AND_LICENSING_PLAN.md`](DATASET_AND_LICENSING_PLAN.md) — source inventory, import strategy, provenance, and licence checks.
- [`LINGUISTIC_ENGINE.md`](LINGUISTIC_ENGINE.md) — query pipeline, relationship types, similarity metrics, and graph construction.
- [`EVALUATION_AND_TESTING.md`](EVALUATION_AND_TESTING.md) — benchmark design, metrics, and test plan.
- [`DEVELOPMENT_ROADMAP.md`](DEVELOPMENT_ROADMAP.md) — six-week MVP plan, deliverables, and Definition of Done.

## MVP summary

- **Goal:** polished portfolio project with a credible linguistic data pipeline.
- **Input:** individual words; sentence input is deferred.
- **Initial coverage:** selected Indo-Aryan and Dravidian languages, subject to source-data coverage.
- **Relationship categories:** historical/cognate relationships, borrowing, spelling similarity, phonetic similarity, and semantic relations. These must remain distinct in storage and presentation.
- **Historical text search:** deferred until the core graph is reliable.
- **Suggested stack:** React + TypeScript + Vite, Cytoscape.js, Python + FastAPI, PostgreSQL, and a repeatable offline ingestion pipeline.

## Non-negotiable product principles

1. Surface resemblance is not proof of common ancestry.
2. Similar meanings are not proof of common ancestry.
3. Every documented historical relationship must be traceable to a source record.
4. Algorithm-generated matches must be labelled as candidates, not facts.
5. Reconstructed forms must be clearly marked, conventionally with an asterisk, and never presented as directly attested forms.
6. Source-data licence and attribution requirements must be checked before redistribution.

## Initial language set

A suggested starting set of 11 modern languages:

- **Indo-Aryan:** Hindi, Bengali, Marathi, Gujarati, Punjabi, Odia, Assamese.
- **Dravidian:** Tamil, Telugu, Kannada, Malayalam.
- **Historical/reference forms:** Sanskrit and documented Prakrit forms where the selected sources support them.

This is a proposed scope, not a guarantee that every language has complete or equally reliable etymological coverage. Confirm coverage in the dataset audit before finalizing release commitments.

## Main reference resources

- Jambu: <https://aryaman.io/jambu/> and data repository <https://github.com/moli-mandala/data>
- Glottolog: <https://glottolog.org/> and downloads <https://glottolog.org/download>
- CLDF: <https://cldf.clld.org/>
- AI4Bharat transliteration resources: <https://ai4bharat.iitm.ac.in/areas/xlit/> and IndicXlit <https://indicnlp.ai4bharat.org/indic-xlit/>
- Digital Dictionaries of South Asia: <https://dsal.uchicago.edu/dictionaries/>
- Bharatavani: <https://bharatavani.in/>
- PostgreSQL `pg_trgm`: <https://www.postgresql.org/docs/17/pgtrgm.html>
- Cytoscape.js: <https://js.cytoscape.org/>

See the data and licensing document before incorporating any external records into a public deployment.
