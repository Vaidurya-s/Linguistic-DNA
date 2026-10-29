# Data Pipeline

How to rebuild the development database from versioned upstream inputs. This implements roadmap Weeks 1–2. The source decisions behind it are in [DATASET_AUDIT.md](DATASET_AUDIT.md).

> **The full import is for local development only.** Almost every record comes from sources marked `permission_required` or `unknown` in [`source_manifest.csv`](../data/manifests/source_manifest.csv). Do not deploy or redistribute the resulting database. `make validate-public` reports this as blocking.

## 1. Inputs

| Input | Where | Pinned version | Committed? |
|---|---|---|---|
| Jambu CLDF | `data/raw/jambu` (clone of `moli-mandala/data`) | commit `665850cdd1451391dc939063b5ccc972e646f6f6` | No |
| Jambu `forms.csv` (Git LFS object) | `data/raw/jambu-lfs/forms.csv` | sha256 `b08eb1f0e04777ff8a204b013829d5a3c7cdbde4a54665fd948256ed223bfd28` | No |
| Glottolog CLDF | `data/raw/glottolog-cldf` | tag `v5.3`, commit `072ca0d0410039fb8b779be8fc165bac575d2cda` | No |
| Source manifest | `data/manifests/source_manifest.csv` | in repo | Yes |
| Jambu key → source map | `data/manifests/jambu_source_map.csv` | in repo | Yes |
| Target languages | `data/config/languages.csv` | in repo | Yes |

`data/raw/` is git-ignored. Fetch the inputs with:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/moli-mandala/data data/raw/jambu
git -C data/raw/jambu checkout 665850cdd1451391dc939063b5ccc972e646f6f6
```

```bash
mkdir -p data/raw/jambu-lfs && curl -L -o data/raw/jambu-lfs/forms.csv \
  https://media.githubusercontent.com/media/moli-mandala/data/665850cdd1451391dc939063b5ccc972e646f6f6/cldf/forms.csv
```

```bash
sha256sum data/raw/jambu-lfs/forms.csv
```

```bash
git clone --depth 1 --branch v5.3 https://github.com/glottolog/glottolog-cldf data/raw/glottolog-cldf
```

## 2. Commands

```bash
make setup        # backend venv + frontend node_modules
```

```bash
make db-up        # Postgres 16 in Docker (or point DATABASE_URL at your own server)
```

```bash
make migrate import-jambu import-glottolog validate coverage
```

| Step | What it does |
|---|---|
| `migrate` | Alembic `0001_initial`: the schema, the `pg_trgm` extension, and the seeded relationship-type and script vocabularies. |
| `import-jambu` | Loads the manifest into `source`, then imports Jambu (see §3). It replaces earlier Jambu rows, so it is safe to re-run. |
| `import-glottolog` | Adds the family hierarchy (`language_family`), `family_id`, ISO codes and glottocode aliases. |
| `validate` | Runs the Dataset plan §8 checks and writes `reports/validation.json`. Exits non-zero if an `error` check fails. |
| `validate-public` | Same, but `release` checks also block. This is the gate for any public seed. |
| `coverage` | Per-language table in `reports/coverage.md` and `.json`. |

On the pinned snapshot, the full import takes about 2 minutes. It yields 323,337 lexemes, 208,099 relationships and 248,024 evidence rows. All `error` checks pass, and a second import produces identical IDs.

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
