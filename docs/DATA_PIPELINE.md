# Data Pipeline

How to rebuild the database from pinned upstream inputs, and how the public seed is produced. Licence decisions live in [DATASET_LICENCE_AUDIT.md](DATASET_LICENCE_AUDIT.md). Jambu's coverage audit is in [DATASET_AUDIT.md](DATASET_AUDIT.md).

There are two databases you can build:

| Build | Contents | May be deployed? |
|---|---|---|
| **Public seed** (`data/public_seed/`) | Only audit-approved datasets, 15 of them: Glottolog, Concepticon, LSI, ASJP, IE-CoR, DravLex, DunniLex, NorthEuraLex, Hale's Nepal wordlists, the Digital Corpus of Sanskrit lexicon, Wikidata Lexemes, Wiktionary, and the Dakshina and Aksharantar spelling pairs. Built before the global imports (`make public-seed` rebuilds it). | Yes, with `ATTRIBUTION.md` |
| **Research database** (`make research-db`, or `make full-db` for every language) | The open datasets plus the research-use ones: Jambu (CDIAL, DEDR and others), Monier-Williams, the Digital Pāḷi Dictionary, Peiros and six more non-commercial Lexibank wordlists, StarLing, High Valyrian, and the Sindhi, Kurdish and Calfa word lists. It also has the open Lexibank wordlists, the Open Multilingual and Mongolian wordnets, WALS and PHOIBLE. | **No.** Local research only. `make validate-public` reports it as blocked. |

## 1. Getting the data after cloning

Raw inputs are never committed; `data/raw/` is git-ignored. They are pinned in [`data/manifests/downloads.json`](../data/manifests/downloads.json): git repositories by tag and commit, and files by SHA-256. To fetch them:

```bash
make fetch-data        # the audit-approved datasets (the "public" group of downloads.json)
```

```bash
make fetch-dev-data    # adds the research-use groups: Jambu, Peiros, DPD, Monier-Williams, StarLing, Kurdish, Calfa, Sindhi
```

Together they are about 8 GB (Wiktionary 2.9 GB, DPD 2.3 GB, Dakshina 1.9 GB, Jambu 2 GB, the Lexibank sets, Aksharantar and Wikidata Lexemes make up most of it). The Sindhi Open Lexicon (84 MB) is fetched with a 10 s pause before the request, as its host asks. The High Valyrian pages are not part of either command: `make fetch-valyrian` (below) is run separately.

The script, `scripts/fetch_data.py`, uses only the Python standard library. It verifies every checksum and skips files that already match.

**If you don't need to rebuild:** the committed public seed (`data/public_seed/*.csv`) is enough to run the app. Load it with `make migrate load-public-seed`.

`downloads.json` has 83 entries: 66 public, 15 research-use and 2 restricted (Jambu). Some examples:

| Input | Group | Pin |
|---|---|---|
| Glottolog CLDF | public | tag `v5.3`, commit `072ca0d` |
| Concepticon | public | tag `v3.4.0`, commit `918bc44` |
| LSI (`lexibank/lsi`) | public | tag `v1.1`, commit `133bcfc` |
| ASJP (`lexibank/asjp`) | public | tag `v21.1`, commit `cf4bf0d` |
| Wikidata Lexemes dump | public | `wikidata-20261028-lexemes.json.bz2`, sha256 `49bc13d3…` |
| Dakshina v1.0 | public | sha256 `83530bec…` |
| Aksharantar, 12 language zips | public | HF revision `e418c1f`; sha256 per file |
| Mongolian Wordnet | public | commit `c747dcf` |
| Jambu CLDF and its LFS `forms.csv` | restricted | commit `665850c`; sha256 `b08eb1f0…` |
| StarLing archives (8) | research | sha256 per archive |
| Kurdish lexicographical resources, Calfa | research | commits `27a85fa`, `71109ce` |
| Sindhi Open Lexicon | research | sha256 `d353a169…` |

