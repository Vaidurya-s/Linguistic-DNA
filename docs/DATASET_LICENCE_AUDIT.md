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
| StarLing etymological databases | Starostin, Sergei A., George S. Starostin et al. *The Tower of Babel: An Etymological Database Project*. https://starlingdb.org/, plus each database's own compilers and source book (§ 4c) | No licence stated; compiled from in-copyright dictionaries |

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

## 4a. Datasets added in the research expansion (2026-10-30)

Every source below was downloaded, its licence was read from the artefact itself, and it was audited with the citation it asks for. The exact citation text is in `data/manifests/dataset_audit.csv`, served at `/api/v1/citations`. "Links" are documented relationships, each with an evidence row.

| Dataset | Pinned version | Licence | Decision | Words | Links |
|---|---|---|---|---:|---:|
| Jambu, in full (CDIAL, DEDR and about 570 cited works) | commit 665850c | none | RESEARCH USE | 991,379 | 492,312 |
| Wiktionary (wiktextract, kaikki.org) | enwiktionary 2026-10-01, extracted 2026-10-25 | CC BY-SA 4.0 and GFDL | APPROVED WITH CONDITIONS | 202,129 | 158,952 |
| Monier-Williams 1899 (Cologne CDSL) | csl-orig e4742e1 | CC BY-NC-SA 3.0, stricter of two stated | RESEARCH USE | 194,083 | 192,637 |
| Digital Corpus of Sanskrit lexicon | 8aeed5a | CC BY 4.0 | APPROVED WITH CONDITIONS | 180,281 | 0 |
| Digital Pāḷi Dictionary | v0.4.20261026 | CC BY-NC-SA 4.0 | RESEARCH USE | 94,782 | 87,873 |
| IE-CoR | v1.2.1 | CC BY 4.0 | APPROVED WITH CONDITIONS | 25,731 | 46,781 cognate |
| Peiros, Sino-Tibetan wordlists (Bodo) | 4619b46 | CC BY-NC 4.0 | RESEARCH USE | 11,041 | 2,360 cognate |
| NorthEuraLex | v4.1 | CC BY 4.0 | APPROVED WITH CONDITIONS | 6,600 | 0 |
| IELex (Dunn) | v1.1 | CC BY 4.0 | APPROVED WITH CONDITIONS | 4,393 | 2,923 cognate |
| DravLex | v1.1 | CC BY 4.0 | APPROVED WITH CONDITIONS | 2,127 | 3,525 cognate |
| Hale's Nepal wordlists | v4.0 | CC BY 4.0 | APPROVED WITH CONDITIONS | 1,227 | 0 |

Alongside the existing Wikidata, LSI and ASJP imports, the research database holds **1,812,733 words, 996,776 documented relationships and 1,060,069 evidence rows** (about 2.1 GB).

**How each source is mapped.**
- Wiktionary etymology templates become typed links: `inh` → inherited, `bor`/`lbor` → borrowed, `der` → "from", calques, `af`/`compound` → component, and `cog` → cognate (undirected). Etymology-only Prakrit and Sanskrit varieties merge into their language, with the variety kept in the label.
- Cognate tables (IE-CoR, IELex, DravLex, Peiros) give undirected `cognate` links between members of a set. A link is kept only when at least one member is in a configured language.
- DPD's Sanskrit equivalents are `related_form` links, because DPD does not say whether a word was inherited. Its `derived_from` links become derived, and its compound constructions become components.
- Monier-Williams compounds marked in `k2` (`agni—hotra`) link to their parts.

**Examined but not used.**
- **DSAL dictionaries (Platts, Tamil Lexicon, Kittel and others):** no bulk download. The terms are CC BY-NC-ND or all rights reserved, and `robots.txt` disallows automated agents. Their entries reach the project only where Jambu cites them.
- **IndoWordNet:** no working bulk download. The Hindi licence is GPL/FDL; licences for the other languages are not stated.
- **CogNet v2 (CC BY-NC-SA):** its cognates are computed automatically and include loans. It can return later as a *candidate* layer once the graph draws candidates distinctly.

