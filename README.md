# 🌱 Ogrodnik AI (Garden Assistant AI)

A self-hosted, password-protected web dashboard for your garden. It collects data from:

*   **Irrigation** — Hunter Hydrawise (cloud REST API),
*   **Mowing** — Dreame robot mower (read through Home Assistant),
*   **Weather** — Open-Meteo forecast for the garden's coordinates (no API key needed),
*   **Manual action log** (fertilizing, planting, pruning, plant protection, manual watering, other) with optional photos,
*   **Garden map** — plant pins placed on a photo or sketch of your garden,
*   **AI analysis (Google Gemini)** — insights and recommendations generated automatically every 24 hours or on demand, plus plant recognition from photos.

Everything is stored in a local SQLite database, so the history outlives the Home Assistant recorder (which keeps only ~10 days by default). The UI is available in Polish (default) and English.

---

## Features

| Area | Description |
| :--- | :--- |
| Dashboard | Watering and mowing counts for the last 14 days, current weather, 7-day precipitation chart from stored snapshots, latest AI insight, recent actions |
| Hunter Hydrawise | Polls the controller status every `POLL_INTERVAL_MINUTES` and builds a local watering history (zone, start, end, duration) — the Hydrawise API itself only returns the upcoming schedule. Read-only |
| Dreame mower | Reads the mower entity's state history from the Home Assistant History API and stores mowing sessions locally. Read-only (no start/stop/dock control) |
| Weather | Open-Meteo current conditions and 3-day forecast; a snapshot is stored every `max(POLL_INTERVAL_MINUTES, 15)` minutes |
| Action log | Form on the dashboard for fertilizing, planting, pruning, plant protection, manual watering and other actions, with product, dose, zone and photo |
| Garden map | Upload a photo or sketch, click a spot, and pin a plant there (name, Latin name, zone, notes, photo) |
| AI plant recognition | Upload a photo; Gemini returns plant suggestions that you can place on the map |
| AI analysis | Gemini summary of the last 14 days of watering, mowing, weather and actions. Generated once at startup and then every 24 h, or on demand with the "Odśwież teraz" (Refresh now) button. Every result is stored; the history is available at `GET /api/insights` |
| Settings in the UI | Garden name and coordinates, API keys, Home Assistant connection, Gemini model and UI language can be changed in the app, with no container restart |
| Login | Single admin account, server-side sessions, rate-limited login form |

---

## Quick Start (Docker Compose)

```bash
git clone https://github.com/RenaCode/Ogrodnik-AI.git
cd Ogrodnik-AI

cp .env.example .env
# Set ADMIN_PASSWORD and SECRET_KEY — see "Required Configuration" below.
# Everything else can stay empty: API keys can be entered later
# in the app under "Ustawienia" (Settings).

docker compose up -d --build
```

Open `http://localhost:8000` and log in with `ADMIN_USERNAME` (default `admin`) and `ADMIN_PASSWORD`.

The compose file starts two containers:

