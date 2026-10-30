<div align="center">

# Linguistic DNA

**An evidence-first graph of how words in India's languages are related.**

Type a word in any of 9 Brahmic scripts or in romanisation, and follow its documented links:
what it was inherited from, borrowed from, built from, or is cognate with, with the source for every claim.

[![CI](https://github.com/Vaidurya-s/Linguistic-DNA/actions/workflows/ci.yml/badge.svg)](https://github.com/Vaidurya-s/Linguistic-DNA/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pg__trgm-4169E1?logo=postgresql&logoColor=white)
![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Cytoscape.js](https://img.shields.io/badge/graph-Cytoscape.js-F7DF1E)
![Languages](https://img.shields.io/badge/languages-19%20modern%20%2B%206%20historical-8A2BE2)

[What it does](#what-it-does) ·
[At a glance](#at-a-glance) ·
[Gallery](#gallery) ·
[Quick start](#quick-start) ·
[Open data vs research use](#open-data-vs-research-use) ·
[How to cite](#how-to-cite) ·
[Docs](docs/README.md)

<a href="docs/media/demo.mp4"><img src="docs/media/demo.gif" width="900" alt="Demo: searching nīru in Kannada, expanding to Proto-Dravidian *kaṇ-ṇīr, opening the evidence for Old Indo-Aryan nīrá borrowed from it; then Hindi पानी, its Prakrit source पाणीअ and Sanskrit पानीय"></a>

<sub>39-second walkthrough (click for the <a href="docs/media/demo.mp4">MP4</a>). Kannada <i>nīru</i> → Proto-Dravidian <i>*kaṇ-ṇīr</i> → the CDIAL record saying Sanskrit <i>nīrá</i> was borrowed from it; then Hindi पानी → Prakrit पाणीअ → Sanskrit पानीय from Wikidata.</sub>

</div>

---

## What it does

**Search the way people actually write.** पानी, *paani*, *pānī* and ਪਾਣੀ land on the same records. A rule-based ISO 15919 romaniser covers Devanagari, Bengali-Assamese, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada and Malayalam, and casual spellings resolve through Dakshina and Aksharantar spelling pairs. Each match says how it was found, for example `paani → पानी (dakshina) → pānī`.

**Every edge is a sentence with a citation.** Links are typed and directed, and each one opens to its evidence: the dataset, the work it cites, the entry or page, and the licence. "ਪਾਣੀ (Punjabi) comes from पाणीअ (Prakrit)" is a claim you can check, not a picture.

**Resemblance is never drawn as relationship.** Words that merely look alike are listed separately as *candidates*, with a score that is explicitly not a measure of relatedness. Reconstructed forms keep their asterisk and are never shown as attested.

**Built for research, careful about redistribution.** The richest sources on Indo-Aryan and Dravidian word history (Turner's CDIAL, Burrow & Emeneau's DEDR) are still in copyright. They are used for research with a citation on every record, but never committed here or put in the downloadable open data. An *Open data only* switch shows what remains without them.

## At a glance

> [!NOTE]
> Headline numbers, as of **2026-10-30**. They change as sources are added; refresh them from the databases (`SELECT count(*) FROM lexeme`, `relationship`, `evidence`, `transliteration_alias`) or from `data/public_seed/manifest.json`.

| | Open public seed<br/><sub>`data/public_seed`, committed</sub> | Research database<br/><sub>open + research-use sources, built locally</sub> |
|---|---:|---:|
| Words | **521,448** | **1,812,733** |
| Documented, cited relationships | **221,594** | **996,776** |
| Evidence rows (citations with locators) | 221,594 | 1,060,069 |
| Transliteration spelling pairs | 947,189 | 947,189 |
| Concepts linking meanings across wordlists | 1,393 | 4,033 |
| Sources cited on individual records | 12 | 538 |
| Size | ≈ 55 MB compressed, ≈ 680 MB loaded | ≈ 2.1 GB |
| Searchable languages | 25 | 25 |

**25 searchable languages** (configured in [`data/config/languages.csv`](data/config/languages.csv)):

| Group | Languages |
|---|---|
| Indo-Aryan | Assamese, Awadhi, Bengali, Bhojpuri, Dogri, Gujarati, Hindi-Urdu, Konkani, Maithili, Marathi, Marwari, Nepali, Odia, Punjabi |
| Dravidian | Kannada, Malayalam, Tamil, Telugu |
| Sino-Tibetan | Bodo |
| Historical and reference | Sanskrit, Pali, Prakrit, Apabhramsha, Ashokan Prakrit, Old Indo-Aryan (CDIAL headwords) |

<p align="center">
  <img src="docs/media/coverage-by-language.svg" width="820" alt="Bar chart of words per language in the open public seed and in the research database, grouped by family. Sanskrit has the most (201,119 open / 441,480 research); Bodo the fewest (331 / 442).">
</p>

<sub>Generated from read-only queries of both databases on 2026-10-30. Coverage is very uneven, and the app shows it as such: the live per-language table, with how many words have at least one documented link, is on the app's *Data &amp; methodology* page.</sub>

## A word's history, as the sources tell it

Two chains from the research database, every step a stored relationship with its evidence row. Blue nodes are open data; orange nodes come from research-use sources.

```mermaid
flowchart LR
  hin["पानी<br/><sub>Hindi · water</sub>"]
  pan["ਪਾਣੀ<br/><sub>Punjabi · water</sub>"]
  pra["पाणीअ<br/><sub>Prakrit</sub>"]
  san["पानीय<br/><sub>Sanskrit · drinkable; water</sub>"]
  hinr["pānī<br/><sub>Hindi</sub>"]
  oia["pānī́ya<br/><sub>Old Indo-Aryan · water</sub>"]
  hin -- "from · Wikidata P5191" --> pra
  pan -- "from · Wikidata P5191" --> pra
  pra -- "from · Wikidata P5191" --> san
  hinr -- "inherited · CDIAL 8082" --> oia
  classDef open fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b
  classDef research fill:#fdeee6,stroke:#eb6834,color:#0b0b0b
  class hin,pan,pra,san open
  class hinr,oia research
```

The Wikidata steps cite the reference recorded on each statement (`stated in Q115652507, p. 452`). Wikidata's "derived from" does not say whether a word was inherited or borrowed, so the app shows it as **from**, not as either.

```mermaid
flowchart BT
  pdr["*kaṇ-ṇīr<br/><sub>Proto-Dravidian · tear; water</sub>"]
  kan["ನೀರು nīru<br/><sub>Kannada</sub>"]
  tam["nīr<br/><sub>Tamil</sub>"]
  tel["nīru<br/><sub>Telugu</sub>"]
  mal["nīr<br/><sub>Malayalam</sub>"]
  oia["nīrá<br/><sub>Old Indo-Aryan · water</sub>"]
  kan -- "inherited · DEDR 3690" --> pdr
  tam -- "inherited · DEDR 3690" --> pdr
  tel -- "inherited · DEDR 3690" --> pdr
  mal -- "inherited · DEDR 3690" --> pdr
  oia == "borrowed · CDIAL, EWA ii 172" ==> pdr
  classDef dra fill:#dcf5e9,stroke:#1baf7a,color:#0b0b0b
  classDef ia fill:#fdf3d6,stroke:#eda100,color:#0b0b0b
  classDef proto fill:#eef0f3,stroke:#64748b,color:#0b0b0b,stroke-dasharray:4 3
  class kan,tam,tel,mal dra
  class oia ia
  class pdr proto
```

Turner's CDIAL records Sanskrit *nīrá* "water" as a borrowing from the Dravidian word that DEDR reconstructs as *\*kaṇ-ṇīr*. Both claims reach the app through Jambu, cited per record.

## How the links are typed

Each source's own label is kept beside the normalised type, so nothing is silently reinterpreted. Counts are relationships in the research database / open seed (2026-10-30).

| Edge in the graph | Type | Reads as | Research / open |
|---|---|---|---:|
| ![](https://img.shields.io/badge/-inherited-2563eb) | `inherited_form` | *A* is a regular descendant of *B* | 404,328 / 29,646 |
| ![](https://img.shields.io/badge/-component-7c3aed) | `has_component` | compound or phrase *A* contains *B* | 298,754 / 50,231 |
| ![](https://img.shields.io/badge/-cognate-be123c) | `cognate` | *A* and *B* share an inherited origin (undirected) | 96,220 / 93,860 |
| ![](https://img.shields.io/badge/-related-0891b2) | `related_form` | the source relates them without saying how | 52,863 / 0 |
| ![](https://img.shields.io/badge/-derived-059669) | `derived_form` | *A* is derived from *B* (affixation, extension) | 49,091 / 0 |
| ![](https://img.shields.io/badge/-borrowed-ea580c) | `borrowed_from` | *A* was borrowed from *B* | 41,983 / 30,531 |
| ![](https://img.shields.io/badge/-variant-64748b) | `variant_of` | *A* is a documented variant of *B* | 36,193 / 0 |
| ![](https://img.shields.io/badge/-from-0f766e) | `etymon` | *A* comes from *B*; inherited or borrowed is not stated | 16,881 / 16,881 |
| ![](https://img.shields.io/badge/-calque-c2410c) | `calque_or_loan_translation` | *A* is a loan translation of *B* | 418 / 418 |
| ![](https://img.shields.io/badge/-influence-db2777) | `contact_influence` | *A* was influenced by *B* through contact | 18 / 0 |
| *listed, never drawn* | similarity candidates | similar spelling or sound, **not evidence of relation** | — |

## Gallery

<table>
  <tr>
    <td width="50%"><a href="docs/media/explore-hindi-paani-chain.png"><img src="docs/media/explore-hindi-paani-chain.png" alt="Hindi पानी with its Prakrit and Sanskrit sources and the Wikidata evidence panel"></a><br/><sub><b>A chain from open data.</b> Hindi पानी → Prakrit पाणीअ → Sanskrit पानीय, with the Wikidata statement and its reference.</sub></td>
    <td width="50%"><a href="docs/media/evidence-borrowed-nira-cdial.png"><img src="docs/media/evidence-borrowed-nira-cdial.png" alt="Evidence panel for nīrá borrowed from Proto-Dravidian, citing CDIAL with a research-use note"></a><br/><sub><b>Every edge opens to its evidence.</b> <i>nīrá</i> borrowed from <i>*kaṇ-ṇīr</i>: CDIAL, Mayrhofer's EWA, and the research-use note.</sub></td>
  </tr>
  <tr>
    <td><a href="docs/media/explore-kannada-niru-proto-dravidian.png"><img src="docs/media/explore-kannada-niru-proto-dravidian.png" alt="Graph around Proto-Dravidian *kaṇ-ṇīr with descendants in Kannada, Tamil, Malayalam, Telugu and Badaga"></a><br/><sub><b>Expanding a reconstruction.</b> Descendants of Proto-Dravidian <i>*kaṇ-ṇīr</i> across Dravidian, from DEDR via Jambu.</sub></td>
    <td><a href="docs/media/open-data-cognates-jibh.png"><img src="docs/media/open-data-cognates-jibh.png" alt="Open data only: Marathi जीभ with cognates across Indo-Aryan and its Sanskrit source"></a><br/><sub><b>Open data only.</b> Marathi जीभ "tongue": cognates and its Sanskrit source, all from openly licensed data.</sub></td>
  </tr>
  <tr>
    <td><a href="docs/media/explore-punjabi-paani.png"><img src="docs/media/explore-punjabi-paani.png" alt="Punjabi ਪਾਣੀ restricted to Punjabi, with its Prakrit source and compounds"></a><br/><sub><b>Native-script search, one language.</b> Punjabi ਪਾਣੀ, its Prakrit source and the compounds and sayings built on it.</sub></td>
    <td><a href="docs/media/explore-kannada-hallu.png"><img src="docs/media/explore-kannada-hallu.png" alt="Kannada ಹಲ್ಲು tooth with its Proto-Dravidian etymon and cognates in Telugu, Malayalam, Tamil and Sholaga"></a><br/><sub><b>Kannada script in, Dravidian history out.</b> ಹಲ್ಲು "tooth": inherited from Proto-Dravidian <i>pal</i> (reconstructed), with cognates in Telugu, Malayalam, Tamil and Sholaga (Wiktionary).</sub></td>
  </tr>
  <tr>
    <td><a href="docs/media/home.png"><img src="docs/media/home.png" alt="Landing page"></a><br/><sub><b>Landing page</b> with suggested searches.</sub></td>
    <td><a href="docs/media/methodology-how-to-cite.png"><img src="docs/media/methodology-how-to-cite.png" alt="How to cite section of the methodology page"></a><br/><sub><b>How to cite.</b> Every dataset with the citation it asks for, research-use or open, and record counts.</sub></td>
  </tr>
  <tr>
    <td><a href="docs/media/methodology-coverage.png"><img src="docs/media/methodology-coverage.png" alt="Coverage by language table"></a><br/><sub><b>Live coverage table</b> on the methodology page: words and words with links, per language.</sub></td>
    <td align="center"><a href="docs/media/mobile-explore.png"><img src="docs/media/mobile-explore.png" width="220" alt="Explore on a phone"></a> <a href="docs/media/mobile-home.png"><img src="docs/media/mobile-home.png" width="220" alt="Home on a phone"></a><br/><sub><b>Works on a phone.</b></sub></td>
  </tr>
</table>

<p align="center"><img src="docs/media/research-use-badge.png" width="352" alt="Evidence for nīrá borrowed from *kaṇ-ṇīr, with the amber 'Research use, not redistributed' note citing Turner's CDIAL"><br/><sub>The note every research-use record carries: cite the work, and the database it came from.</sub></p>

## Open data vs research use

Every dataset is a row in a machine-readable licence audit, [`data/manifests/dataset_audit.csv`](data/manifests/dataset_audit.csv), explained in [`docs/DATASET_LICENCE_AUDIT.md`](docs/DATASET_LICENCE_AUDIT.md). The importers, the validator and the seed builder all read it, so "may this be published?" is a query, not a judgement call made at release time.

| Decision | Datasets | Where it can appear |
|---|---|---|
| **APPROVED** / **APPROVED WITH CONDITIONS** | Glottolog, Concepticon, LSI, ASJP, Wikidata Lexemes, Wiktionary (wiktextract), IE-CoR, IELex, DravLex, NorthEuraLex, Hale's Nepal wordlists, Digital Corpus of Sanskrit lexicon, Dakshina, Aksharantar (approved components) | Everywhere, including the committed open seed, with attribution in [`data/public_seed/ATTRIBUTION.md`](data/public_seed/ATTRIBUTION.md) |
| **RESEARCH USE** | Jambu (and through it Turner's CDIAL, Burrow & Emeneau's DEDR and about 570 other works), Monier-Williams 1899 (Cologne), Digital Pāḷi Dictionary, Peiros' Sino-Tibetan wordlists | The research database and a research deployment, with a citation on every record. **Never** in this repository or the open seed |
| **BLOCKED** | everything unverified | Nowhere. `validate --research` fails on it |

In the app:
- research-use records carry a **"Research use, not redistributed"** note with the citation of the work and of the database it came from;
- **Open data only** in Explore hides research-use data from search and from the graph;
- `GET /api/v1/citations` lists every dataset with its required citation, and every work cited by individual records with record counts.

## Quick start

You need Python 3.12+, Node 22, and Docker (or your own PostgreSQL 16 with `pg_trgm`). [`REQUIREMENTS.md`](REQUIREMENTS.md) lists everything to install on Linux, with the commands; [`docs/DEPLOYMENT.md` § 6](docs/DEPLOYMENT.md#6-running-it-on-your-own-linux-machine) walks through running it on your own Linux machine, including sharing it through a tunnel.

```bash
make setup db-up migrate    # venv + npm install, Postgres in Docker, schema
```

**Open data, no downloads.** Load the committed public seed:

```bash
make load-public-seed
```

**Or rebuild the open data from upstream.** Every input is pinned by commit or SHA-256 in [`data/manifests/downloads.json`](data/manifests/downloads.json):

```bash
make fetch-data import-open validate
```

**The research database** adds the research-use sources, fetched from their own upstream (never from this repository):

```bash
make fetch-dev-data
make research-db            # open imports, research imports, Glottolog, re-key, validate --research
```

**Everything, in every language** (about 5,000 languages, with Wiktionary's full etymologies and descendant lists; about 100 GB of free disk recommended, see [`REQUIREMENTS.md`](REQUIREMENTS.md)):

```bash
make full-db                # all downloads, every import in every language, checks, size report
```

**Run the app** with `make serve-api` and `make serve-web` (a production build on :5173), or in development mode (the API reads `DATABASE_URL`, default `postgresql+psycopg://postgres@localhost:5432/lsg`):

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload    # API on :8000, OpenAPI docs at /docs
```

```bash
cd frontend && npm run dev                                # site on :5173, proxies /api to :8000
```

Then open <http://localhost:5173/#/explore?q=पानी&lang=hin>. There is no public hosted instance yet; [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) covers a Docker API plus a static site (GitHub Pages workflow included), and how to host the research version.

<details>
<summary><b>More make targets</b></summary>

| Target | What it does |
|---|---|
| `make validate` / `validate-public` / `validate-research` | Provenance and data-quality checks; the public mode fails on anything not approved, the research mode on any uncited research-use record |
| `make coverage` | Per-language coverage table in `reports/coverage.md` |
| `make benchmark` | Runs the relationship benchmark in `data/benchmark/` (results stay provisional until reviewed by a linguist) |
| `make public-seed` | Exports approved rows only to `data/public_seed/`, with `ATTRIBUTION.md` and a checksummed `manifest.json` |
| `make research-dump` | `pg_dump` of the research database into the git-ignored `data/research_dump/`, for a hosted research instance |
| `make test` / `make lint` | pytest against PostgreSQL and vitest; ruff, oxlint and tsc |

Full pipeline: [`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md).
</details>

<details>
<summary><b>API</b></summary>

All under `/api/v1`; interactive docs at `http://localhost:8000/docs`.

| Endpoint | Returns |
|---|---|
| `GET /search?q=…&language_id=…` | whole-word matches (with how each was found), stems and affixes, compounds, and spelling candidates |
| `GET /graph/{lexeme_id}` | the neighbourhood of a word: typed edges, capped for readability |
| `GET /lexemes/{id}`, `GET /relationships/{id}` | a word or a link with its source, citation and evidence |
| `GET /languages` | configured languages with word and linked-word counts |
| `GET /citations` | every dataset's required citation and every cited work, with counts |
| `GET /health` | liveness |

Every search and graph call accepts `open_only=true`.
</details>

## How it is built

```mermaid
flowchart LR
  subgraph OPEN["Open, redistributable (audit: APPROVED)"]
    direction TB
    o1["Glottolog · Concepticon"]
    o2["Wikidata Lexemes · Wiktionary"]
    o3["IE-CoR · IELex · DravLex<br/>NorthEuraLex · Hale · LSI · ASJP"]
    o4["DCS Sanskrit lexicon"]
    o5["Dakshina · Aksharantar<br/>(spelling pairs)"]
  end
  subgraph RES["Research use, cited per record"]
    direction TB
    r1["Jambu<br/>(CDIAL, DEDR, ~570 works)"]
    r2["Monier-Williams 1899"]
    r3["Digital Pali Dictionary"]
    r4["Peiros Sino-Tibetan"]
  end
  OPEN --> F["fetch_data.py<br/>pinned commits + sha256"]
  RES --> F
  F --> RAW[("data/raw<br/>git-ignored")]
  RAW --> IMP["Importers<br/>typed links + evidence"]
  AUD["dataset_audit.csv"] -. gates .-> IMP
  IMP --> DB[("Research database<br/>PostgreSQL 16 + pg_trgm")]
  DB --> V1{"validate --research"}
  DB --> SB["Seed builder<br/>approved rows only"]
  SB --> SEED[("data/public_seed<br/>committed")]
  SEED --> V2{"validate --public-seed"}
  V1 --> API["FastAPI"]
  V2 --> API
  API --> UI["React + Cytoscape"]
```

- **Back end:** FastAPI, SQLAlchemy and Alembic on PostgreSQL 16 with `pg_trgm`. Every word and link records the dataset it came from; every source points to an audit row. IDs are deterministic, so re-imports keep them.
- **Front end:** React 19, TypeScript, Vite, Tailwind and Cytoscape.js, with hash routes (`#/`, `#/explore?q=…&lang=…`, `#/methodology`), so it deploys as a static site. Graph shaping (merging duplicate records, filters, neighbour capping, edge sentences) is a pure, unit-tested module; the canvas only draws.
- **Search:** our own ISO 15919 romaniser for nine Brahmic scripts, with language-specific inherent-vowel and anusvara rules; whole words are kept apart from stems, affixes and compounds.

The design decisions are explained in [`docs/WRITEUP.md`](docs/WRITEUP.md).

<details>
<summary><b>Project structure</b></summary>

```text
backend/     FastAPI app, SQLAlchemy models, Alembic migrations, importers, validator, tests
frontend/    React + TypeScript + Vite + Tailwind + Cytoscape.js
data/
  config/      configured languages
  manifests/   licence audit, source manifest, pinned downloads
  public_seed/ the open seed: gzipped CSVs, ATTRIBUTION.md, manifest.json
  benchmark/   hand-picked relationship cases
  raw/         downloaded inputs (git-ignored)
scripts/     fetch_data.py and audit / fixture helpers
docs/        specification, architecture, licence audit, pipeline, deployment, write-up, media
```
</details>

## Roadmap

- [x] **Phase 1, data correctness and licensing.** Licence audit as data; provenance on every row; a public seed built only from approved data; exact matches separated from stems and compounds.
- [x] **Phase 2, scripts and graph.** Native-script and romanised search in 9 scripts; graph clutter control; eight more Devanagari languages (17 → 25).
- [x] **Phase 3, presentation.** Landing and methodology pages, write-up, Docker image and deployment docs.
- [x] **Research expansion.** Jambu in full, Wiktionary etymologies, expert cognate sets, Sanskrit and Pāli dictionaries, with per-record citations and the *Open data only* switch.
- [ ] **Hosted demo** of the open seed and of the research version ([`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)).
- [ ] **More scripts and languages:** Urdu, Kashmiri and Sindhi (Perso-Arabic), Santali (Ol Chiki), Manipuri (Meitei Mayek); then Tulu, Kodava, Kurukh, Khasi, Mizo.
- [ ] **Linguist review** of the benchmark, and a separately drawn *candidate* layer for computed similarity.

The release gate and its status are tracked in [`docs/DATASET_LICENCE_AUDIT.md`](docs/DATASET_LICENCE_AUDIT.md) §7.

## How to cite

When you use a word or a link from this project, **cite the work named on that record and the dataset it was taken from.** The exact citation for every dataset is in [`data/manifests/dataset_audit.csv`](data/manifests/dataset_audit.csv), served at `GET /api/v1/citations` and shown on the app's *Data &amp; methodology* page. The two dictionaries behind most Indo-Aryan and Dravidian word histories here:

> Turner, Ralph Lilley. 1962–1966. *A comparative dictionary of the Indo-Aryan languages*. London: Oxford University Press.
>
> Burrow, Thomas and Murray Barnson Emeneau. 1984. *A Dravidian Etymological Dictionary*. 2nd edn. Oxford: Clarendon Press.

and the database through which they reach this project:

> Arora, Aryaman, Adam Farris, Samopriya Basu and Suresh Kolichala. 2023. Jambu: A historical linguistic database for South Asian languages. *Proceedings of the 20th SIGMORPHON Workshop*, 68–77. ACL. doi:10.18653/v1/2023.sigmorphon-1.8

To cite this software, name the repository and the commit you used:

```text
Linguistic DNA: an evidence-first graph of word relationships in the languages of India.
https://github.com/Vaidurya-s/Linguistic-DNA, commit <hash>.
```

**Licensing.** The open seed carries the terms of its sources (CC0, CC BY 4.0, CC BY-SA 4.0 for Dakshina- and Wiktionary-derived rows), listed in [`data/public_seed/ATTRIBUTION.md`](data/public_seed/ATTRIBUTION.md). The repository does not yet include a licence file for its code.

## Acknowledgements

This project stands on the work of others: the compilers of CDIAL and DEDR; the Jambu team, who made decades of South Asian historical linguistics machine-readable; Glottolog, Concepticon and the Lexibank / CLDF community (LSI, ASJP, IE-CoR, IELex, DravLex, NorthEuraLex, Hale's Nepal, Peiros); Wikidata and Wiktionary contributors, and wiktextract / kaikki.org; the Digital Corpus of Sanskrit, the Cologne Digital Sanskrit Dictionaries and the Digital Pāḷi Dictionary; and Google Research's Dakshina and AI4Bharat's Aksharantar for transliteration data.

<div align="center"><sub>Surface resemblance is not proof of common ancestry. Every documented relationship here traces to a source.</sub></div>
