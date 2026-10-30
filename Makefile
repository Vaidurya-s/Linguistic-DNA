# Local development entry points. See docs/DATA_PIPELINE.md.
PY ?= backend/.venv/bin/python
JAMBU_COMMIT ?= 665850cdd1451391dc939063b5ccc972e646f6f6
JAMBU_CLDF ?= data/raw/jambu/cldf
JAMBU_FORMS ?= data/raw/jambu-lfs/forms.csv
GLOTTOLOG_CLDF ?= data/raw/glottolog-cldf/cldf
WIKIDATA_DUMP ?= data/raw/wikidata/wikidata-20261028-lexemes.json.bz2

.PHONY: setup db-up fetch-data fetch-dev-data migrate import-open import-jambu import-glottolog \
        import-concepticon import-lsi import-asjp import-wikidata import-aliases validate \
        validate-public \
        coverage benchmark public-seed load-public-seed fixture test lint

setup:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -e 'backend[dev]'
	cd frontend && npm install

# Downloads pinned inputs into data/raw/ (see data/manifests/downloads.json).
fetch-data:
	python3 scripts/fetch_data.py --group public

# Adds Jambu (development only; never redistributed).
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

# Every dataset the audit approves, in dependency order.
import-open: import-concepticon import-lsi import-asjp import-wikidata import-aliases \
             import-glottolog

import-concepticon:
	cd backend && .venv/bin/python -m app.cli import-concepticon --data ../data/raw/concepticon-data

import-lsi:
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/lsi/cldf \
		--dataset lsi --version "v1.1 (133bcfc)"

import-asjp:
	cd backend && .venv/bin/python -m app.cli import-wordlist --cldf ../data/raw/asjp/cldf \
		--dataset asjp --version "v21.1 (cf4bf0d)" --transcription ASJPcode

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