| Service | Port | Purpose |
| :--- | :--- | :--- |
| `ogrodnik-ai` | `8000` | The application (FastAPI/uvicorn), with a Docker `HEALTHCHECK` on `/health` |
| `ogrodnik-db` | `127.0.0.1:8082` | Optional [sqlite-web](https://github.com/coleifer/sqlite-web) database browser — see below |

All data (SQLite database, uploaded photos and map images) lives in the Docker volume `ogrodnik_data`, so it survives container restarts and rebuilds.

If Home Assistant runs on the same machine and its hostname is not resolvable from inside the container, uncomment the `extra_hosts` section in `docker-compose.yml` and set `HA_BASE_URL=http://host.docker.internal:8123`.

> **HTTPS note:** the session cookie is set with the `Secure` flag. Browsers accept it on `http://localhost`, but if you open the app over plain HTTP from another host (e.g. a LAN address), logging in will not stick. Put the app behind an HTTPS reverse proxy for anything other than local use.

Pre-built images are published by CI to `ghcr.io/renacode/ogrodnik-ai` and `ghcr.io/renacode/ogrodnik-db` (tags `latest` and `sha-<commit>`).

---

## Quick Start (Local, without Docker)

Requires Python 3.12 (the version used in the Docker image; `sqlmodel` 0.0.22 does not start on Python 3.14).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set ADMIN_PASSWORD and SECRET_KEY

uvicorn app.main:app --reload
```

Run it from the repository root (templates are loaded from `app/templates`). Open `http://localhost:8000`. Data is written to `./data/`.

---

## Required Configuration

Two environment variables have **no default value** and the application refuses to
start without them. This is deliberate: this repository is public, so any default
baked into the source would be known to everyone — and the login screen is the only
thing guarding the *Settings* tab, which holds your Home Assistant token and API keys.

| Variable | Purpose |
| :--- | :--- |
| `ADMIN_PASSWORD` | Password for the admin panel (username comes from `ADMIN_USERNAME`, default `admin`) |
| `SECRET_KEY` | Key used to sign session identifiers — a **separate** secret, not the password |

Generate a `SECRET_KEY` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set both in `.env` (Docker Compose reads it via `env_file`), or — for the Helm chart —
in the Kubernetes Secret referenced by `secretName` in `charts/ogrodnik/values.yaml`.
If either is missing, startup aborts with a message naming the variable.

Sessions are stored server-side in the SQLite database (only an HMAC of the token is
kept), so logging out really invalidates the session and sessions survive a restart.

---

## Optional Configuration

All variables are listed in [`.env.example`](./.env.example).

| Variable | Default | Editable in the UI | Purpose |
| :--- | :--- | :---: | :--- |
| `ADMIN_USERNAME` | `admin` | | Login name |
| `GARDEN_NAME` | `Mój ogród` | ✓ | Garden name |
| `GARDEN_LAT` / `GARDEN_LON` | `52.2297` / `21.0122` | ✓ | Coordinates for the weather forecast |
| `HYDRAWISE_API_KEY` | — | ✓ | Hunter Hydrawise API key (from your Hydrawise account settings) |
| `HA_BASE_URL` | — | ✓ | Home Assistant URL, e.g. `http://homeassistant.local:8123` |
| `HA_LONG_LIVED_TOKEN` | — | ✓ | Home Assistant long-lived access token |
| `HA_MOWER_ENTITY_ID` | — | ✓ | Entity ID of the mower in Home Assistant |
| `GEMINI_API_KEY` | — | ✓ | Key from [aistudio.google.com](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | ✓ | Gemini model name |
| `POLL_INTERVAL_MINUTES` | `5` | | Hydrawise and Home Assistant polling interval (weather: at least 15 min) |
| `TRUSTED_PROXY_CIDRS` | empty | | Comma-separated proxy networks whose `X-Forwarded-For` header is trusted — see below |

The UI language (Polish / English) is set only in the app, under *Ustawienia* (Settings). It also switches the language of Gemini's answers.

Values saved in the *Settings* tab take precedence over `.env` and take effect immediately. They are stored **unencrypted** in the SQLite database. Leaving a field empty keeps the current value; saved keys and tokens are never shown back in the form.

The dashboard, action log, garden map and weather work without any keys. Hydrawise, Home Assistant/Dreame and Gemini switch on automatically once their settings are filled in.

### Login rate limit and reverse proxies

After 10 failed attempts within 15 minutes for the same (client address, username) pair, the login form returns HTTP 429. Behind a reverse proxy (e.g. Traefik) every request comes from the proxy's address, so unless `TRUSTED_PROXY_CIDRS` is set (for k3s the pod network is `10.42.0.0/16` by default), the limit is effectively **global** — anyone sending wrong passwords can lock the owner out. Set it in any proxied deployment.

---

## Integrations

| Integration | Requires | Status |
| :--- | :--- | :--- |
| Open-Meteo (weather) | Nothing | Works out of the box |
| Action log and photos | Nothing | Works out of the box |
| Garden map | Nothing | Works out of the box |
| Hunter Hydrawise | API key | Working: polling, local watering history |
| Dreame mower | Home Assistant with a Dreame mower custom integration, a long-lived token and the mower's entity ID | Working: mowing sessions are detected from state history with a simple heuristic (states `mowing`, `cleaning` or `on` count as mowing) — adjust it in `app/integrations/dreame.py` if your integration uses other state names |
| Google Gemini (analysis and plant recognition) | API key | Working: every 24 h and on demand |

---

## JSON API

All endpoints except `/health` require a logged-in session (unauthenticated `/api/*` requests get `401`, other routes redirect to `/login`). The OpenAPI docs (`/docs`, `/redoc`, `/openapi.json`) are disabled on purpose.

| Endpoint | Description |
| :--- | :--- |
| `GET /api/timeline?days=14` | Watering, mowing and manual actions merged into one timeline |
| `GET /api/weather/history?days=7` | Stored weather snapshots |
| `GET /api/weather/forecast` | Raw Open-Meteo response |
| `POST /api/analysis?days=14` | Generate and store a new AI insight |
| `GET /api/insights?limit=20` | History of AI insights |
| `GET /actions` | All manual garden actions |
| `GET /health` | Health check (no login required) |

Uploaded photos and map images are served only to logged-in users, and only with image file extensions.

---

## Database Browser (sqlite-web)

`docker-compose.yml` ships an optional `sqlite-web` container bound to `127.0.0.1:8082`.
In the Helm chart the same sidecar is available under `dbWeb.enabled` and is **disabled
by default** — inside a cluster it would listen on the pod IP with no authentication,
letting any other pod read and overwrite the `appsetting` table (Home Assistant token,
Gemini and Hydrawise keys) without logging in. Enable it only temporarily, and preferably
alongside a NetworkPolicy restricting port 8080.

---

## Kubernetes (Helm)

A Helm chart is included in [`charts/ogrodnik`](./charts/ogrodnik). It deploys a single replica with:

*   environment variables loaded from the Secret named in `secretName` (`ogrodnik-secret` by default) — put `ADMIN_PASSWORD`, `SECRET_KEY` and any other variables there,
*   a PersistentVolumeClaim for `/app/data` (`persistence.size`, `persistence.storageClass`),
*   a Traefik ingress with cert-manager TLS and a Traefik `Middleware` adding security headers (HSTS, CSP, `X-Frame-Options`, etc.); set `ingress.hosts` and `ingress.tls` to your own domain.

On every push to `main`, the GitHub Actions workflow builds both images, pushes them to GHCR and commits the new `sha-<commit>` tag to `charts/ogrodnik/values.yaml`, so a GitOps tool such as Argo CD can pick it up.

---

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest
```

The tests cover the login rate limit, sessions, proxy and secret handling, media exposure, `.gitignore` coverage and the Helm chart's `dbWeb` defaults.

---

## Technology Stack

Python 3.12 · FastAPI + Jinja2 (server-side rendering, no SPA) · SQLModel / SQLite · APScheduler · httpx · Tailwind CSS (Play CDN) and Chart.js (jsDelivr) · self-hosted Outfit font · Docker / Docker Compose · Helm.

---

## License

[MIT](./LICENSE) — free to use, modify, and distribute.
