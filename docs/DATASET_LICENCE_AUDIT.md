# Dataset Acquisition and Licence Audit

This is the authority on what may enter the public application. The machine-readable version is [`data/manifests/dataset_audit.csv`](../data/manifests/dataset_audit.csv), with one row per dataset or separately licensed component. The importers, the validator and the public-seed builder all read it.

Audit date: 2026-10-29. Every input is pinned in [`data/manifests/downloads.json`](../data/manifests/downloads.json); fetch them with `make fetch-data`.

## 1. Decision rules

| Decision | Meaning |
|---|---|
| **APPROVED** | Licence verified on the records themselves, and it permits redistribution. |
| **APPROVED WITH CONDITIONS** | As above, but attribution, ShareAlike or a subset filter applies. |
| **RESEARCH USE** | No right to redistribute, but usable for academic research with a citation on every record. Allowed in the research database and the hosted research app; never in the public seed or the repository (section 4). |
| **BLOCKED** | Unverified, or not to be used at all. The reason is recorded. Fails `validate --research`. |

**What counts as verified.** A licence is "verified" only when it was read from the downloaded artefact itself: a LICENSE file, CLDF `dc:license`, a dataset card, or a README at a pinned commit. Each row names that evidence in `licence_evidence`. A licence quoted only from the research shortlist is marked "claimed", and its row stays BLOCKED.

**CC0 packaging is not enough.** CC0 on a package of third-party text does not clear the text inside it. Rows carrying that caveat stay BLOCKED until their upstream sources are identified.

## 2. Priority datasets (verified)

| Dataset | Version | Licence (evidence) | Decision | What it gives us |
|---|---|---|---|---|
| Glottolog | `glottolog-cldf` v5.3 (`072ca0d`) | CC-BY-4.0 (LICENSE, `dc:license`) | APPROVED WITH CONDITIONS | Language identity and family classification |
| ASJP | `lexibank/asjp` v21.1 (`cf4bf0d`) | CC-BY-4.0 (LICENSE, README, `dc:license`) | APPROVED WITH CONDITIONS | 2,266 forms in 25 doculects of our 12 languages; 40-concept lists in ASJPcode |
| Linguistic Survey of India | `lexibank/lsi` v1.1 (`133bcfc`) | CC-BY-4.0 (LICENSE, README, `dc:license`) | APPROVED WITH CONDITIONS | 3,602 forms in 18 doculects; Grierson 1928 comparative vocabulary |
| Concepticon | `concepticon-data` v3.4.0 (`918bc44`) | CC-BY-4.0 (`metadata.json` `dc:license`) | APPROVED WITH CONDITIONS | 4,033 concept sets that align meanings across all datasets |
| Wikidata Lexemes | dump 20261028 | CC0 (Wikidata:Licensing: "All structured data (i.e. the main, Property, Lexeme, and EntitySchema namespaces) is released into the public domain under Creative Commons Zero") | APPROVED | See §3 |
| Dakshina | v1.0 tarball (md5 matches the GCS hash) | CC-BY-SA-4.0 (README "License") | APPROVED WITH CONDITIONS (ShareAlike) | Native-script and romanised lexicons for 9 of our languages (Phase 2) |
| Aksharantar | HF revision `e418c1f` | Split by the `source` field on each record (dataset card "Licensing Information") | See below | Transliteration pairs (Phase 2) |

**Aksharantar is split into components by each record's `source` field.** Counts are for Hindi, which has 1,315,624 pairs:

| Component | `source` values | Hindi pairs | Decision |
|---|---|---:|---|
| Manually collected | AK-Freq, AK-NEI, AK-NEF | 14,820 | APPROVED WITH CONDITIONS (CC-BY) |
| From Wikidata | Wikidata | 25,012 | APPROVED (CC0 upstream) |
| From Dakshina | Dakshina | 31,295 | APPROVED WITH CONDITIONS: Dakshina's CC-BY-SA governs, since AI4Bharat's CC0 cannot remove it |
| Unnamed existing sources | Existing | 131,773 | BLOCKED: upstream not identified |
| Mined | IndicCorp, Samanantar | 1,112,724 | BLOCKED: "We do not own any of the text from which this data has been extracted" |

