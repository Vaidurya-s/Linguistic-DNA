# Local development entry points. See docs/DATA_PIPELINE.md.
PY ?= backend/.venv/bin/python
JAMBU_COMMIT ?= 665850cdd1451391dc939063b5ccc972e646f6f6
JAMBU_CLDF ?= data/raw/jambu/cldf
JAMBU_FORMS ?= data/raw/jambu-lfs/forms.csv
GLOTTOLOG_CLDF ?= data/raw/glottolog-cldf/cldf
WIKIDATA_DUMP ?= data/raw/wikidata/wikidata-20261028-lexemes.json.bz2
# libpq URL of the research database, for pg_dump (the app itself reads DATABASE_URL).
RESEARCH_PG_URL ?= postgresql://postgres@localhost:5432/lsg
WIKTIONARY_DIR ?= data/raw/wiktionary
WIKTIONARY_VERSION ?= "kaikki.org wiktextract of enwiktionary 2026-10-01 (file 2026-10-25)"
# Ancestor languages whose own Wiktionary entries are imported (as disabled reference
# languages) so that etymology chains continue; chosen from what our entries cite.
WIKTIONARY_REFERENCE_CODES ?= inc-pro,iir-pro,ira-pro,ine-pro,dra-pro,dra-sou-pro,inc-mid,omr,inc-ohi,inc-oaw,inc-ogu,inc-mgu,inc-opa,inc-oas,inc-mas,inc-obn,inc-mbn,inc-kam,oty,dra-okn,dra-mkn,dra-ote

.PHONY: setup db-up fetch-data fetch-dev-data migrate import-open import-jambu import-glottolog \
        import-concepticon import-lsi import-asjp import-wikidata import-aliases validate \
        validate-public validate-research import-research research-db research-dump \
        import-wiktionary import-cognates import-peirosst import-dcs import-dpd import-cdsl-mw \
        refresh-languages import-lexibank import-profiles \
        coverage benchmark public-seed load-public-seed fixture test lint

setup:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -e 'backend[dev]'
	cd frontend && npm install

# Downloads pinned inputs into data/raw/ (see data/manifests/downloads.json).
fetch-data:
	python3 scripts/fetch_data.py --group public

# Adds the research-use sources (Jambu with CDIAL, DEDR and the works it cites), fetched
# from their own upstream; never redistributed by this repository.
fetch-dev-data:
	python3 scripts/fetch_data.py --group all

db-up:
	docker compose up -d --wait db

migrate:
	cd backend && .venv/bin/alembic upgrade head

import-jambu:
	cd backend && .venv/bin/python -m app.cli import-jambu --cldf ../$(JAMBU_CLDF) \
		--forms ../$(JAMBU_FORMS) --version $(JAMBU_COMMIT) --all-languages

import-glottolog:
	cd backend && .venv/bin/python -m app.cli import-glottolog --cldf ../$(GLOTTOLOG_CLDF)

# Research-use datasets, cited per record; never in the public seed.
import-research: import-jambu import-peirosst import-dpd import-cdsl-mw import-lexibank

# Every Lexibank dataset in data/manifests/lexibank.tsv (CC BY ones are open, NC ones are
# research use), with all their languages, cognate sets and borrowings.
import-lexibank:
	cd backend && .venv/bin/python -m app.cli import-lexibank

import-cdsl-mw:
	cd backend && .venv/bin/python -m app.cli import-cdsl-mw --file ../data/raw/cdsl/mw.txt \
		--version "csl-orig e4742e1"

import-dpd:
	mkdir -p data/raw/dpd/x
	test -f data/raw/dpd/x/dpd.db || tar -xJf data/raw/dpd/dpd.db.tar.xz -C data/raw/dpd/x
	cd backend && .venv/bin/python -m app.cli import-dpd --db ../data/raw/dpd/x/dpd.db \
		--archive ../data/raw/dpd/dpd.db.tar.xz --version v0.4.20261026

