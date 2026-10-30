# Linguistic DNA documentation

An interactive, evidence-backed graph of how words in India's languages are related. Users enter a word in a supported native script or in romanisation and explore documented historical relationships (inheritance, borrowing, derivation, composition, cognacy) in a navigable graph, with the source of every link. Resemblance in spelling or sound is listed separately, as candidates, and never drawn as a relationship.

Back to the [project README](../README.md).

<p align="center"><a href="media/demo.mp4"><img src="media/demo.gif" width="760" alt="Demo of searching, expanding the graph and opening a link's evidence"></a></p>

## Reading order

**If you are a researcher or linguist**, start with what the data says and where it comes from:

1. [`WRITEUP.md`](WRITEUP.md): the problem, what the app does, design decisions and limitations. Its "Numbers" section is a snapshot from before the research expansion; current figures are in the project README's *At a glance* table.
2. [`DATASET_LICENCE_AUDIT.md`](DATASET_LICENCE_AUDIT.md): **the authority** on every dataset, its licence evidence, the decision (APPROVED, RESEARCH USE, BLOCKED), counts, and how each source is mapped to link types.
3. [`LINGUISTIC_ENGINE.md`](LINGUISTIC_ENGINE.md): relationship types, what counts as evidence, and why similarity is never evidence.
4. [`DATASET_AUDIT.md`](DATASET_AUDIT.md): the first audit of Jambu's coverage and schema.
5. [`EVALUATION_AND_TESTING.md`](EVALUATION_AND_TESTING.md): benchmark design and how relationship quality is measured.

**If you are a developer**, start with how to build and run it:

1. [`DATA_PIPELINE.md`](DATA_PIPELINE.md): fetching pinned inputs, the import commands, validation, and building the open seed.
2. [`TECHNICAL_ARCHITECTURE.md`](TECHNICAL_ARCHITECTURE.md): stack, database model and APIs.
3. [`DEPLOYMENT.md`](DEPLOYMENT.md): Docker API plus static site, and hosting the research version.
4. [`DATASET_LICENCE_AUDIT.md`](DATASET_LICENCE_AUDIT.md) §4 and §6: what may be published, and how the validator enforces it.
5. [`PROJECT_SPECIFICATION.md`](PROJECT_SPECIFICATION.md) and [`DEVELOPMENT_ROADMAP.md`](DEVELOPMENT_ROADMAP.md): the original requirements and plan.

## Every document

| Document | What it is |
|---|---|
| [`WRITEUP.md`](WRITEUP.md) | Technical write-up: problem, architecture, design decisions, testing, limitations |
| [`DATASET_LICENCE_AUDIT.md`](DATASET_LICENCE_AUDIT.md) | Licence audit and decisions for every dataset; research-use rules; release-gate status (authoritative) |
| [`DATASET_AND_LICENSING_PLAN.md`](DATASET_AND_LICENSING_PLAN.md) | The original plan: sources to investigate, provenance model, licence checks |
| [`DATASET_AUDIT.md`](DATASET_AUDIT.md) | Audit of Jambu (`moli-mandala/data`): coverage, schema fit, licence status |
| [`DATA_PIPELINE.md`](DATA_PIPELINE.md) | Rebuilding the databases from pinned upstream inputs; the public seed |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Deploying the open demo and the research version |
| [`TECHNICAL_ARCHITECTURE.md`](TECHNICAL_ARCHITECTURE.md) | Frontend and backend architecture, APIs, database model, security |
| [`LINGUISTIC_ENGINE.md`](LINGUISTIC_ENGINE.md) | Query pipeline, relationship types, similarity metrics, graph construction |
| [`EVALUATION_AND_TESTING.md`](EVALUATION_AND_TESTING.md) | Benchmark design, metrics and test plan |
| [`PROJECT_SPECIFICATION.md`](PROJECT_SPECIFICATION.md) | Vision, scope, functional requirements, acceptance criteria |
| [`DEVELOPMENT_ROADMAP.md`](DEVELOPMENT_ROADMAP.md) | The six-week MVP plan, deliverables and Definition of Done |