3,584 records (across all languages) spell the source `Ak-Freq`; they are treated as AK-Freq. AK-Uni (4,169 records) is not one of the approved components and is skipped.

The card is inconsistent about the manually collected part: it says CC-BY, and in another sentence waives all rights to "manually collected data". The stricter CC-BY reading is used.

**Neither LSI nor ASJP contains cognate judgments for our languages.** LSI has none at all. ASJP flags 43 forms as loans but names no donor. These datasets therefore add forms and concept-aligned meanings, but no historical links. The importers create no relationships from them; ASJP's loan flag is kept only as a tag.

## 3. Wikidata Lexemes in our languages

Import of dump 20261028: 89,772 lexemes in our languages, plus 1,527 lexemes in 40 other languages that their statements point to.

| Language | Lexemes | | Language | Lexemes |
|---|---:|---|---|---:|
| Malayalam | 67,388 | | Nepali | 23 |
| Bengali | 11,835 | | Bodo | 18 |
| Punjabi | 3,780 | | Bhojpuri | 15 |
| Hindi (via Hindustani Q11051) | 2,760 | | Pali | 14 |
| Tamil | 1,612 | | Assamese | 13 |
| Sanskrit | 1,469 | | Apabhramsha (Q616419) | 12 |
| Odia | 286 | | Konkani | 7 |
| Prakrit (Q192170) | 208 | | Dogri | 7 |
| Gujarati | 124 | | Maithili | 3 |
| Telugu | 87 | | Awadhi | 3 |
| Marathi | 82 | | Marwari | 0 |
| Kannada | 26 | | | |

Relationships:

| Statement | Imported as | Count | Of which have no reference |
|---|---|---:|---:|
| P5191 "derived from lexeme" | `etymon` | 4,000 | 972 |
| P5238 "combines lexemes" | `has_component` | 5,413 | 5,376 |

87 statements pointed to lexemes missing from the dump and were skipped.

Coverage is very uneven, and is shown as such. Wikidata is the only redistributable source of word-history links found so far, and it covers far fewer words than CDIAL or DEDR.

### Coverage of the eight languages added in Tier 1

Public seed, after the Tier 1 import. "With links" counts words that have at least one cited relationship.

| Language | Glottocode | LSI | ASJP | Wikidata | Total words | With links |
|---|---|---:|---:|---:|---:|---:|
| Nepali | `nepa1254` | 218 | 122 | 23 | 363 | 13 |
| Maithili | `mait1250` | 214 | 39 | 3 | 256 | 1 |
| Bodo | `bodo1269` | 183 | 41 | 18 | 242 | 0 |
| Awadhi | `awad1243` | 193 | 37 | 3 | 233 | 1 |
| Konkani | `konk1267` (+ `goan1235`, `konk1270`) | 174 | 44 | 7 | 225 | 0 |
| Marwari | `marw1260` | 200 | 24 | 0 | 224 | 0 |
| Dogri | `dogr1250` | 174 | 28 | 7 | 209 | 1 |
| Bhojpuri | `bhoj1244` | 0 | 58 | 15 | 73 | 4 |

These languages are searchable and appear in meaning-based comparisons, but they have almost no word-history links. The wordlists add words and meanings, not relationships. Aksharantar spelling pairs were added for Nepali, Maithili, Dogri, Bodo and Konkani, from the approved components only.

## 4. Research-use sources

The project now serves academic research. A source with no open licence, or one still in copyright, may be used **if every record cites it**. Such sources get the audit decision **RESEARCH USE**:

- **Where it may appear:** the research database and the hosted research app.
- **Where it never appears:** the public seed and the repository. Anyone can rebuild the research database from the sources' own upstream with `make fetch-dev-data research-db`.