## 4b. The global source list (50 sources, 2026-10-30)

Each source below was checked against its own licence, terms and robots.txt. Rows marked *not imported* are listed in the audit with their reason, so the decision can be revisited if access or terms change. Verified versions and citations are in `dataset_audit.csv`, `downloads.json` and `lexibank.tsv`.

**Global and cross-linguistic**

| # | Source | Outcome |
|---|---|---|
| 1 | PanLex | **Not imported.** No official snapshot is reachable. PanLex's licence is CC BY-NC-SA 4.0, while third-party mirrors say CC0. Revisit if PanLex confirms terms. |
| 2, 3 | Wiktionary dumps, kaikki.org | **Imported** (Indian languages and their ancestors). A global import is sized at 3.0M entries with etymology across 2,939 languages. It runs in capped form within the disk budget. |
| 4 | Open Multilingual Wordnet 2.0 | **Imported.** 32 wordnets, every one licensed for redistribution. Senses are linked through interlingual (ILI) concepts. |
| 5 | Global WordNet Association | A directory, not a dataset. Its open wordnets are reached through OMW. |
| 6 | Concepticon | **Imported** (v3.4.0). |
| 7, 8 | Lexibank, CLDF datasets | **Imported.** 130 datasets plus the earlier ones: 124 CC BY, and 6 non-commercial treated as RESEARCH USE. All languages, cognate sets and borrowings are included. |
| 9 | Glottolog | **Imported** in full: 8,594 languages and 4,853 families. Every source's languages map to one record per glottocode. |
| 10 | WALS | **Imported** as language profiles: 73k values for 2,433 languages. |
| 11 | PHOIBLE | **Imported** as language profiles: 79k segment entries for 2,048 languages. |
| 12 | ASJP | **Imported**, all 11,115 doculects. |
| 13 | CLICS⁴ | Audited (CC BY 4.0). Its forms duplicate Lexibank. Colexifications are planned as a concept layer. |
| 14, 15 | WOLD / Loanword Typology | **Imported** through Lexibank: 21,624 directed borrowings. |

**European and Indo-European**

| # | Source | Outcome |
|---|---|---|
| 16 | IELex | **Imported.** |
| 17 | IE-CoR | **Imported.** |
| 18 | NorthEuraLex | **Imported**, all 107 languages. |
| 19 | Indo-European Etymological Dictionaries Online (Brill) | **Not imported.** Subscription product with no bulk access. |
| 20 | Comparative Linguistic Databank (Goethe University) | **Not imported.** Status and access are unknown. |
| 21 | ALEW (Old Lithuanian etymological dictionary) | **Not imported** for now. v1.1 is CC BY-NC-SA 3.0 DE, but its repository's robots.txt disallows automated agents; a person can download it. |
| 22 | SLIEKKAS | **Not imported.** No public bulk download, and its CLARIN mirror disallows automated agents. |
| 23 | CorDon | Audited. Bulk download exists, CC BY-NC 3.0 DE, which would make it RESEARCH USE. It is a corpus of one author (about 24k words). |
| 24, 49 | TITUS (old and 2.0) | **Not imported.** Scholarly non-commercial use only, partly restricted to members, no bulk download. |
| 25 | VATEC | **Not imported.** All rights reserved. |
| 26 | Rustaveli Digital Corpus | **Not imported.** Not found as a separate resource. |
| 27 | ECLING | **Not imported.** Credentials required. |
| 28 | Universal Dependencies 2.18 | Audited. Licences vary per treebank (61 non-commercial). Lemmas from open treebanks are planned. |
| 29, 30 | Scaife, Perseus | Audited (CC BY-SA 4.0). The LSJ and Lewis & Short lexica are planned. |
| 31 | Logeion | **Not imported.** An aggregator with no bulk download; its parts have mixed rights, including no-derivatives. |
| 32 | Estonian WordNet | **Not imported.** Download requires contacting the maintainer, and listings conflict between CC BY-SA and BY-NC. |
| 33 | FinnWordNet | **Imported** through OMW (CC BY 3.0). |
| 34 | plWordNet | The OMW subset is **imported**. Version 4.5 is an open SQL dump that needs conversion; version 5.0 requires a request. |
| 35 | Tilde MODEL | Audited (CC BY). Parallel text only; no word-level relationships are derived. |

