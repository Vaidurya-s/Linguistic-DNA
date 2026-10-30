# What to install before running Linguistic DNA (Linux)

Everything below is for a Linux laptop or desktop. Commands are given for Ubuntu/Debian (`apt`) and Fedora (`dnf`); other distributions have the same packages under similar names. Once these are installed, follow [docs/DEPLOYMENT.md § Running it on your own Linux machine](docs/DEPLOYMENT.md#6-running-it-on-your-own-linux-machine).

## Hardware

| | Minimum | Recommended |
|---|---|---|
| Free disk | 30 GB | 40 GB, preferably an SSD |
| Memory (RAM) | 8 GB | 16 GB |
| Network | about 8 GB of downloads, once | |

Where the disk goes:
- about 7.5 GB of downloaded source data in `data/raw/`;
- the research database (Postgres), several GB with every source imported;
- about 0.5 GB for Python and Node dependencies.

The open-data-only setup (step 4b in the guide) needs far less: about 2 GB.

## Software

| Tool | Version | Why |
|---|---|---|
| git | any recent | to clone the repository and the pinned data repositories |
| make | any | every step is a `make` target |
| curl | any | quick checks |
| Python | **3.12 or newer**, with `venv` | backend, importers, data tools |
| Node.js | **20.19+ or 22.12+** (22 LTS recommended) | the web interface (Vite 8 requires it) |
| Docker Engine with the Compose plugin | Docker 24+ | runs PostgreSQL 16 (`docker compose up`) |
| xz-utils | any | unpacks the Digital Pāḷi Dictionary release |
| PostgreSQL client tools (`psql`, `pg_dump`, `pg_restore`) | 16 (optional) | only to inspect the database or make a dump; Docker already contains the server |

**You do not need** CMake, a C/C++ compiler, uv, Conda, Git LFS or a Java runtime. The Python database driver installs as a prebuilt wheel (`psycopg[binary]`), and the one large Git LFS file is downloaded directly by URL with a pinned checksum.

## Installing

### Ubuntu / Debian

```bash
sudo apt update
```

```bash
sudo apt install -y git make curl xz-utils python3 python3-venv python3-pip postgresql-client
```

Check that Python is 3.12 or newer (Ubuntu 24.04 ships 3.12):

```bash
python3 --version
```

Node.js 22 LTS from NodeSource (the version in older Ubuntu releases is too old):

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
```

```bash
sudo apt install -y nodejs
```

Docker Engine and the Compose plugin:

```bash
curl -fsSL https://get.docker.com | sudo sh
```

Let your user run Docker without `sudo`, then log out and back in:

```bash
sudo usermod -aG docker "$USER"
```

### Fedora

```bash
sudo dnf install -y git make curl xz python3 nodejs postgresql
```

```bash
sudo dnf install -y docker docker-compose-plugin
```

```bash
sudo systemctl enable --now docker
```

```bash
sudo usermod -aG docker "$USER"
```

On older Fedora releases where `nodejs` is older than 20.19, install Node 22 with [nvm](https://github.com/nvm-sh/nvm) instead.

## Check everything

Each of these should print a version that meets the table above:

```bash
git --version && make --version | head -1 && python3 --version && node --version && npm --version && docker --version && docker compose version
```

`docker run --rm hello-world` should work without `sudo`; if it does not, log out and back in after the `usermod` step.
