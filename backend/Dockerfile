# API image for a public deployment. It contains only the public seed, never data/raw.
# Build from the repository root:  docker build -f backend/Dockerfile -t lsg-api .
# BASE_IMAGE lets you use a registry mirror, e.g. public.ecr.aws/docker/library/python:3.13-slim
ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY backend/pyproject.toml backend/
RUN mkdir -p backend/app && pip install --no-cache-dir ./backend && pip uninstall -y lsg-backend

COPY backend/ backend/
COPY data/public_seed/ data/public_seed/
COPY data/manifests/ data/manifests/
COPY data/config/ data/config/
RUN pip install --no-cache-dir --no-deps ./backend

WORKDIR /srv/backend
EXPOSE 8000
# Migrate, load the public seed on first start, then serve. PORT is set by most hosts.
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli ensure-seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
