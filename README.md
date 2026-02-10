# Real-Time Sentiment Analysis Platform

Build a production-grade platform that ingests social posts, analyzes sentiment and emotion with AI models, stores results, and streams live updates to a dashboard.

## Features

- Redis Streams ingestion with consumer groups and acknowledgments
- Dual-model AI analysis (local Hugging Face + external Groq LLM)
- FastAPI REST endpoints and WebSocket streaming
- PostgreSQL storage for posts, analyses, and alerts
- React + Vite dashboard with live charts via Recharts
- Docker Compose orchestration for zero-config startup

## Architecture Overview

See ARCHITECTURE.md for the system diagram, data flow, and service responsibilities.

## Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- 4GB RAM minimum
- Ports 3000 and 8000 available
- Groq API key (https://console.groq.com)

## Quick Start

```bash
# Clone repository
git clone <repo-url>
cd Real-Time-Sentiment-Analysis

# Copy environment template
cp .env.example .env

# Edit .env file with your API keys
nano .env

# Start all services
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
docker-compose ps

# Access dashboard
# Open http://localhost:3000 in browser

# Stop services
docker-compose down
```

## Configuration

All configuration is provided via environment variables in .env.

- POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT: Postgres connection settings
- DATABASE_URL: SQLAlchemy async connection string
- REDIS_HOST, REDIS_PORT: Redis connection settings
- REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, REDIS_CONSUMER_NAME: Redis Streams configuration
- REDIS_CACHE_PREFIX: Redis cache key prefix for API caching
- INGESTER_POSTS_PER_MINUTE: Ingestion rate
- HUGGINGFACE_MODEL, EMOTION_MODEL: Local model identifiers
- EXTERNAL_LLM_PROVIDER, EXTERNAL_LLM_API_KEY, EXTERNAL_LLM_MODEL: External LLM settings
- API_HOST, API_PORT, FRONTEND_PORT, LOG_LEVEL: Service ports and logging
- ALERT_NEGATIVE_RATIO_THRESHOLD, ALERT_WINDOW_MINUTES, ALERT_MIN_POSTS: Alert thresholds

## API Documentation

REST endpoints:

- GET /api/health
- GET /api/posts
- GET /api/sentiment/aggregate
- GET /api/sentiment/distribution

WebSocket:

- ws://localhost:8000/ws/sentiment

OpenAPI docs are available at http://localhost:8000/docs.

## Testing Instructions

```bash
# Run backend tests with coverage
docker-compose exec backend pytest --cov=backend --cov-report=term
```

## Troubleshooting

- Services restarting: check logs with `docker-compose logs <service>`
- Redis/DB connection errors: ensure health checks are passing with `docker-compose ps`
- Slow model download: first run pulls Hugging Face models; allow extra time
- Frontend blank: ensure backend is reachable at http://localhost:8000

## Project Structure

```
backend/     # FastAPI API + services + models
worker/      # Redis Stream consumer + analysis pipeline
ingester/    # Redis Stream producer
frontend/    # React + Vite dashboard
```

## License

MIT
