import os
import json
import asyncio
import datetime
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func

import redis.asyncio as aioredis

# Package-qualified imports
from backend.services.alerting import AlertService
from backend.services.sentiment_analyzer import SentimentAnalyzer
from backend.models.models import Base, SocialMediaPost, SentimentAnalysis, SentimentAlert


# ----------------------------------------------------
# FASTAPI APP
# ----------------------------------------------------
app = FastAPI(title="Real-Time Sentiment Analysis API")

# ----------------------------------------------------
# CORS
# ----------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://0.0.0.0:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sentiment_user:sentiment_password@postgres:5432/sentiment_db",
)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_STREAM_NAME = os.getenv("REDIS_STREAM_NAME", "social_posts_stream")

# ----------------------------------------------------
# DATABASE
# ----------------------------------------------------
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ----------------------------------------------------
# REDIS
# ----------------------------------------------------
redis_client: Optional[aioredis.Redis] = None


# ----------------------------------------------------
# STARTUP / SHUTDOWN
# ----------------------------------------------------
@app.on_event("startup")
async def startup_event():
    # Create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Init Redis
    global redis_client
    try:
        redis_client = aioredis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
        )
        await redis_client.ping()
    except Exception:
        redis_client = None
    else:
        asyncio.create_task(_redis_pubsub_forward())

    # Start alert monitoring (non-blocking)
    try:
        alert_service = AlertService(AsyncSessionLocal, redis_client)
        asyncio.create_task(alert_service.run_monitoring_loop())
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.close()


# ----------------------------------------------------
# REDIS → WEBSOCKET FORWARDER
# ----------------------------------------------------
async def _redis_pubsub_forward():
    if not redis_client:
        return

    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("sentiment_channel")

        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue

            try:
                payload = json.loads(message["data"])
            except Exception:
                payload = {"type": "raw", "data": message["data"]}

            await manager.broadcast(payload)
    except Exception:
        return


# ----------------------------------------------------
# HEALTH ENDPOINT
# ----------------------------------------------------
@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    status = "healthy"
    services = {"database": "connected", "redis": "connected"}

    try:
        await db.execute(select(func.now()))
    except Exception:
        services["database"] = "disconnected"
        status = "unhealthy"

    try:
        if redis_client is None:
            raise RuntimeError("Redis not initialized")
        await redis_client.ping()
    except Exception:
        services["redis"] = "disconnected"
        status = "unhealthy"

    total_posts = 0
    total_analyses = 0

    try:
        res = await db.execute(select(func.count()).select_from(SocialMediaPost))
        total_posts = res.scalar() or 0

        res2 = await db.execute(select(func.count()).select_from(SentimentAnalysis))
        total_analyses = res2.scalar() or 0
    except Exception:
        pass

    return {
        "status": status,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "services": services,
        "stats": {
            "total_posts": total_posts,
            "total_analyses": total_analyses,
        },
    }


