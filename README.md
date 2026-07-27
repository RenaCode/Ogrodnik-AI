# 🌱 Ogrodnik AI (Garden Assistant AI)

A web-based garden dashboard that aggregates:

*   **Irrigation** — Hunter Hydrawise (Wi-Fi),
*   **Mowing** — Dreame robot (via Home Assistant bridge),
*   **Weather** — Local garden coordinates forecast (Open-Meteo, API key not required),
*   **Manual action logs** (fertilizing, planting, pruning, plant protection) with photos,
*   **Garden map** with plant positioning (interactive pins on a photo or sketch),
*   **AI Analysis (Gemini)** — Auto-generated insights and recommendations every 24 hours, on-demand analysis, and plant species recognition from photos.

All collected data is stored in a local SQLite database, as the default Home Assistant recorder only keeps history for ~10 days.

---

## Features

| Area | Description |
| :--- | :--- |
| Dashboard | Summary of watering, mowing, weather, and latest AI insights |
| Hunter Hydrawise | Schedule polling, local watering history builder |
| Dreame Mower | Mowing history fetched via Home Assistant (REST API) |
| Weather | Real-time and forecast data for the garden's coordinates (Open-Meteo) |
| Action Logs | Form and photo uploads for fertilizing, planting, pruning, etc. |
| Garden Map | Upload a photo/sketch, click to set locations, and map plants with pins |
| AI Plant Recognition | Upload a photo of a plant; Gemini Vision suggests species for mapping |
| AI Analysis | Daily automated reports (every 24h) + on-demand analysis with history |
| Settings in UI | Edit API keys and coordinates directly in the app without container restarts |

---

## Quick Start (Docker — Recommended)

```bash
git clone <your-repo-url> ogrodnik-ai
cd ogrodnik-ai

cp .env.example .env
# You can leave most of .env empty — all API keys can 
# be entered later in the application under "Settings"

docker compose up -d --build
```

Open `http://localhost:8000`

All data (SQLite database, uploaded photos, and maps) is stored in the Docker volume `ogrodnik_data`, so it will persist across container restarts and rebuilds.

---

## Quick Start (Local, without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env

uvicorn app.main:app --reload
```

Open `http://localhost:8000`

---

## API Key Configuration

Keys (Hydrawise, Home Assistant, Gemini) can be configured in two ways:

1.  **In the Application**: In the *Settings* tab (`/settings`). Values configured here override `.env` and take effect immediately without restarting the container — ideal for Docker deployments.
2.  **In the `.env` File**: Before the first launch, see [`.env.example`](./.env.example).

The application works out of the box (without any keys) for the dashboard, garden action log with photo uploads, garden map, and weather (Open-Meteo does not require a key). Hydrawise, Dreame/Home Assistant, and Gemini AI activate automatically once their corresponding configuration is supplied.

---

## Integration Status

| Integration | Requires | POC Status |
| :--- | :--- | :--- |
| Open-Meteo (Weather) | Nothing | Active out of the box |
| Action Log & Photos | Nothing | Active out of the box |
| Garden Map (Plants) | Nothing | Active out of the box |
| Hunter Hydrawise | API key | Working (polling, local history building) |
| Dreame Mower | Home Assistant + mower integration | Core skeleton ready, requires configured Home Assistant |
| Gemini AI (Analysis & Plant ID) | API key from [aistudio.google.com](https://aistudio.google.com/apikey) | Working (automatically every 24h + on-demand) |

---

## Technology Stack

FastAPI + Jinja2 (server-side rendering, no SPA) · SQLModel/SQLite · APScheduler · httpx · Tailwind CSS & Chart.js via CDN · Docker / Docker Compose.

---

## License

[MIT](./LICENSE) — free to use, modify, and distribute.
