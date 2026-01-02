# Architecture Overview

This project is a microservice-based real-time sentiment analysis platform.

Services:
- Postgres: stores `social_media_posts`, `sentiment_analysis`, and `sentiment_alerts`.
- Redis: message bus (Redis Streams) and pub/sub for real-time WebSocket forwarding.
- Ingester: synthetic/post ingestion into Redis stream.
- Worker: consumes Redis stream, analyzes sentiment (local transformers optional), writes to Postgres, publishes WebSocket events.
- Backend: FastAPI app exposing REST endpoints and WebSocket `/ws/sentiment`.
- Frontend: static dashboard (Chart.js) connecting to backend.

Notes:
- To avoid long Docker builds, heavy ML dependencies (`transformers`, `torch`) are not installed by default. Use `worker/requirements-ml.txt` or build the worker image with ML extras.
- Startup order uses Docker healthchecks for Postgres and Redis; services are resilient to temporary delays.
# Architecture Overview

Services:

- Postgres: relational storage for posts, analysis and alerts
- Redis: message bus (Redis Streams) and pub/sub for realtime events
- Ingester: generates simulated social posts and XADD to Redis Stream
- Worker: XREADGROUP from Redis Stream, runs sentiment/emotion analysis and stores results
- Backend: FastAPI providing REST endpoints and WebSocket to clients
- Frontend: simple dashboard (static) connecting to API and WebSocket

Data flow:

1. Ingester publishes posts to Redis Stream `social_posts_stream`.
2. Worker consumes messages from stream via consumer group, analyzes and stores into Postgres.
3. Worker publishes lightweight events to Redis pub/sub channel `sentiment_channel` for realtime delivery.
4. Backend subscribes to `sentiment_channel` and broadcasts to connected WebSocket clients.

Design decisions:

- Use Redis Streams for ingestion (at-least-once delivery) and Redis Pub/Sub for low-latency realtime events.
- Async FastAPI + SQLAlchemy async for scalable non-blocking API.
- Transformers pipelines for local analysis with rule-based fallbacks.