The rest (the Lexibank wordlists, the wordnets, WALS, PHOIBLE and so on) are listed in the file itself.

Wikimedia keeps dated dumps for a limited time. If the pinned dump is gone, pick a newer date and update both `downloads.json` and `WIKIDATA_DUMP` in the Makefile.

## 2. Commands

```bash
make setup db-up migrate
```

```bash
make import-open validate coverage benchmark
```

```bash
make public-seed
```

The research database (needs `make fetch-dev-data` first; run `make fetch-valyrian` yourself for High Valyrian):

```bash
make research-db         # import-open, import-research, Glottolog, refresh-languages, rekey-search, validate --research
```

```bash
make FULL=1 research-db  # the same with Wiktionary and Wikidata in every language (or `make full-db`, which also downloads)
```

To rebuild into a second database, so that a hosted site never serves a half-built one, see § 5.

One importer at a time, for example after adding a dataset (each `import-*` target is listed in the Makefile; those for research-use word lists skip themselves while their download is missing):

```bash
make import-sindhi refresh-languages
```

| Step | What it does |
|---|---|
| `migrate` | Alembic migrations 0001–0007: schema, `pg_trgm`, vocabularies, the `dataset_audit` table and `lexeme.form_kind`, transliteration aliases, the research-use decision, the global-language tables (`language_stats`, language profiles) and the empty `layers` schema (§ 6). |
| `import-open` | Every approved dataset, in dependency order: `refresh-languages`, Concepticon, LSI, ASJP, Wikidata Lexemes, transliteration aliases (Dakshina and approved Aksharantar components), Wiktionary, the expert cognate sets (IE-CoR, DravLex, DunniLex, NorthEuraLex, Hale), the Digital Corpus of Sanskrit lexicon, the Open Multilingual Wordnet, the Mongolian Wordnet, WALS and PHOIBLE, then Glottolog classification. Each step first loads the audit and source manifest and registers the configured languages. |
| `import-jambu` | The restricted development import (§3). Prunes unused auto-created sources afterwards. |
| `import-research` | The research-use imports: Jambu, Peiros, DPD, Monier-Williams, the research-use and open Lexibank wordlists, StarLing, High Valyrian, Kurdish, Calfa and Sindhi. |
| `refresh-languages` | Gives every Glottolog language one record, merges the `wkt-`/`jb-`/`wd-`/`gl-` records the sources created into it, refreshes per-language statistics and makes a language searchable from 200 words. Exact duplicate Wiktionary words that merging two codes of one language created are joined. Run it after any import that adds languages. |
| `research-db` | `import-open`, `import-research`, Glottolog, `refresh-languages`, `rekey-search` and `validate --research`. |
| `db-size` | The database size and the words and links per dataset. |
| `validate` | 33 data-quality and provenance checks (16 errors, 9 informational, 4 release and 4 research-use), plus "every row traces to an audit record". Writes `reports/validation.json`. |
| `validate-public` | Same, but rows from BLOCKED datasets also fail. This is the gate for any deployment. |
| `coverage` | Per-language table in `reports/coverage.md`. |
| `benchmark` | Runs `data/benchmark/relationships.csv`; results stay provisional until a person reviews the cases. |
| `public-seed` | Exports audit-approved rows to `data/public_seed/`, with `ATTRIBUTION.md` and `manifest.json` (counts and checksums). |
| `load-public-seed` | Loads the seed into a freshly migrated database, for deployments. |
| `init-layers` | Creates every table of the `layers` schema from `backend/app/layers/*.sql`. Idempotent; the migration runs the same files. |
| `seed-lineage` | Writes the documented source lineage (which dataset is derived from which) into `layers.source_lineage`. |
| `build-sound-key` | Builds `layers.sound_key` for the searchable languages (`--languages a,b` for some). |
| `verify-link <relationship_id>` | Re-reads the dataset's own file under `data/raw` and checks that it says what the stored link says. A check that cannot be made is reported as `unsupported`, never as a pass. |