**Southeast Asian and Austronesian**

| # | Source | Outcome |
|---|---|---|
| 36, 37 | SEAlang Library, Mon-Khmer project | **Not imported.** The host is unreachable and no bulk download was found. |
| 38 | STEDT | **Not imported.** No public release; the author releases data on request. Sino-Tibetan cognates come through Lexibank (sagartst, Peiros). |
| 39 | ABVD | **Imported**: 1,982 languages, cognate sets drawn as stars. |
| 40 | Austronesian Comparative Dictionary | **Imported** through Lexibank: cognate sets and borrowings. |
| 41 | SEABOR | **Imported** through Lexibank (cognates). |
| 42 | PARADISEC | **Not imported.** Metadata only, and its user licence forbids redistribution. |
| 43 | Tibetan and Himalayan Library / Digital Himalaya | **Not imported.** Non-commercial, no derivatives, online only. |
| 44 | Leipzig Corpora Collection | Audited. Downloads exist, but their licence page is behind a bot challenge, so the licence is unverified. |
| 45 | OPUS | Audited. Its dictionaries come from automatic word alignment, i.e. computed, so they are not imported as relationships. Its API disallows automated agents. |

**Multilingual and historical**

| # | Source | Outcome |
|---|---|---|
| 46 | Tatoeba | Audited (CC BY 2.0 FR). Sentence pairs give no word-level relationships without computed alignment. |
| 47, 48 | NLLB-Seed, FLORES-200 | Audited (CC BY-SA 4.0). Evaluation sets whose terms forbid crawler-reachable re-hosting; not imported. |
| 50 | Historica Corpus | **Not identified.** The name matches several corpora; a link would settle it. |

## 4c. StarLing (The Tower of Babel)

**Decision: RESEARCH USE.** These are the downloadable StarLing databases of Sergei Starostin's *Tower of Babel* project, archives dated 18 November 2005.

**Evidence.**
- Neither the download page nor the archives' `.inf` files state a licence.
- The databases are compiled from dictionaries that are still in copyright: Walde–Pokorny and Pokorny's *IEW* (1959), Vasmer's *Russisches etymologisches Wörterbuch* in Trubachev's Russian edition (1964–1973), Starostin, Dybo & Mudrak's *Etymological Dictionary of the Altaic Languages* (Brill, 2003), Burrow & Emeneau's *DED*, Nikolayev & Starostin's *North Caucasian Etymological Dictionary* (1994), Starostin & Peiros' Sino-Tibetan dictionary, and Mudrak's Chukchee-Kamchatkan dictionary (2000).

**Access.**
- `starlingdb.org/robots.txt` disallows AI crawlers (`anthropic-ai`, `GPTBot`, `CCBot`, `Google-Extended`).
- So the archives are never fetched by an automated agent working on this repository. They are downloaded only by the user's own `make fetch-dev-data`, as a person would from the site's Download page.
- Their checksums are recorded on that first download: the manifest entries are `unpinned`.
- The online-only databases (Uralic, Nostratic, Afroasiatic, Eskimo, long-range) have no download and are not scraped.

**What is stored.**
- Proto-forms, reflex forms, glosses of up to 120 characters, links between etymologies, and page references (Walde–Pokorny, Pokorny *IEW* pages, Vasmer volume and page).
- No dictionary prose: no Vasmer or Trubachev articles, no Pokorny material, no comments.
- Every record and link cites its own database and compilers, for example "StarLing, Indo-European etymology (S. L. Nikolayev, on the basis of Walde and Pokorny …), no. 1", with page locators.

**Caveat.** The Altaic databases present Turkic, Mongolic, Tungusic, Korean and Japanese as one family. That is a contested hypothesis, so links between those databases carry a note saying so.

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