Related files outside `docs/`: [`data/manifests/dataset_audit.csv`](../data/manifests/dataset_audit.csv) (the machine-readable audit), [`data/manifests/downloads.json`](../data/manifests/downloads.json) (pinned inputs), [`data/public_seed/ATTRIBUTION.md`](../data/public_seed/ATTRIBUTION.md) (credits for the open seed), and [`data/config/languages.csv`](../data/config/languages.csv) (configured languages).

## Media

Screenshots and the demo recording in [`media/`](media/) were captured from a local build against the research database on 2026-10-30, at 1440 px wide (phone views at 390 px). Research-use records in them are shown with their citations, for research presentation; the underlying data is never stored in this repository.

| File | Shows |
|---|---|
| [`demo.gif`](media/demo.gif), [`demo.mp4`](media/demo.mp4) | 39 s walkthrough: search, pick a match, expand, open a link's evidence |
| [`explore-hindi-paani-chain.png`](media/explore-hindi-paani-chain.png) | Hindi पानी → Prakrit पाणीअ → Sanskrit पानीय (Wikidata), with the evidence panel |
| [`explore-punjabi-paani.png`](media/explore-punjabi-paani.png) | Punjabi ਪਾਣੀ restricted to Punjabi |
| [`explore-kannada-niru-proto-dravidian.png`](media/explore-kannada-niru-proto-dravidian.png) | Kannada ನೀರು expanded to Proto-Dravidian *\*kaṇ-ṇīr* (DEDR via Jambu) |
| [`evidence-borrowed-nira-cdial.png`](media/evidence-borrowed-nira-cdial.png) | Evidence for Old Indo-Aryan *nīrá* borrowed from *\*kaṇ-ṇīr* (CDIAL) |
| [`research-use-badge.png`](media/research-use-badge.png) | The "Research use, not redistributed" note, close up |
| [`explore-kannada-hallu.png`](media/explore-kannada-hallu.png) | Kannada ಹಲ್ಲು "tooth" with cognates (Wiktionary) |
| [`open-data-cognates-jibh.png`](media/open-data-cognates-jibh.png) | *Open data only*: Marathi जीभ "tongue" and its cognates |
| [`home.png`](media/home.png), [`mobile-home.png`](media/mobile-home.png), [`mobile-explore.png`](media/mobile-explore.png) | Landing page, and phone views |
| [`methodology-how-to-cite.png`](media/methodology-how-to-cite.png), [`methodology-coverage.png`](media/methodology-coverage.png) | The methodology page's *How to cite* and coverage sections |
| [`coverage-by-language.svg`](media/coverage-by-language.svg) | Words per language, open seed vs research database (read-only DB query) |

## Non-negotiable product principles

1. Surface resemblance is not proof of common ancestry.
2. Similar meanings are not proof of common ancestry.
3. Every documented historical relationship must be traceable to a source record.
4. Algorithm-generated matches must be labelled as candidates, not facts.
5. Reconstructed forms must be clearly marked, conventionally with an asterisk, and never presented as directly attested forms.
6. Source-data licence and attribution requirements must be checked before redistribution.

## Main reference resources

- Jambu: <https://aryaman.io/jambu/> and data repository <https://github.com/moli-mandala/data>
- Glottolog: <https://glottolog.org/> and downloads <https://glottolog.org/download>
- CLDF: <https://cldf.clld.org/>
- AI4Bharat transliteration resources: <https://ai4bharat.iitm.ac.in/areas/xlit/> and IndicXlit <https://indicnlp.ai4bharat.org/indic-xlit/>
- Digital Dictionaries of South Asia: <https://dsal.uchicago.edu/dictionaries/>
- Bharatavani: <https://bharatavani.in/>
- PostgreSQL `pg_trgm`: <https://www.postgresql.org/docs/17/pgtrgm.html>
- Cytoscape.js: <https://js.cytoscape.org/>
