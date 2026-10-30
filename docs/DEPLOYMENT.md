# Deploying the public demo

The public demo is two pieces:
- **API:** a container built from `backend/Dockerfile`, which contains only the audit-approved public seed;
- **Site:** a static bundle (`frontend/dist`) that calls the API.

Both fit on free tiers. Research-use data (Jambu, CDIAL, DEDR) is never part of the image or the seed; section 5 covers hosting the research version.

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

## 5. The research version

The research version adds the research-use sources (Jambu, and through it Turner's CDIAL, Burrow & Emeneau's DEDR and the other works Jambu cites). These have no open licence: they are used for academic research with a citation on every record, and this repository never contains or redistributes them. The hosted research database is therefore built on your machine from the sources' own upstream and copied to the host. It is never baked into the image.

1. **Build it locally.**
   ```bash
   make fetch-dev-data
   make migrate research-db
   ```
   `research-db` imports the open datasets, then the research-use ones, then runs `validate --research`. That check fails on any BLOCKED data and on any research-use record without a cited source.
2. **Size the host.** With Jambu in full the database is about 1.7 GB, against about 350 MB for the open seed. That is beyond the 500 MB free tiers of Neon and Supabase. Use a paid tier, or a small VM running PostgreSQL 16 with `pg_trgm`.
3. **Copy it to the host.**
   ```bash
   make research-dump
   pg_restore --no-owner --no-acl --clean --if-exists -d "$HOSTED_DATABASE_URL" data/research_dump/lsg-research.dump
   ```
   `data/research_dump/` is gitignored.
4. **Run the API** from the same Docker image, with `DATABASE_URL` pointing at that database. On start, `ensure-seed` sees a non-empty `lexeme` table and leaves the data alone.
5. **Check citations.** Research-use records show a "Research use, not redistributed" note with the database citation. `GET /api/v1/citations` and the *How to cite* section on the methodology page list every dataset and every cited work. Ticking *Open data only* in Explore hides research-use data.
