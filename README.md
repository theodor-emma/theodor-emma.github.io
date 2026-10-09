# theodor-emma.github.io

Emma & Theodor's wedding site: a save-the-date page in three languages, an RSVP
form guests open with a personal code, and a small admin dashboard that creates
invitations and prints them.

| Folder | What it is |
| --- | --- |
| `docs/` | The site itself. GitHub Pages serves this folder as-is — no build step. |
| `docs/rsvp/` | The RSVP form, plus `admin.html` (dashboard) and `invite-pdf.js` (prints invitations). |
| `backend/` | FastAPI + MongoDB. Stores invitations and replies. Deployed at `api-rsvp.theodor-emma.fr`. |
| `email/` | Save-the-date blocks to paste into an email, one per language. |
| `pdf/` | Printable A5 save-the-date cards, one per language, with their print sources. |

The site is static and the backend is a separate service, so you can work on
either one alone. Only the RSVP form and the admin page need the backend.

## Running the site

```bash
cd docs
python3 -m http.server 8002
```

Then open <http://localhost:8002/>. The language pages are `/fr.html` and
`/ro.html` (`/fr` and `/ro` redirect to them), and the RSVP form is at
`/rsvp/`.

Serve it over http rather than opening the files directly: `file://` breaks the
relative paths and the API calls.

## Running the backend

### 1. MongoDB

```bash
podman run -d \
  --name mongodb \
  --env GLIBC_TUNABLES=glibc.pthread.rseq=1 \
  -p 27017:27017 --replace \
  mongo:latest
```

Two details in there:

* `GLIBC_TUNABLES=glibc.pthread.rseq=1` works around a crash of the official
  image on recent kernels. Drop it if yours starts without it.
* `--replace` is a Podman flag; it recreates the container if one of that name
  already exists. On Docker proper it is not a flag — run `docker rm -f mongodb`
  first instead.

It must listen on **27017**, which is what `MONGODB_URI` points at below. The
backend creates the database and its collection on first write, so there is
nothing to set up inside Mongo. Check it is up with:

```bash
podman exec mongodb mongosh --quiet --eval 'db.runCommand({ ping: 1 })'
```

Nothing is mounted, so recreating the container starts from an empty database
and the invitations you seeded are gone. Add `-v mongo-data:/data/db` if you
would rather keep them between runs.

### 2. Configuration

```bash
cd backend
cp .env.sample .env
```

`.env` is read at startup and is not committed:

| Variable | Meaning |
| --- | --- |
| `MONGODB_URI` | `mongodb://localhost:27017` for the container above. |
| `MONGODB_DB` | Database name, `wedding`. |
| `CORS_ORIGINS` | Comma-separated origins, or `*` locally. |
| `ADMIN_SECRET` | The password for the admin dashboard. **The backend refuses to start if it is empty**, so put something in it. |

### 3. Start it

```bash
./run.sh --reload      # http://127.0.0.1:8000, restarts on file changes
```

It starts whether or not Mongo is up — `pymongo` connects lazily — so if you
forgot the container, the server runs and every request answers
`503 {"detail": "Database unavailable"}`.

It must be on **port 8000**: `docs/rsvp/api-base.js` picks the API from the
hostname, and for `localhost` it points at `http://localhost:8000` with no way
to override it. (`--public` binds `0.0.0.0` instead, for testing from a phone
on the same network — the same file maps a private LAN IP to port 8000 on that
host.)

Interactive API docs come with FastAPI, at <http://127.0.0.1:8000/docs>.

### 4. Some invitations to play with

```bash
uv run seed_example.py
```

This inserts one of each kind of invitation — a single guest, a couple, a
plus-one and a family — and prints the code for each. Open
`http://localhost:8002/rsvp/?invite=<CODE>` to answer as that guest, or use the
dashboard at `http://localhost:8002/rsvp/admin.html` with the `ADMIN_SECRET`
from `.env` to add your own.

In the dashboard, set **Public RSVP address** to
`http://localhost:8002/rsvp/` while testing, otherwise the links and QR codes it
generates point at the live site.

## Tests

```bash
cd backend
uv run pytest
```

The suite replaces MongoDB with `mongomock`, so **it does not need a database
running** — it exercises the real routes and models against an in-memory stand-in.
The same command runs in CI on every push that touches `backend/`
(`.github/workflows/backend-tests.yml`).

## Deploying

* **Site** — push to `main`. GitHub Pages serves `docs/` directly.
* **Backend** — `backend/refresh_backend.sh` pulls on the server and restarts
  the systemd unit. It does not run the tests first, so check CI is green.

If you are deploying a version that predates the guest-list format, run
`uv run migrate_invites.py` on the server (dry run) and then with `--apply`. The
API reads both shapes, so this is only tidying.