| Dataset | Citation required | Why RESEARCH USE |
|---|---|---|
| Jambu | Arora, Aryaman, Adam Farris, Samopriya Basu and Suresh Kolichala. 2023. Jambu: A historical linguistic database for South Asian languages. *Proceedings of the 20th SIGMORPHON Workshop*, 68–77. ACL. doi:10.18653/v1/2023.sigmorphon-1.8 | No repository licence; aggregates works with differing terms |
| CDIAL, through Jambu | Turner, Ralph Lilley. 1962–1966. *A comparative dictionary of the Indo-Aryan languages*. London: Oxford University Press | In copyright |
| DEDR, through Jambu | Burrow, Thomas and Murray Barnson Emeneau. 1984. *A Dravidian Etymological Dictionary*. 2nd edn. Oxford: Clarendon Press | In copyright |
| Wiktionary (wiktextract) | Wiktionary contributors, via wiktextract (Ylonen 2022) and kaikki.org | Provisional, until the extract's licence terms are verified |

Jambu cites the work behind each form and edge: CDIAL, DEDR and about 570 more, listed in its `sources.bib`. That citation is kept on every lexeme (`source_id`) and on every relationship's evidence, with the page or entry locator. `GET /api/v1/citations` lists all of them with record counts.

**Enforcement.**
- `validate --research` fails on any BLOCKED data, and on any research-use record without a cited source.
- `validate --public-seed` fails on anything not APPROVED or APPROVED WITH CONDITIONS.
- The seed builder exports only those two decisions.
- In the app, research-use records carry a "Research use, not redistributed" note with the citation. Explore has an *Open data only* switch.

**Jambu imported in full.** `import-jambu --all-languages` keeps every form, not only those of our 25 languages and their ancestors, so etymology chains through other languages stay whole. Those other languages are created disabled and become searchable when added to `data/config/languages.csv`.

| | Our 25 languages and ancestors | Full |
|---|---:|---:|
| Words | 347,721 | 991,379 |
| Relationships | 220,972 | 492,312 |
| Evidence rows | | 555,605 |

## 5. Shortlist datasets not yet audited

The other 22 shortlisted resources have rows with decision BLOCKED and reason "unverified": Lexibank (as a collection), Open English WordNet, Unicode CLDR, IndicLID, Samanantar, IndicCorp v2, Naamapadam, BPCC-Mined, BPCC-H-Wiki, BPCC-H-Daily, IN22-Gen, IN22-Conv, FLORES-200, NLLB-Seed, Tatoeba, Wiktionary, Wikipedia, Open Multilingual Wordnet, Universal Dependencies, Common Voice, FLEURS, and CLDF datasets on Zenodo.

Their licence column records what the shortlist claims, not a verified fact. Each one is promoted only after its release is downloaded and its terms are read. IndicLID's MIT licence for code and models is verified from its README at tag v1.0, but the licence for its benchmark data is not yet confirmed.

## 6. How the audit is enforced

- **Every row is traced.** Each lexeme and relationship records the dataset it was imported from (`dataset`), and each source points to an audit row (`source.dataset_id`). `make validate` fails if anything cannot be traced to an audit record.
- **The public seed is checked.** `make validate-public` additionally fails on any row from a BLOCKED dataset.
- **The public seed is built from approved data only.** `make public-seed` exports only rows whose dataset and source the audit approves, outright or with conditions. It also generates `data/public_seed/ATTRIBUTION.md` from this audit.

## 7. Phase 1 release-gate status

| Gate condition | Status |
|---|---|
| All deployed dataset components have documented reuse permission | Met for the public seed, which contains APPROVED and APPROVED WITH CONDITIONS rows only. Not met for the development database. |
| Native-script and romanised searches pass a multilingual regression suite | Met for the 19 modern languages: `backend/tests/test_multilingual.py` (one native-script query per language, the alias path, and romanisation rules). |
| Exact matches are not confused with compounds or approximate matches | Met: `form_kind`, separate result groups, and regression tests. |
| Every documented historical relationship has traceable evidence | Met: validator checks, plus Wikidata statement IDs. |
| Graph usable for dense results and on small screens | Met in the first version: duplicate merging, filters by type and language group, neighbour capping with "show all", a table synchronised with the selection, and a responsive layout. Needs usability testing. |
| Demo and repository explain sources and limitations | Met: this document, the app's Data & methodology page (sources, licences, limitations, live coverage), and `docs/WRITEUP.md`. |
