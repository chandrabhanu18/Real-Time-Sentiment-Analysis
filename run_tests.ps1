#!/usr/bin/env pwsh
Write-Host "Stopping any existing compose stack..."
docker compose down --volumes --remove-orphans

Write-Host "Building and starting services (will run in background) — BuildKit disabled to avoid snapshot errors..."
# Disable BuildKit for this session to avoid Docker snapshot/buildkit issues on some systems
$Env:DOCKER_BUILDKIT = "0"
docker compose build --no-cache
docker compose up -d --build

Start-Sleep -Seconds 10

Write-Host "Running backend tests..."
docker compose exec backend pytest -v

Write-Host "Running backend tests with coverage..."
docker compose exec backend pytest --cov=backend --cov-report=term

Write-Host "Tests complete. If the worker or build still failed with snapshot errors, run docker builder prune --force and re-run this script."
