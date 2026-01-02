#!/usr/bin/env bash
set -euo pipefail

echo "Stopping any existing compose stack..."
docker compose down --volumes --remove-orphans || true

echo "Building and starting services (will run in background) — BuildKit disabled to avoid snapshot errors..."
# Disable BuildKit for this build to avoid snapshot/extraction errors on some Docker setups
export DOCKER_BUILDKIT=0
docker compose build --no-cache
docker compose up -d --build

echo "Waiting 10s for services to become healthy..."
sleep 10

echo "Running backend tests..."
docker compose exec backend pytest -v

echo "Running backend tests with coverage..."
docker compose exec backend pytest --cov=backend --cov-report=term

echo "Tests complete. If you still see build/extraction errors, run: docker builder prune --force and re-run this script."
