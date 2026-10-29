# Local development entry points. See docs/DATA_PIPELINE.md.
PY ?= backend/.venv/bin/python
JAMBU_COMMIT ?= 665850cdd1451391dc939063b5ccc972e646f6f6
JAMBU_CLDF ?= data/raw/jambu/cldf
JAMBU_FORMS ?= data/raw/jambu-lfs/forms.csv
GLOTTOLOG_CLDF ?= data/raw/glottolog-cldf/cldf

.PHONY: setup db-up migrate import-jambu import-glottolog validate validate-public coverage \
        fixture test lint

setup:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -e 'backend[dev]'
	cd frontend && npm install

db-up:
	docker compose up -d --wait db

migrate:
	cd backend && .venv/bin/alembic upgrade head

import-jambu:
	cd backend && .venv/bin/python -m app.cli import-jambu --cldf ../$(JAMBU_CLDF) \
		--forms ../$(JAMBU_FORMS) --version $(JAMBU_COMMIT)

import-glottolog:
	cd backend && .venv/bin/python -m app.cli import-glottolog --cldf ../$(GLOTTOLOG_CLDF)

validate:
	cd backend && .venv/bin/python -m app.cli validate

validate-public:
	cd backend && .venv/bin/python -m app.cli validate --public-seed

coverage:
	cd backend && .venv/bin/python -m app.cli coverage

fixture:
	python3 scripts/build_fixture.py $(JAMBU_CLDF) $(JAMBU_FORMS) $(GLOTTOLOG_CLDF)

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run lint && npm run typecheck