# ----------------------------------------------------
# POSTS ENDPOINT
# ----------------------------------------------------
@app.get("/api/posts")
async def get_posts(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    sentiment: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SocialMediaPost)
        .order_by(SocialMediaPost.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if source:
        stmt = stmt.where(SocialMediaPost.source == source)

    results = await db.execute(stmt)
    posts = results.scalars().all()

    output = []
    for post in posts:
        res = await db.execute(
            select(SentimentAnalysis)
            .where(SentimentAnalysis.post_id == post.post_id)
            .order_by(SentimentAnalysis.analyzed_at.desc())
            .limit(1)
        )
        analysis = res.scalars().first()

        if sentiment and (not analysis or analysis.sentiment_label != sentiment):
            continue

        output.append(
            {
                "post_id": post.post_id,
                "source": post.source,
                "content": post.content,
                "author": post.author,
                "created_at": post.created_at.isoformat() if post.created_at else None,
                "sentiment": {
                    "label": analysis.sentiment_label if analysis else None,
                    "confidence": analysis.confidence_score if analysis else None,
                    "emotion": analysis.emotion if analysis else None,
                    "model_name": analysis.model_name if analysis else None,
                },
            }
        )

    return {
        "posts": output,
        "total": len(output),
        "limit": limit,
        "offset": offset,
    }


# ----------------------------------------------------
# SENTIMENT DISTRIBUTION
# ----------------------------------------------------
@app.get("/api/sentiment/distribution")
async def sentiment_distribution(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SentimentAnalysis)
    rows = (await db.execute(stmt)).scalars().all()

    from collections import Counter

    labels = [r.sentiment_label for r in rows if r.sentiment_label]
    counts = Counter(labels)

    total = sum(counts.values())

    return {
        "timeframe_hours": hours,
        "distribution": dict(counts),
        "total": total,
        "percentages": {
            k: (v / total * 100 if total else 0.0) for k, v in counts.items()
        },
        "cached": False,
    }


# ----------------------------------------------------
# SENTIMENT AGGREGATE
# ----------------------------------------------------
@app.get("/api/sentiment/aggregate")
async def sentiment_aggregate(
    period: str = Query(..., regex="^(minute|hour|day)$"),
    start_date: Optional[datetime.datetime] = None,
    end_date: Optional[datetime.datetime] = None,
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    if end_date is None:
        end_date = datetime.datetime.utcnow()
    if start_date is None:
        start_date = end_date - datetime.timedelta(hours=24)

    stmt = (
        select(SentimentAnalysis)
        .where(SentimentAnalysis.analyzed_at >= start_date)
        .where(SentimentAnalysis.analyzed_at <= end_date)
    )

    if source:
        stmt = stmt.join(
            SocialMediaPost,
            SocialMediaPost.post_id == SentimentAnalysis.post_id,
        ).where(SocialMediaPost.source == source)

    rows = (await db.execute(stmt)).scalars().all()

    from collections import defaultdict

    def truncate(dt):
        if period == "minute":
            return dt.replace(second=0, microsecond=0)
        if period == "hour":
            return dt.replace(minute=0, second=0, microsecond=0)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    buckets = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "conf": 0.0, "count": 0})

    for r in rows:
        key = truncate(r.analyzed_at)
        label = r.sentiment_label or "neutral"
        buckets[key][label] += 1
        buckets[key]["conf"] += r.confidence_score or 0.0
        buckets[key]["count"] += 1

    data = []
    for ts in sorted(buckets.keys()):
        b = buckets[ts]
        total = b["count"]
        data.append(
            {
                "timestamp": ts.isoformat(),
                "positive_count": b["positive"],
                "negative_count": b["negative"],
                "neutral_count": b["neutral"],
                "total_count": total,
                "positive_percentage": (b["positive"] / total * 100) if total else 0,
                "negative_percentage": (b["negative"] / total * 100) if total else 0,
                "neutral_percentage": (b["neutral"] / total * 100) if total else 0,
                "average_confidence": (b["conf"] / total) if total else 0,
            }
        )

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "data": data,
        "summary": {
            "total_posts": sum(d["total_count"] for d in data),
            "positive_total": sum(d["positive_count"] for d in data),
            "negative_total": sum(d["negative_count"] for d in data),
            "neutral_total": sum(d["neutral_count"] for d in data),
        },
    }


# ----------------------------------------------------
# WEBSOCKET
# ----------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws/sentiment")
async def websocket_sentiment(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_json(
            {
                "type": "connected",
                "message": "Connected to sentiment stream",
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }
        )
        while True:
            await asyncio.sleep(30)
            await manager.broadcast(
                {
                    "type": "metrics_update",
                    "data": {},
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                }
            )
    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.get("/api/debug")
async def debug_status(db: AsyncSession = Depends(get_db)):
    """Simple debug endpoint returning counts and recent posts."""
    try:
        res = await db.execute(select(func.count()).select_from(SocialMediaPost))
        total_posts = res.scalar() or 0
        res2 = await db.execute(select(func.count()).select_from(SentimentAnalysis))
        total_analyses = res2.scalar() or 0

        r = await db.execute(select(SocialMediaPost).order_by(SocialMediaPost.ingested_at.desc()).limit(10))
        posts = [ { 'post_id': p.post_id, 'source': p.source, 'content': p.content, 'author': p.author, 'created_at': p.created_at.isoformat() if p.created_at else None } for p in r.scalars().all() ]
    except Exception as e:
        return { 'error': str(e) }

    return { 'total_posts': total_posts, 'total_analyses': total_analyses, 'recent_posts': posts }
