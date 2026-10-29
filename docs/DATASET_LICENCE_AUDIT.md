# Dataset Acquisition and Licence Audit

This is the authority on what may enter the public application. The machine-readable version is [`data/manifests/dataset_audit.csv`](../data/manifests/dataset_audit.csv), with one row per dataset or separately licensed component. The importers, the validator and the public-seed builder all read it.

Audit date: 2026-10-29. Every input is pinned in [`data/manifests/downloads.json`](../data/manifests/downloads.json); fetch them with `make fetch-data`.

## 1. Decision rules

| Decision | Meaning |
|---|---|
| **APPROVED** | Licence verified on the records themselves, and it permits redistribution. |
| **APPROVED WITH CONDITIONS** | As above, but attribution, ShareAlike or a subset filter applies. |
| **BLOCKED** | Unverified, unresolved, or no right to redistribute. The reason is recorded. Blocked data may be used only in a local development database. |

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

The card is inconsistent about the manually collected part: it says CC-BY, and in another sentence waives all rights to "manually collected data". The stricter CC-BY reading is used.

**Neither LSI nor ASJP contains cognate judgments for our languages.** LSI has none at all. ASJP flags 43 forms as loans but names no donor. These datasets therefore add forms and concept-aligned meanings, but no historical links. The importers create no relationships from them; ASJP's loan flag is kept only as a tag.

## 3. Wikidata Lexemes in our languages

_Filled in from the import of dump 20261028; see §6._

## 4. Development-only sources

Jambu, CDIAL and DEDR are BLOCKED for public use. Jambu has no licence of its own, and CDIAL and DEDR are in copyright with DSAL reuse terms unestablished (see [DATASET_AUDIT.md](DATASET_AUDIT.md)). They remain in the local development database, are downloaded only from their own upstream, and never enter the public seed.

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
| Native-script and romanised searches pass a multilingual regression suite | Not yet: Phase 2, which adds the transliteration aliases. |
| Exact matches are not confused with compounds or approximate matches | Met: `form_kind`, separate result groups, and regression tests. |
| Every documented historical relationship has traceable evidence | Met: validator checks, plus Wikidata statement IDs. |
| Graph usable for dense results and on small screens | Partly: Phase 2. |
| Demo and repository explain sources and limitations | Partly: this document; the methodology page is Phase 3. |