**Wordlists (LSI, ASJP).**
- Each doculect becomes a `variety` of its language, matched by glottocode.
- Forms link to Concepticon concepts.
- ASJP forms are ASJPcode transcriptions, stored as `phonemic`.
- Neither dataset has cognate judgments for our languages, so no relationships are created.

**Wikidata.**
- Takes the lemma and up to three English glosses per lexeme. Hindi lexemes are filed under Hindustani (Q11051) and are kept when they have a Hindi lemma.
- With `FULL=1`, every lexeme in every language. The language is resolved through the lemma's language code, ISO 639 and Glottolog; items no code resolves become disabled `wd-<qid>` languages.
- "Derived from lexeme" (P5191) becomes the `etymon` type, because Wikidata does not say whether a word was inherited or borrowed. "Combines lexemes" (P5238) becomes `has_component`.
- Every edge cites its statement ID and the statement's own reference, or says it has none.
- Names of non-target languages are looked up once (`--fetch-language-names`) and committed in `data/config/wikidata_languages.csv`.

**Wiktionary (kaikki.org wiktextract).**
- One record per language and headword. Up to three English glosses, merged across parts of speech on the same page. Inflected-form entries are skipped outside the configured languages.
- Etymology templates become typed links: `inh` → `inherited_form`, `bor`/`lbor`/… → `borrowed_from`, `der` → `etymon`, `cal`/`sl` → `calque_or_loan_translation`, `af`/`compound`/… → `has_component`, and `cog` → an undirected `cognate`. `{{etymon}}` follows its `:inh` / `:bor` / `:af` … markers.
- An entry's Descendants list adds the other direction. Each descendant is `inherited_form` from the entry unless Wiktionary marks it borrowed or calqued. A nested descendant descends from the item above it.
- An unmarked `{{desc}}` line only defaults to "inherited"; it is never proof. Other statements win over it:
  - the descendant's own `bor`, `der` or calque template replaces the default link;
  - the parent's marked-borrowed line yields to the descendant's own `{{inh}}`;
  - mutual "inherited" pairs, where each page lists the other as a descendant, are dropped;
  - when the descendant's entry has no template but its etymology sentence starts "Borrowed", "Learned borrowing" or "Semi-learned borrowing" (and does not also say "Inherited"), the link is `borrowed_from`, with the label "{{desc}} + entry etymology text" and the citation "etymology text (borrowing)".
