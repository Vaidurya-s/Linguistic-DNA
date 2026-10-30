# Deploying the public demo

The public demo is two pieces:
- **API:** a container built from `backend/Dockerfile`, which contains only the audit-approved public seed;
- **Site:** a static bundle (`frontend/dist`) that calls the API.

Research-use data (Jambu, CDIAL, DEDR and the other non-commercial or unlicensed sources) is never part of the image or the seed; section 5 covers hosting the research version. **To run everything on your own Linux machine instead, see section 6** and [REQUIREMENTS.md](../REQUIREMENTS.md).

## 1. Database

Create an empty PostgreSQL 16 database. The loaded seed takes about 680 MB including indexes (521k words, 222k links, 947k spelling pairs), which is more than the 500 MB free tiers of [Neon](https://neon.tech) or [Supabase](https://supabase.com): use their smallest paid tier, or a small VM running PostgreSQL 16. The `pg_trgm` extension must be available; the migration creates it. Note the connection URL. Both `postgres://…` and `postgresql://…` forms are accepted.

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
2. **Size the host.** With every research source imported the database is about 2.1 GB (1.81M words, 997k links), against about 680 MB for the open seed. That is beyond the 500 MB free tiers of Neon and Supabase. Use a paid tier, or a small VM running PostgreSQL 16 with `pg_trgm`.
3. **Copy it to the host.**
   ```bash
   make research-dump
   pg_restore --no-owner --no-acl --clean --if-exists -d "$HOSTED_DATABASE_URL" data/research_dump/lsg-research.dump
   ```
   `data/research_dump/` is gitignored.
4. **Run the API** from the same Docker image, with `DATABASE_URL` pointing at that database. On start, `ensure-seed` sees a non-empty `lexeme` table and leaves the data alone.
5. **Check citations.** Research-use records show a "Research use, not redistributed" note with the database citation. `GET /api/v1/citations` and the *How to cite* section on the methodology page list every dataset and every cited work. Ticking *Open data only* in Explore hides research-use data.

## 6. Running it on your own Linux machine

This is the recommended setup for research. It is free, it has no size limits, and research-use data stays on your machine. Install the prerequisites in [REQUIREMENTS.md](../REQUIREMENTS.md) first. Run every command from the repository folder.

### Get the code and configuration

```bash
git clone https://github.com/Vaidurya-s/Linguistic-DNA.git
```

```bash
cd Linguistic-DNA
```

The Docker database uses the password `postgres`; `.env` tells the app so:

```bash
cp .env.example .env
```

### Start the database and install dependencies

```bash
make db-up
```

```bash
make setup
```

```bash
make migrate
```

`db-up` starts PostgreSQL 16 in Docker; its data persists in a Docker volume across restarts. `setup` creates `backend/.venv` and installs the frontend packages.

### Load data: open data only (4a), the research database (4b) or everything (4c)

**4a. Open data only.** This takes a few minutes and needs about 2 GB. It loads the public seed committed in `data/public_seed`:

```bash
make load-public-seed
```

**4b. The full research database.** This takes 1.5–3 hours and needs about 30 GB. Everything is downloaded from its own upstream, pinned by commit or checksum: about 8 GB, and finished downloads are skipped on a re-run.

```bash
make fetch-data fetch-dev-data
```

Build the database, which ends with `validate --research`:

```bash
make research-db
```

**4c. Everything, in every language (recommended with 100 GB free).** This is 4b plus the whole Wiktionary dump and all of Wikidata Lexemes in every language (about 5,000 languages), with Wiktionary's descendant lists. That adds roughly 5–8 million words and 8–12 million cited links, including the English, European and global etymologies that 4b leaves out. It takes about 4–8 hours and needs about 60 GB at its peak; 16 GB of RAM is recommended. One command does the downloads, the imports, the checks and a size report:

```bash
make full-db
```

`make FULL=1 import-wiktionary` (or `import-wikidata`) re-runs just one of the all-language imports, for example after downloading a newer dump; follow it with `make refresh-languages`. `make db-size` prints the database size and the words and links per dataset at any time.

A `fetch-data` line saying *NEWER snapshot* means a rolling source has been updated upstream. The kaikki.org Wiktionary dump and the SIL ISO table both behave this way. The import still works; the pinned checksum and version in `data/manifests/downloads.json` just describe the older file.

### Run it

In one terminal, start the API on `127.0.0.1:8000`:

```bash
make serve-api
```

In a second terminal, build the site and serve it on `http://localhost:5173`. It forwards `/api` to the API.

```bash
make serve-web
```

Open <http://localhost:5173>. To stop, press `Ctrl+C` in both terminals. The database keeps running in Docker until you stop it:

```bash
docker compose stop db
```

### Share it temporarily (optional)

To show it to colleagues without hosting anything, open a Cloudflare quick tunnel to the site. It is free, needs no account, and gives a random `https://….trycloudflare.com` address that works only while the command runs. Install `cloudflared` from <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>, then start the site so that it accepts the tunnel's address:

```bash
VITE_ALLOWED_HOSTS=.trycloudflare.com make serve-web
```

In another terminal, open the tunnel:

```bash
cloudflared tunnel --url http://localhost:5173
```

Anyone with that address can then read everything the app shows, including research-use data. Share it only with people the research-use terms allow, and close the tunnel when you are done.

### Updating later

Pull the latest code and apply migrations:

```bash
git pull
```

```bash
make setup migrate
```

Re-run `make research-db` (or `make load-public-seed`) when the data changes. Downloads already on disk are reused.
