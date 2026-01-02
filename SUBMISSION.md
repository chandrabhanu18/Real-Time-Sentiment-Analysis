Submission Checklist
====================

Run these steps locally to verify the project before submitting:

1) Copy environment template

```bash
cp .env.example .env
# Edit .env to set POSTGRES_PASSWORD and optional API keys
```

2) Start all services

```bash
docker compose up -d --build
```

3) Verify services are running

```bash
docker compose ps
curl -sS http://localhost:8000/api/health | jq .
curl -I http://localhost:3000
```

4) Run backend tests and coverage

```bash
./run_tests.sh    # or .\run_tests.ps1 on Windows
```

Optional quick verification script

```powershell
# from repo root on Windows PowerShell
docker compose up -d --build
Start-Sleep -Seconds 6
Write-Output 'Checking backend API...'
curl http://localhost:8000/api/posts | ConvertFrom-Json | Select-Object -First 1
Write-Output 'Open dashboard at http://localhost:3000'
```

5) Confirm coverage >= 70% (pytest prints coverage summary)

6) Ensure .env.example, README.md, ARCHITECTURE.md, docker-compose.yml, and backend/tests/ are included in repository
 
7) Add submission artifacts

- Record a short demo video (5–8 minutes) showing the steps in this checklist and the live dashboard. Upload the video and include the link below.
- Include the final commit SHA and the video URL in this file before submitting.

Submission metadata (fill before final submission):

- Commit: ___________________________
- Demo video: _______________________

Acceptance criteria (reviewer checklist)

- `docker compose up -d --build` starts all services and `docker compose ps` shows services Up
- Backend OpenAPI available at `http://localhost:8000/docs`
- `http://localhost:3000` serves the dashboard with live charts
- Worker processes ingested posts and backend returns posts via `/api/posts`
- Tests run and coverage reported (>= 70%)
- `SUBMISSION.md`, `README.md`, `.env.example`, `docker-compose.yml`, and `backend/tests/` present in the repo
