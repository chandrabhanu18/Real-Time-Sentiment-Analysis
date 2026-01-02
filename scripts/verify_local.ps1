# Quick verification script for Windows PowerShell
Write-Host "Bringing up services..."
$Env:DOCKER_BUILDKIT = "0"
docker compose up -d --build
Start-Sleep -Seconds 6

Write-Host "Services:"
docker compose ps

Write-Host "Backend health:" 
try{ docker run --rm byrnedo/alpine-curl -sS http://host.docker.internal:8000/api/health | ConvertFrom-Json } catch { try{ curl http://localhost:8000/api/health } catch { Write-Host 'Health check failed' } }

Write-Host "First post (if any):"
try{ docker run --rm byrnedo/alpine-curl -sS http://host.docker.internal:8000/api/posts | jq '.[0]' } catch { Write-Host 'Failed to fetch posts (jq missing in container)' }

Write-Host "UI: http://localhost:3000"
Write-Host "Done. If any commands above failed, check logs with: docker compose logs backend worker ingester"