# Expert cognate sets (CLDF, CC BY 4.0). --all-languages keeps every doculect, so cognate
# links to languages we do not configure yet stay in the data (disabled gl-<glottocode>).
import-cognates:
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/iecor/cldf \
		--dataset iecor --version "v1.2.1 (dd1ebc9)" --all-languages
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/dravlex/cldf \
		--dataset dravlex --version "v1.1 (0afb2cd)" --all-languages
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/dunnielex/cldf \
		--dataset dunnielex --version "v1.1 (f6f9150)" --all-languages
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/northeuralex/cldf \
		--dataset northeuralex --version "v4.1 (e9a8119)" --all-languages
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/halenepal/cldf \
		--dataset halenepal --version "v4.0 (ec54471)" --all-languages

# Language profiles: typology (WALS) and sound inventories (PHOIBLE).
import-profiles:
	cd backend && .venv/bin/python -m app.cli import-structure --cldf ../data/raw/wals/cldf --dataset wals
	cd backend && .venv/bin/python -m app.cli import-structure --cldf ../data/raw/phoible/cldf --dataset phoible

import-dcs:
	cd backend && .venv/bin/python -m app.cli import-dcs --dictionary ../data/raw/dcs/dictionary.csv \
		--version "8aeed5a"

# Non-commercial licence: research use only.
import-peirosst:
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/peirosst/cldf \
		--dataset peirosst --version "master (4619b46)" --all-languages

import-wiktionary:
	cd backend && .venv/bin/python -m app.cli import-wiktionary --dir ../$(WIKTIONARY_DIR) \
		--version $(WIKTIONARY_VERSION) --reference-codes $(WIKTIONARY_REFERENCE_CODES)

# The full research database: open data, then research-use data, then checks.
research-db: import-open import-research
	$(MAKE) import-glottolog  # classify the languages the research imports created
	$(MAKE) refresh-languages
	cd backend && .venv/bin/python -m app.cli rekey-search
	cd backend && .venv/bin/python -m app.cli validate --research

# All Glottolog languages; one record per language across sources; statistics; which
# languages are searchable (docs/DATA_PIPELINE.md).
refresh-languages:
	cd backend && .venv/bin/python -m app.cli refresh-languages \
		--glottolog ../$(GLOTTOLOG_CLDF) --iso ../data/raw/iso639/iso-639-3.tab

validate-research:
	cd backend && .venv/bin/python -m app.cli validate --research

# A pg_dump of the research database for loading a hosted instance (see docs/DEPLOYMENT.md).
# data/research_dump/ is gitignored: research-use data is never committed.
research-dump:
	mkdir -p data/research_dump
	pg_dump --no-owner --no-acl --format=custom --file=data/research_dump/lsg-research.dump \
		"$(RESEARCH_PG_URL)"
	@ls -lh data/research_dump/lsg-research.dump

# Every dataset the audit approves, in dependency order.
import-open: import-concepticon import-lsi import-asjp import-wikidata import-aliases \
             import-wiktionary import-cognates import-dcs import-glottolog

import-concepticon:
	cd backend && .venv/bin/python -m app.cli import-concepticon --data ../data/raw/concepticon-data

import-lsi:
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/lsi/cldf \
		--dataset lsi --version "v1.1 (133bcfc)" --all-languages

import-asjp:
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/asjp/cldf \
		--dataset asjp --version "v21.1 (cf4bf0d)" --transcription ASJPcode \
		--all-languages

import-aliases:
	cd backend && .venv/bin/python -m app.cli import-dakshina \
		--tar ../data/raw/dakshina/dakshina_dataset_v1.0.tar
	cd backend && .venv/bin/python -m app.cli import-aksharantar --dir ../data/raw/aksharantar

import-wikidata:
	cd backend && .venv/bin/python -m app.cli import-wikidata --dump ../$(WIKIDATA_DUMP) \
		--version 20261028

validate:
	cd backend && .venv/bin/python -m app.cli validate

validate-public:
	cd backend && .venv/bin/python -m app.cli validate --public-seed

coverage:
	cd backend && .venv/bin/python -m app.cli coverage

benchmark:
	cd backend && .venv/bin/python -m app.cli benchmark

# Writes data/public_seed/ from audit-approved rows only, then checks it in a scratch DB.
public-seed:
	cd backend && .venv/bin/python -m app.cli build-public-seed

load-public-seed:
	cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -m app.cli load-public-seed

fixture:
	python3 scripts/build_fixture.py $(JAMBU_CLDF) $(JAMBU_FORMS) $(GLOTTOLOG_CLDF)

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run lint && npm run typecheck