- A `{{der}}` link is only `etymon`. It is retyped `borrowed_from` by the same rule, from the entry's own text: the entry's etymology opens with a borrowing sentence ("Borrowed from French jus"), the words after "from" are a language name followed by the link's target term, and that language fits the target's language code (a variety such as "Late Latin" may add words before its parent's name). One link per entry is retyped, the first whose language fits; none when the entry's own templates already say `bor`, `inh` or calque, or when the text also says "Inherited". The label becomes "{{der}} + entry etymology text". The importer reports `links_retyped_der_by_etymology_text` beside the `{{desc}}` count. Re-import Wiktionary (and rebuild the layers, § 6) to apply the rule to existing data.
- Proto-languages follow the language name ("Proto-X"). The `-pro` code ending is only a fallback when the name is unknown (`oc-pro` is Provençal).
- Languages Wiktionary mentions only by code are named from the ISO 639-3 table (`--iso`; the Makefile passes it).
- Terms a template names but that have no entry are created from the template, in their own language.
- Every link cites the Wiktionary page and, in words, where on it ("etymology (inherited)", "descendants" …). The raw `{{template}}` stays only in `relationship.original_label`.
- Forms are cleaned (see "Shared cleaning" below); punctuation-only forms are skipped.
- Scope:
  - by default, the configured languages, their ancestors and the steppe corridor, plus large languages (English, German, Persian, Finnish …) where an entry has an etymology;
  - with `FULL=1` (`make full-db`), every language in the dump: 6.0 million words in 6,253 language records.
- Rows are staged in temporary tables and merged in SQL, so memory stays flat.

**StarLing (The Tower of Babel; research use).**
- **Format.** The downloads (`data/raw/starling/*.exe`) are self-extracting ZIP archives, read directly with Python's `zipfile`.
  - Each database is a dBase III `.dbf`. Its text fields are 6-byte pointers (offset, length) into a `.var` file.
  - The `.inf` file names the fields and the databases that number fields link to.
- **Encoding.** Text is in StarLing's own encoding: ASCII, CP866 Cyrillic, diacritics and combining accents in the upper range, `0x1D` escapes, Greek and OCS byte pairs, and Big5 for Chinese. It is decoded with A. Brouwer's tables (`app/importers/starling_charset.py`).
- **What becomes what** (`data/config/starling.csv`):
  - An etymology record becomes a reconstructed word in its database's proto-language. Wiktionary codes are used where they exist (`ine-pro`, `gem-pro`, `trk-pro` …), so the same proto-language holds both sources' forms.
  - Each reflex field gives one word per `;`-separated segment, linked to the proto-form as `etymon`.
  - A number field that links a subordinate database to its main one (Germanic to Indo-European, Turkic to Altaic) gives an `etymon` link between the two proto-forms. Links within the Altaic databases note that the family is contested.
  - Vasmer's entries become Russian words, with the stress mark kept in `native_form`, linked to the PIE root that cites them. A headword Vasmer stars (`*чур`) is a hypothetical form and is stored as `reconstructed`, never as attested.
  - A language the import creates (`wkt-<code>`) gets a `wiktionary` alias, which is how `refresh-languages` merges it into the language's Glottolog record. Run `make refresh-languages` after every StarLing import, or the words stay on a separate, non-searchable `wkt-<code>` language.
  - Pokorny's dictionary supplies page references only.
  - No dictionary prose is stored.
- **Languages.** A field name ("Old Greek", "Gothic") or the abbreviation that opens a segment in a mixed field ("Oss." in "Other Iranian") resolves to a language through `data/config/starling_languages.csv`; Glottolog's language names are the fallback.
  - Anything unresolved is skipped and listed in `reports/starling_unmapped.csv`, with counts and any encoding misses.
  - To include more, add the name or abbreviation to that file and run `make import-starling refresh-languages`.

**Valyrian languages (constructed, fictional; research use).**
- **Source.** David J. Peterson's High Valyrian, created for HBO's *Game of Thrones*, and its Low Valyrian descendants (Astapori, Meereenese), from The Languages of David J. Peterson wiki.
- **Download.** `scripts/fetch_valyrian.py` (`make fetch-valyrian`) is run by the user.
  - It saves the dictionary pages, then every term's article page, into `data/raw/valyrian/`.
  - It honours robots.txt: article pages only, never `/index.php` or `/api.php`.
  - It waits between requests (`make fetch-valyrian` uses 6 seconds, because the wiki answers HTTP 429 at 3), retries timeouts and 429/5xx errors, skips a page that keeps failing, and resumes where it stopped. HTTP 403 stops it at once.
  - `make fetch-valyrian VALYRIAN_ARGS="--delay 6 --categories"` also fetches the wiki's `Category:Astapori_Valyrian_lemmas` and `Category:Meereenese_Valyrian_lemmas` (two extra requests) and adds their members to the pages to download. Those dictionary pages are prose lists marked incomplete, so the category lists are the up-to-date source. `/Category:` pages are allowed by robots.txt, but the continuation of a list of more than one page is served through `/index.php`, which is not, so a longer list is used as far as its first page goes and the script says so. The importer needs no change: it reads every saved page, whatever languages its sections are in.
- **Import** (`app/importers/valyrian.py`):
  - The dictionary table gives each term and its definition. The row anchor gives the lower-case spelling, and the page's headword restores the capitals of proper nouns.
  - Each language section of a word page gives its headword, up to three definitions, the Etymology and the Descendants.
  - **Etymology:** a term in the same language is `has_component` when the etymology joins terms with "+", otherwise `derived_form`. A High Valyrian term on a Low Valyrian page is `inherited_form` (`borrowed_from` when the text says borrowed).
  - **Descendants:** each descendant is `inherited_form` from the word.
  - Every link cites the page and its revision (`oldid`).
- **Kept apart.** The languages are `conlang-<code>` records in the family "Valyrian languages (constructed, fictional)". `refresh-languages` never merges them, and no link connects them to a natural language: the importer accepts only the Valyrian language codes, and a page's mention of a word in any other language (Latin, English, another invented language) is skipped and counted as `skipped:<code>` in the import statistics. A language is searchable from 200 words.

**Word lists and wordnets for thinly covered languages** (2026-11-03; details in [DATASET_LICENCE_AUDIT.md](DATASET_LICENCE_AUDIT.md) § 4e to 4g and the candidate list in [CANDIDATE_DATASETS.md](CANDIDATE_DATASETS.md)). None of them states word-to-word relationships, so they add words and meanings, not links.
- **MonWN** (`make import-monwn`; open, in `fetch-data`): the Mongolian Wordnet's TSV in the Open Multilingual Wordnet's layout. A synset such as `06177450-n` is mapped to its `ili:` concept through the synset IDs of the OMW English wordnet, so it must run after `import-omw`. Words are Halh Mongolian.
- **Kurdish** (`make import-kurdish`; research use): the four Ontolex-Lemon Turtle files (Sorani, Kurmanji, Hawrami, Southern Kurdish). A small reader handles the regular subset of Turtle they use; each headword's gloss is the label of its linked translation entry, English preferred.
- **Calfa** (`make import-calfa`; research use): Classical Armenian headwords with their first English definition from the definitions TSVs. The etymology file (Armenian prose, AI-processed) is not read.
- **Sindhi Open Lexicon** (`make import-sindhi`; research use): only entries whose headword is Sindhi, one word per headword. Other-language headword dictionaries in the same CSV are skipped.
- All four write through `app/importers/headwords.py` (or `monwn.py`), replace their own dataset on re-import, and are skipped by `research-db` while their download is missing. The language is found by ISO 639-3 code in the Glottolog-based language records, so run `make refresh-languages` first.

**Shared cleaning.** Every importer cleans the text it stores with `clean_form` (forms), `plain_text` (glosses and definitions) and `is_placeholder_form` from `backend/app/services/normalize.py`. They remove HTML tags, entities, wiki links and templates, zero-width and control characters, edge whitespace and stray line breaks such as `\n>>`, while keeping infix and affix notation. A form with nothing letter-like left (a lone dash or question mark) is a placeholder and is skipped, and counted as `skipped_placeholder_form` in the import statistics. `normalize_form`, which feeds the IDs, is not changed, so IDs stay stable. A new importer uses these helpers.

**Monier-Williams (Cologne Digital Sanskrit Lexicon).** A record whose whole body is a `{{Lbody=N}}` pointer takes the gloss of the record it points to.

**Concepts.** Jambu's concept IDs are Concepticon IDs (all 3,321 match ID and gloss), so all datasets share one concept space.

**Transliteration search (Phase 2).** A query in any of the nine supported scripts is romanised by our own rule-based converter (`backend/app/services/transliterate.py`), following ISO 15919. It tries the readings the script leaves open: whether inherent vowels are pronounced, and whether anusvara is a nasal consonant or a nasalised vowel. The resulting loose keys are matched only within languages that use that script. A romanised query such as "paani" is looked up in the transliteration aliases (Dakshina, plus the approved Aksharantar components) to get native spellings, which then take the same path. Every such match has `match_type = transliteration` and a `via` explanation. Records stored only in a native script (most Wikidata lemmas) are keyed by their romanisation, using per-language vowel rules (Sanskrit keeps inherent vowels, Hindi drops some), so romanised queries reach them. After changing these rules, run `python -m app.cli rekey-search`.

**Form kinds.** Every lexeme is classified as `word`, `stem`, `affix`, `root`, `compound` or `phrase`. Only words can be search matches; the other kinds are returned in their own result groups.

## 3. What the Jambu importer does

- **Scope.** It takes every form in a language listed in `data/config/languages.csv`, then follows `edges.csv` from child to parent to pull in their etyma, proto-forms, donors and components. It keeps edges and comparisons whose two ends are both in scope.
- **Headers.** It checks the real CSV headers, not `Wordlist-metadata.json`. A missing column fails the import.
- **Placeholder forms.** A form whose `Form` is blank or only a placeholder (a proto node without a recorded form) is skipped, with the links that touch it.
- **Normalisation.** The raw `Form` is kept unchanged. `normalized_form` is NFC with control characters removed and whitespace collapsed. Diacritics, case and punctuation are not touched.
- **Reconstruction.**
  - A `*` prefix, or a `Proto-…` language, gives `reconstructed`.
  - `√` roots and affixes give `uncertain`.
  - Other forms of configured languages give `attested`.
  - Anything else is `unknown`.
- **Native script.** `Native` is used when present. Otherwise a `Form` written in a native script is used. Both are marked `native_form_origin = source`. Nothing is transliterated yet.
- **Relationships.** An edge is read as *source --type--> target*, where the source is the child (descendant, borrower, derivative, compound or variant). Jambu's own kind is kept in `original_label`. A `reflex` edge from a PIE or Proto-Indo-Iranian form to an Indo-Aryan CDIAL headword only groups headwords under a proto-form and does not claim inheritance, so it is stored as an `etymon` link from the headword to the proto-form (the label is kept).
- **Evidence.** Each `key[locator]` citation becomes an evidence row whose citation is the reference's plain text (at most 200 characters), not the bare key. When an edge has no citation of its own, the child form's citations are used and the evidence note says so.
- **Sources.** Citation keys map to manifest sources through `jambu_source_map.csv`. Unmapped keys become `jambu-ref:<key>` sources with `reuse_status = unknown` and `parent_source_id = jambu`.
- **Never imported:**
  - `forms.Etymology` and `entry-texts.csv`, which hold verbatim dictionary entries;
  - the free-text `comparisons.Evidence`.

  Gloss markup (`<i>`, `<b>`) is stripped to plain text.
- **Provenance.** Each run writes an `import_batch` row with the upstream commit, input sha256 values, the list of transformations, and counts.
- **Stable IDs.** IDs are deterministic (`lx_`/`rel_` plus a hash of dataset and source record), so a re-import keeps them.

## 4. Tests

```bash
make test   # pytest against TEST_DATABASE_URL (default: lsg_test on localhost), plus vitest
```

```bash
make lint   # ruff check/format, oxlint, tsc
```

The backend tests import `backend/tests/fixtures/jambu_mini` (29 forms; see its README for the licence caveat) and `glottolog_mini`. They check:

- relationship-type mapping and direction;
- that the raw form is kept beside the normalised one;
- reconstruction flags;
- that evidence locators are kept, or that inherited citations are marked;
- that the sentinel planted in `Etymology`/`Evidence` never reaches the database;
- ID stability across a re-import;
- that validation passes in development mode and blocks in public-seed mode.

To regenerate the fixtures from the raw snapshots, run `make fixture`.

## 5. Rebuilding into a second database

Rebuild into a new database next to the live one, check it, and swap the names, so the hosted site never serves a half-built database.

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/lsg_build
make migrate
make FULL=1 research-db
make validate-research benchmark db-size
```

Then stop the API, rename `lsg` to `lsg_old` and `lsg_build` to `lsg`, and start the API again. Keep `lsg_old` until the new one has been checked in the app. Run the tests only against their own `TEST_DATABASE_URL`, never against `lsg` or `lsg_build`.

After the swap, rebuild the layers (§ 6) in the new database: they are computed from the documented links and are out of date after any re-import.

## 6. Derived layers (the `layers` schema)

The documented graph holds only what a source states. Everything computed from it lives in a separate schema, `layers`, and never feeds `public` (the `relationship` and `evidence` tables). Every row carries its method and parameters; inferred rows also carry the ids of the documented relationships they rest on.

| Module (`backend/app/layers/`) | Table(s) | What it holds |
|---|---|---|
| `inferred.py` | `inferred_pair`, view `inferred_chain_step` | Two words that documented ancestry puts under one ancestor, as an ordered chain of documented relationship ids. Steps follow inherited, etymon and derived links; loans, calques and variants are never followed. Capped searches say so. |
| `candidate.py`, `calibrate.py` | `candidate_pair`, `candidate_calibration`, `gloss_token` | Same-meaning words ranked by a sound-aware score, with the gate that made them comparable and a precision calibrated on held-out expert cognate judgements (`calibrate-candidates` fits it). No citation: a suggestion. |
| `keys.py`, `romanise.py` | `word_key`, `word_key_build` | The same word in another script or spelling, by rule (`fold`, `translit`, `translit_rule`). `translit` and `translit_rule` are for borrowing and word identity only. |
| `sound_key.py` | `sound_key`, `sound_key_build` | A sound-class skeleton that puts words that may be related in one bucket, so a search compares only the bucket. |
| `hub.py` | `cognate_component`, `edge_hub_flag`, `cognate_component_build` | Connected components of the documented cognate links, and the edges that sit in an oversized component (more than 5,000 words; homograph chaining). Nothing is deleted. |
| `lineage.py` | `source_lineage` | Which dataset is derived from which, only where a document says so. Datasets that share a lineage do not count as independent corroboration. |
| `verify.py`, `verify_sources.py` | none | Re-checks a stored link against the original source file (`verify-link`). |

Setting up and rebuilding:

```bash
cd backend
python -m app.cli init-layers          # creates the tables (migration 0007 does the same)
python -m app.cli seed-lineage
python -m app.cli build-sound-key
python -m app.layers.hub build         # cognate components; `stats` prints the sizes
python -m app.cli calibrate-candidates # precision per score bin, from the IE-CoR files in data/raw
```

The word keys and the gloss tokens are built by `app.layers.keys.build` and `app.layers.candidate.build_gloss_tokens` (Python calls, no command line yet). The cutoff of `hub build` is 5,000 words. It was chosen on the development half of the multi-family gold: a cutoff of 50 lost 11.7% of the true links there (14.4% on the test half), a cutoff of 5,000 lost 0.6% (1.7%) and still flags the largest components (the biggest holds 287,939 words). `calibrate-candidates` reads `data/raw/iecor/cldf`, scores the gold pairs on the words of the approved datasets (IE-CoR and DunniLex are held out) and fits the calibration on the development concepts only; rerun it after a re-import that changes IE-CoR words or glosses. Inferred and candidate pairs are computed on request and can be stored with `materialise_inferred` and `materialise_candidates`.

- **Rebuild after every re-import.** The layers are computed from the documented links. After an import changes `relationship`, rebuild them, or they describe the old graph.
- **Keep them out of evaluation.** `layers.cognate_component` is built over every dataset. A held-out evaluation must compute components itself, without the held-out source, in a scratch database: `hub.build` (also with `--exclude`) rewrites the stored table.
- **Missing tables are not an error.** If a layer's tables are not built, the API answers `status: unavailable` for that layer only.
- The `oversized_cognate_component` check of `validate` reads `layers.edge_hub_flag` and counts flagged edges; it is 0 when the layer is not built.
