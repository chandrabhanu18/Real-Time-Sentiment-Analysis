#!/usr/bin/env bash
set -euo pipefail

echo "Bringing up services..."
export DOCKER_BUILDKIT=0
docker compose up -d --build

echo "Waiting for services to start..."
sleep 6

echo "Services:"
docker compose ps

echo "Backend health:" 
curl -sS http://localhost:8000/api/health | jq . || true

echo "First post (if any):"
curl -sS http://localhost:8000/api/posts | jq '.[0]'

echo "UI: http://localhost:3000"

echo "Done. If any commands above failed, check logs with: docker compose logs backend worker ingester"