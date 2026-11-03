# Building the full database on your own machine, with Claude Code

This is a runbook for Claude Code running on the Linux machine that will hold the full research database (about 100 GB of free disk). The person running it pastes the prompt in [§ 0](#0-the-prompt-to-paste) into Claude Code, from the repository folder. Claude Code then works through the steps below, stopping where a step says to ask.

The project rules in [`CLAUDE.md`](../CLAUDE.md) apply throughout. In particular, nothing under `data/raw/`, `data/research_dump/` or `reports/`, and no research-use data, is ever committed or uploaded.

## 0. The prompt to paste

First, in a terminal (not through Claude Code):

```bash
git clone https://github.com/Vaidurya-s/Linguistic-DNA.git
```

```bash
cd Linguistic-DNA
```

```bash
claude
```

Then paste:

```text
Set up this repository's full research database on this machine by following
docs/LOCAL_SETUP_WITH_CLAUDE.md step by step, and obey CLAUDE.md throughout.
Check the prerequisites first and tell me exactly what to install if anything is
missing. Do not download from starlingdb.org yourself: when the runbook reaches the
download step, give me the command to run in my own terminal and wait. Run the long
imports in the background with logs, check on them, and fix failures you can fix
within the rules. Do not commit research data, and ask me before any git push.
At the end, give me the report described in the runbook's last section.
```

## 1. Check the machine

Run these and compare with [`REQUIREMENTS.md`](../REQUIREMENTS.md):

```bash
df -h . /var/lib/docker
```

```bash
free -g
```

```bash
git --version && make --version | head -1 && python3 --version && node --version && docker --version && docker compose version
```

- **Disk:** at least 60 GB free where the repository is, and where Docker keeps its volumes (`/var/lib/docker` by default). If Docker's partition is small but another disk is large, stop and tell the user how to move Docker's `data-root` (REQUIREMENTS.md explains it). Do not change system configuration without the user's go-ahead.
- **Versions:** Python at least 3.12; Node 20.19+ or 22.12+; Docker with the Compose plugin; `docker run --rm hello-world` works without `sudo`.
- **RAM:** 16 GB is recommended; with 8 GB it works but slowly.

If anything is missing, list the exact install commands from REQUIREMENTS.md for this distribution, and wait for the user to install it (they need `sudo`).

## 2. Install and start the database

```bash
cp -n .env.example .env
```

```bash
make db-up
```

```bash
make setup
```

```bash
make migrate
```

Check it: `make test` should pass (it uses a separate `lsg_test` database). The tests read only the `TEST_DATABASE_URL` environment variable, whose built-in default has no password, so with the Docker database export it first or every database test errors with `fe_sendauth: no password supplied`:

```bash
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/lsg_test
```

The tests drop and recreate the `public` schema of that database, so never point it at `lsg`.

## 3. Downloads (the user runs this)

Ask the user to run, in their own terminal, from the repository folder:

```bash
make fetch-dev-data
```

It downloads about 8 GB, every file pinned by commit or SHA-256, and skips what is already there, so it can be re-run after an interruption. It includes the StarLing archives from starlingdb.org; that site disallows AI crawlers, which is why the user, not Claude Code, runs this step. It also fetches the Sindhi Open Lexicon (84 MB), with a 10 s pause before the request, as its host asks. The Kurdish, Calfa and Mongolian Wordnet repositories come as git clones.

If the user wants High Valyrian, they also run, in their own terminal (4–7 hours at one request every 6 seconds, because the wiki answers HTTP 429 at 3 seconds; it can run alongside the build, retries transient errors and resumes if stopped):

```bash
make fetch-valyrian
```

When it has finished, run `make import-valyrian` (it is also part of `research-db`, which skips it while nothing is downloaded). Its output gives words per language (`words:hval` should be about 3,160, `words:asta` 444 and `words:meer` 266, with `skipped:<code>` counts for mentions of other languages) and relationship counts (about 3,700).

When the user says it has finished:
- Look at its output (ask the user to paste it if needed). Every line should be `ok`, `downloaded` or `cloned`.
- A `FAILED` line: re-run the command once (network); if it fails again, report the entry and the error.
- `NEWER snapshot` (kaikki.org Wiktionary, the ISO 639-3 table): fine, the upstream file was updated.
- `sha256 mismatch` for a `starling-*` entry (the eight StarLing checksums are already pinned in `data/manifests/downloads.json`): the archive on the server changed. Do not overwrite the pin; report it to the user.

## 4. Build everything

Run in the background with a log (4–8 hours is a safe estimate; the first run of this runbook took about 50 minutes on a desktop with 28 threads, 61 GB of RAM and an NVMe SSD). Keep the log outside the repository, or in a git-ignored place, so it cannot be committed by accident:

```bash
nohup make FULL=1 research-db > build.log 2>&1 &
```

This runs every open import (including the Mongolian Wordnet), every research import (StarLing, High Valyrian when downloaded, and the Kurdish, Calfa and Sindhi word lists), Wiktionary and Wikidata in **every** language, Glottolog classification, `refresh-languages`, `rekey-search` and `validate --research`.

While it runs:
- Check `tail -n 30 build.log`, `df -h` and `docker system df` every 15–30 minutes. Do not start a second build.
- If free disk drops under 10 GB, stop the build (find the PID with `pgrep -af "app.cli"` and kill that PID), tell the user, and wait.
- If a step fails:
  - read the traceback;
  - fix the cause if it is in this repository's code or configuration and within the rules;
  - run `make lint test`;
  - re-run only the failed import (`make import-<name>`, or `make FULL=1 import-wiktionary` / `import-wikidata`);
  - then continue with the remaining steps of `research-db` in order (see the Makefile).
- Report anything you could not fix, with the error.

## 5. Check the result

```bash
make db-size
```

```bash
make validate-research
```

```bash
make benchmark
```

Then reclaim space and refresh the planner statistics:

```bash
docker compose exec db psql -U postgres -d lsg -c "VACUUM ANALYZE lexeme" -c "VACUUM ANALYZE relationship" -c "VACUUM ANALYZE evidence"
```

`validate --research` must pass. Spot-check the thinly covered languages through the API, for example Sindhi (`GET /api/v1/search?q=سنڌي`), a Kurdish dialect, Classical Armenian and Halh Mongolian: each should have its words from `sindhi-lexicon`, `kurdish-lexicography`, `calfa-armenian` or `monwn`. Any check that fails: report it with its count and a few example rows (read-only queries).

## 6. StarLing: mapping

`make import-starling` (part of the build) writes `reports/starling_unmapped.csv`: StarLing field names and segment abbreviations it could not assign to a language, with how often each occurs. The committed `data/config/starling_languages.csv` already maps the frequent ones, so the list should be short; what remains (family-level fields, uncertain dialects, columns that are not languages) was left unmapped on purpose.

1. **Map the frequent entries.** For each one with many occurrences, find the language it names. The StarLing field alias (e.g. "Old Church Slavonic") or abbreviation (e.g. "Lith.") usually says it plainly. Add a row to `data/config/starling_languages.csv` with its Wiktionary language code. Use `*` for a field that mixes several languages.
   - Do not guess: leave anything unclear for the user, and list it in the report. Family-level fields (Tungus-Manchu, Mongolian, Turkic), dialect fields whose language is uncertain, and fields that are not languages at all (Grammar, reference columns) stay unmapped.
   - The file uses CRLF line endings. Append rows with CRLF (for example in binary mode), or the diff shows every line as changed.
2. **Re-import and check.** `import-starling` replaces its own dataset and creates a `wkt-<code>` language for each code it uses; the `refresh-languages` that follows merges those into the Glottolog languages (Russian, Latin, Tulu …). Always run both, in this order, and check afterwards that the StarLing words moved:

   ```bash
   make import-starling refresh-languages validate-research
   ```

   ```bash
   docker compose exec db psql -U postgres -d lsg -c "SELECT language_id, count(*) FROM lexeme WHERE dataset = 'starling' GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
   ```

   Russian should appear as `gl-russ1263` (about 17,000 words), not `wkt-ru`. Afterwards, `cd backend && .venv/bin/python -m app.cli rekey-search` rebuilds the search keys (there is no make target for it); it is cheap and safe to run.
3. **Commit only the config change** (`starling_languages.csv`) on a new branch. Ask the user before pushing.

## 7. Update the README figures (optional; ask first)

If the user wants the README to reflect this machine's database:
- Regenerate the chart with `PGPASSWORD=postgres python3 scripts/coverage_chart.py data/config/languages.csv docs/media/coverage-by-language.svg`. The script calls `psql`, so install the PostgreSQL client first (`sudo apt install -y postgresql-client`); a newer client than the server's version 16 works.
- Update the numbers in README.md's "At a glance" table and in the chart's alt text from `make db-size` and read-only SQL.
- Show the user the diff. Commit on a branch, and push only if they say so.

## 8. Run it

In two terminals (or in the background):

```bash
make serve-api
```

```bash
make serve-web
```

Open <http://localhost:5173/#/explore>. Try these words, and confirm each shows a graph with cited links:
- **Russian:** вдова
- **Hindi:** पानी
- **English:** water
- **A StarLing word:** search a Russian word from Vasmer, and check that a link cites "StarLing" and "Vasmer".

To open it from other devices on the same network, build the site once and let the preview listen on all interfaces, leaving the API on localhost (the site forwards `/api` to it):

```bash
cd frontend && npm run build && npx vite preview --host 0.0.0.0 --port 5173 --strictPort
```

Other devices then use `http://<this machine's LAN address>:5173`. Keep this to a trusted network: the site serves the research-use data. If a device cannot connect, check the firewall (`sudo ufw status`).

To share it temporarily over the internet, see `docs/DEPLOYMENT.md` § 6 (Cloudflare quick tunnel). Only do this if the user asks: research-use data must not be published openly.

## 9. Report to the user

End with a short report:
- **Steps:** which completed, and how long the build took.
- **Database:** `make db-size`: size, words and links per dataset, and searchable languages.
- **Checks:** the `validate --research` and `benchmark` results.
- **Russian:** words and links (`gl-russ1263`), and the StarLing totals (words, links, the databases found).
- **Word lists:** words per dataset for the Sindhi, Kurdish, Calfa and Mongolian imports, and High Valyrian if it was downloaded.
- **StarLing mapping:** what was mapped from `reports/starling_unmapped.csv`, and what is left for the user to decide.
- **Fixes:** any code or config changes, with their branch and commits, unpushed unless the user approved.
- **Problems:** anything that failed and was not fixed, with the error and a suggested next step.
