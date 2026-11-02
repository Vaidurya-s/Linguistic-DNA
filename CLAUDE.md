# Linguistic DNA: notes for Claude Code

An evidence-first graph of word relationships: FastAPI + PostgreSQL 16 (`pg_trgm`) back end in `backend/`, React + Cytoscape front end in `frontend/`, importers that turn licensed linguistic datasets into typed, cited relationships. Read `README.md` first; the pipeline is in `docs/DATA_PIPELINE.md`. For setting up the full local database, follow `docs/LOCAL_SETUP_WITH_CLAUDE.md`.

## Rules that are never relaxed

- **Never commit data.** `data/raw/`, `data/research_dump/` and `reports/` are git-ignored. Research-use data (Jambu with CDIAL and DEDR, Monier-Williams, the Digital Pāḷi Dictionary, Peiros and the other non-commercial Lexibank sets, the StarLing databases, the Valyrian wiki pages) must never enter the repository, a commit, the public seed (`data/public_seed/`), an issue, a PR or any upload.
- **Every dataset goes through the audit.** `data/manifests/dataset_audit.csv` decides where data may appear: APPROVED / APPROVED WITH CONDITIONS (anywhere, with attribution), RESEARCH USE (local research database only, cited on every record), BLOCKED (nowhere). A new source needs an audit row with its licence evidence before it is imported.
- **Every relationship needs a source.** Each link records its dataset and an evidence row with a citation and, where possible, a page or entry locator. Never create relationships from string similarity; similar spellings are only ever listed as candidates.
- **Respect sites' terms and robots.txt.** No scraping. `starlingdb.org` disallows AI crawlers (`anthropic-ai`), so StarLing archives are downloaded only by the user running `make fetch-dev-data` in their own terminal; do not fetch them yourself. The Valyrian pages (The Languages of David J. Peterson wiki) are downloaded the same way, by the user running `make fetch-valyrian`, a robots-compliant, rate-limited download of article pages. Do not scrape DSAL, ALEW, SLIEKKAS or the OPUS API.
- **Constructed languages stay apart.** High Valyrian and its descendants are fictional languages: they live in their own family (`conlang-*` languages), are never merged by `refresh-languages`, and are never linked to natural languages.
- **Ask before pushing** or before any action that publishes something.

## Commands

| Task | Command |
|---|---|
| Install | `make setup` (backend venv, npm install) |
| Database | `make db-up` (Docker Postgres 16), `make migrate` |
| Downloads | `make fetch-data` (open), `make fetch-dev-data` (everything; user runs it), `make fetch-valyrian` (user runs it) |
| Build the research database | `make research-db`; everything in every language: `make FULL=1 research-db` (or `make full-db`, which also downloads) |
| One importer | `make import-<name>` (see the Makefile), then `make refresh-languages` |
| Checks | `make validate-research`, `make benchmark`, `make db-size` |
| Run the app | `make serve-api` and `make serve-web` (http://localhost:5173) |
| Tests and lint | `make test`, `make lint` (ruff, pytest against Postgres; oxlint, tsc, vitest) |
| Coverage chart for the README | `python3 scripts/coverage_chart.py data/config/languages.csv docs/media/coverage-by-language.svg` |

## Things learned the hard way

- After any import that adds languages, run `make refresh-languages`: it maps every source's languages to one record per language (Glottolog), refreshes per-language statistics and decides which languages are searchable (at least 200 words). It also runs ANALYZE; after very large imports also run `VACUUM ANALYZE` on `lexeme`, `relationship` and `evidence`, or searches get slow.
- Historical stages (Old, Middle, Proto, Prakrit) are never merged into modern languages; ambiguous glottocodes are never merged.
- Importers replace their own dataset (delete, then insert); IDs are deterministic, so re-imports keep them.
- Long imports: run them in the background with output to a log file, and check the log, rather than blocking a session. Kill a stuck process by its PID, never with a `pkill -f` pattern that can match your own shell.
- Disk: the full build needs about 60 GB at its peak. Check `df -h` and `docker system df` before large imports.
- StarLing: unmatched field names and abbreviations are listed in `reports/starling_unmapped.csv`; extend `data/config/starling_languages.csv` (name or abbreviation -> Wiktionary language code) and re-run `make import-starling refresh-languages`. The file uses CRLF line endings; append rows with CRLF so the diff stays small. Always run `refresh-languages` after `import-starling`: it merges the `wkt-<code>` languages the import creates into the Glottolog ones. Vasmer headwords starred in the source are stored as reconstructed.
- `make test` needs `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/lsg_test` exported with the Docker database (the built-in default has no password). The tests wipe that database's `public` schema, so never point them at `lsg`.

## Style

Code reads like the surrounding code: small, typed Python with ruff formatting (line length 100); tests use the `db` fixture and synthetic fixtures under `backend/tests/fixtures/`. Docs are plain, short sentences.
