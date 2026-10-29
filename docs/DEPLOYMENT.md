# Deploying the public demo

The public demo is two pieces:
- **API:** a container built from `backend/Dockerfile`, which contains only the audit-approved public seed;
- **Site:** a static bundle (`frontend/dist`) that calls the API.

Both fit on free tiers. Restricted data (Jambu, CDIAL, DEDR) is never part of the image or the seed.

## 1. Database

Create an empty PostgreSQL 16 database. The loaded seed takes about 335 MB including indexes, so the 500 MB free tiers of [Neon](https://neon.tech) or [Supabase](https://supabase.com) are enough. The `pg_trgm` extension must be available; the migration creates it. Note the connection URL. Both `postgres://…` and `postgresql://…` forms are accepted.

## 2. API

On first start, the container runs migrations, loads the public seed into the empty database (a couple of minutes), then serves on `$PORT`. Later restarts skip the load.

```bash
docker build -f backend/Dockerfile -t lsg-api .
```

```bash
docker run -p 8000:8000 -e DATABASE_URL='postgres://user:pass@host/db' \
  -e CORS_ORIGINS='["https://<you>.github.io"]' lsg-api
```

Hosts that build from a Dockerfile work as is:
- **Render:** Web Service, Docker runtime, Dockerfile path `backend/Dockerfile`, build context `.`.
- **Koyeb.**
- **Fly.io:** `fly launch --dockerfile backend/Dockerfile`.

Set two environment variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the URL from step 1 |
| `CORS_ORIGINS` | a JSON list of the site's origin(s) |

If Docker Hub rate-limits the base image, add `--build-arg BASE_IMAGE=mirror.gcr.io/library/python:3.13-slim`.

Check it works with `GET /api/v1/health`, then `GET /api/v1/search?q=paani`.

## 3. Site

**GitHub Pages (workflow included).**
1. Set the repository variable `API_BASE` to the API URL plus `/api/v1`.
2. Choose *Settings → Pages → Source: GitHub Actions*.
3. Push to `main`, or run the "Deploy site to GitHub Pages" workflow.

**Other static hosts** (Cloudflare Pages, Netlify, Vercel):
- build command: `cd frontend && npm ci && npm run build`;
- output directory: `frontend/dist`;
- environment variable: `VITE_API_BASE=<API URL>/api/v1`.

The app uses hash URLs (`#/explore?q=…`), so no rewrite rules are needed.

## 4. Before going public

- `make validate-public` passes against the deployed database: a fresh seed load passes it by construction.
- `data/public_seed/ATTRIBUTION.md` and the site's *Data & methodology* page credit every dataset. Dakshina-derived spelling pairs are CC BY-SA 4.0.
