# Sentiment Analysis — Submission-Ready

Quick-start (Docker-light): this project runs 6 services: Postgres, Redis, Ingester, Worker, Backend API, Frontend.
# Sentiment Analysis — Submission-Ready

This repository contains a small, containerized sentiment analysis platform (6 services): Postgres, Redis, Ingester, Worker, Backend (FastAPI) and Frontend (static dashboard).

Quick start
-----------

Prerequisites
- Docker (with Compose v2)

1) Copy the environment template and edit secrets if needed:

```bash
cp .env.example .env
# edit .env to set POSTGRES_PASSWORD and any API keys
```

2) Build and start all services:

```bash
docker compose up -d --build
```

3) Verify basic services:

```bash
docker compose ps
curl -sS http://localhost:8000/api/health | jq .
# Open the UI: http://localhost:3000
```

Helper scripts
--------------
- `run_tests.sh` / `run_tests.ps1` — builds, starts services and runs backend tests with coverage
- `scripts/verify_local.sh` / `scripts/verify_local.ps1` — quick smoke checks to confirm the stack

Run backend tests
-----------------

Use the helper to build/start the stack and run pytest with coverage:

```bash
./run_tests.sh    # or .\run_tests.ps1 on Windows
```

Quick verification
------------------

Run the smoke-check helper to confirm the stack and endpoints:

```bash
scripts/verify_local.sh    # or scripts\verify_local.ps1 on Windows
```

Running tests (optional virtualenv)
----------------------------------

```bash
python -m venv .venv
.venv/bin/activate        # macOS / Linux
# or: .venv\Scripts\Activate.ps1  # PowerShell on Windows
pip install -r backend/requirements.txt
pytest -q --cov=backend
```

Project layout
--------------

- `backend/` — FastAPI backend, async SQLAlchemy models, REST & WebSocket
- `worker/` — background worker consuming Redis Streams and analyzing posts
- `ingester/` — publishes simulated social posts into Redis Stream
- `frontend/` — static dashboard served by nginx
- `docker-compose.yml` — orchestrates services
- `.env.example` — environment variables template

Developer notes
---------------

- The worker includes a startup wait loop to avoid DB race conditions on fresh Postgres initialization.
- The frontend includes a Chart.js CDN fallback and local `chart.min.js` to ensure charts load behind restricted networks.
- If image build/export errors occur on your system, run `docker builder prune --force` and re-run the build.

Access URLs
-----------

- Backend OpenAPI: http://localhost:8000/docs
- Backend Health Check: http://localhost:8000/api/health
- Posts API: http://localhost:8000/api/posts
- Frontend UI (dashboard): http://localhost:3000

If you hit issues, run the verification script and paste outputs when asking for help:

PowerShell:
```powershell
.\scripts\verify_local.ps1
```

Bash:
```bash
./scripts/verify_local.sh
```

For submission instructions and the final checklist see `SUBMISSION.md`.

