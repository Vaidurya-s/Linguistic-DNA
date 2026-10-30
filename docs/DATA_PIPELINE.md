# Data Pipeline

How to rebuild the database from pinned upstream inputs, and how the public seed is produced. Licence decisions live in [DATASET_LICENCE_AUDIT.md](DATASET_LICENCE_AUDIT.md). Jambu's coverage audit is in [DATASET_AUDIT.md](DATASET_AUDIT.md).

There are two databases you can build:

| Build | Contents | May be deployed? |
|---|---|---|
| **Public seed** (`data/public_seed/`) | Only audit-approved datasets: Glottolog, Concepticon, LSI, ASJP and Wikidata Lexemes. | Yes, with `ATTRIBUTION.md` |
| **Development database** | The above plus Jambu (CDIAL, DEDR and others). | **No.** Local research only. `make validate-public` reports it as blocked. |

## 1. Getting the data after cloning

Raw inputs are never committed; `data/raw/` is git-ignored. They are pinned in [`data/manifests/downloads.json`](../data/manifests/downloads.json): git repositories by tag and commit, and files by SHA-256. To fetch them:

```bash
make fetch-data        # audit-approved datasets (about 3.3 GB: Dakshina 1.9 GB, Aksharantar, Wikidata)
```

```bash
make fetch-dev-data    # adds the restricted Jambu data (about 5 GB in total)
```

The script, `scripts/fetch_data.py`, uses only the Python standard library. It verifies every checksum and skips files that already match.

**If you don't need to rebuild:** the committed public seed (`data/public_seed/*.csv`) is enough to run the app. Load it with `make migrate load-public-seed`.

| Input | Group | Pin |
|---|---|---|
| Glottolog CLDF | public | tag `v5.3`, commit `072ca0d` |
| Concepticon | public | tag `v3.4.0`, commit `918bc44` |
| LSI (`lexibank/lsi`) | public | tag `v1.1`, commit `133bcfc` |
| ASJP (`lexibank/asjp`) | public | tag `v21.1`, commit `cf4bf0d` |
| Wikidata Lexemes dump | public | `wikidata-20261028-lexemes.json.bz2`, sha256 `49bc13d3…` |
| Dakshina v1.0 | public | sha256 `83530bec…` |
| Aksharantar, 12 language zips | public | HF revision `e418c1f`; sha256 per file |
| Jambu CLDF and its LFS `forms.csv` | restricted | commit `665850c`; sha256 `b08eb1f0…` |

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

Development only:

```bash
make import-jambu validate
```

| Step | What it does |
|---|---|
| `migrate` | Alembic migrations 0001–0003: schema, `pg_trgm`, vocabularies, the `dataset_audit` table and `lexeme.form_kind`. |
| `import-open` | Concepticon, LSI, ASJP, Wikidata Lexemes, transliteration aliases (Dakshina and approved Aksharantar components), then Glottolog classification. Each step first loads the audit and source manifest and registers the configured languages. |
| `import-jambu` | The restricted development import (§3). Prunes unused auto-created sources afterwards. |
| `validate` | Data-quality and provenance checks, plus "every row traces to an audit record". Writes `reports/validation.json`. |
| `validate-public` | Same, but rows from BLOCKED datasets also fail. This is the gate for any deployment. |
| `coverage` | Per-language table in `reports/coverage.md`. |
| `benchmark` | Runs `data/benchmark/relationships.csv`; results stay provisional until a person reviews the cases. |
| `public-seed` | Exports audit-approved rows to `data/public_seed/`, with `ATTRIBUTION.md` and `manifest.json` (counts and checksums). |
| `load-public-seed` | Loads the seed into a freshly migrated database, for deployments. |

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
- Terms a template names but that have no entry are created from the template, in their own language.
- Every link cites the Wiktionary page and template.
- Scope:
  - by default, the configured languages, their ancestors and the steppe corridor, plus large languages (English, German, Persian, Finnish …) where an entry has an etymology;
  - with `FULL=1` (`make full-db`), every language in the dump, about 5.4 million entries in 5,000 languages.
- Rows are staged in temporary tables and merged in SQL, so memory stays flat.

**Concepts.** Jambu's concept IDs are Concepticon IDs (all 3,321 match ID and gloss), so all datasets share one concept space.

**Transliteration search (Phase 2).** A query in any of the nine supported scripts is romanised by our own rule-based converter (`backend/app/services/transliterate.py`), following ISO 15919. It tries the readings the script leaves open: whether inherent vowels are pronounced, and whether anusvara is a nasal consonant or a nasalised vowel. The resulting loose keys are matched only within languages that use that script. A romanised query such as "paani" is looked up in the transliteration aliases (Dakshina, plus the approved Aksharantar components) to get native spellings, which then take the same path. Every such match has `match_type = transliteration` and a `via` explanation. Records stored only in a native script (most Wikidata lemmas) are keyed by their romanisation, using per-language vowel rules (Sanskrit keeps inherent vowels, Hindi drops some), so romanised queries reach them. After changing these rules, run `python -m app.cli rekey-search`.

**Form kinds.** Every lexeme is classified as `word`, `stem`, `affix`, `root`, `compound` or `phrase`. Only words can be search matches; the other kinds are returned in their own result groups.

## 3. What the Jambu importer does

- **Scope.** It takes every form in a language listed in `data/config/languages.csv`, then follows `edges.csv` from child to parent to pull in their etyma, proto-forms, donors and components. It keeps edges and comparisons whose two ends are both in scope.
- **Headers.** It checks the real CSV headers, not `Wordlist-metadata.json`. A missing column fails the import.
- **Normalisation.** The raw `Form` is kept unchanged. `normalized_form` is NFC with control characters removed and whitespace collapsed. Diacritics, case and punctuation are not touched.
- **Reconstruction.**
  - A `*` prefix, or a `Proto-…` language, gives `reconstructed`.
  - `√` roots and affixes give `uncertain`.
  - Other forms of configured languages give `attested`.
  - Anything else is `unknown`.
- **Native script.** `Native` is used when present. Otherwise a `Form` written in a native script is used. Both are marked `native_form_origin = source`. Nothing is transliterated yet.
- **Relationships.** An edge is read as *source --type--> target*, where the source is the child (descendant, borrower, derivative, compound or variant). Jambu's own kind is kept in `original_label`.
- **Evidence.** Each `key[locator]` citation becomes an evidence row. When an edge has no citation of its own, the child form's citations are used and the evidence note says so.
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
