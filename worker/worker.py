import asyncio
import datetime
import json
import os
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from redis.exceptions import ResponseError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.models.models import Base, SocialMediaPost, SentimentAnalysis
from backend.services.sentiment_analyzer import SentimentAnalyzer


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentiment_worker")


def _parse_dt(value: Any) -> Optional[datetime.datetime]:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        dt = value
        if dt.tzinfo is not None:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


async def save_post_and_analysis(
    db_session: AsyncSession,
    post_data: Dict[str, Any],
    sentiment_result: Dict[str, Any],
    emotion_result: Dict[str, Any],
) -> tuple[int, int]:
    post_id = str(post_data["post_id"])
    existing = (
        await db_session.execute(select(SocialMediaPost).where(SocialMediaPost.post_id == post_id))
    ).scalars().first()

    created_at = _parse_dt(post_data.get("created_at"))
    if existing is None:
        post = SocialMediaPost(
            post_id=post_id,
            source=post_data.get("source"),
            content=post_data.get("content"),
            author=post_data.get("author"),
            created_at=created_at,
            ingested_at=datetime.datetime.utcnow(),
        )
        db_session.add(post)
    else:
        existing.ingested_at = datetime.datetime.utcnow()
        post = existing

    await db_session.flush()

    analysis = SentimentAnalysis(
        post_id=post_id,
        model_name=sentiment_result.get("model_name"),
        sentiment_label=sentiment_result.get("sentiment_label"),
        confidence_score=sentiment_result.get("confidence_score"),
        emotion=emotion_result.get("emotion"),
        analyzed_at=datetime.datetime.utcnow(),
    )
    db_session.add(analysis)

    await db_session.commit()
    await db_session.refresh(post)
    await db_session.refresh(analysis)
    return post.id, analysis.id


class SentimentWorker:
    """
    Consumes posts from Redis Stream and processes them through sentiment analysis.
    """

    def __init__(self, redis_client, db_session_maker, stream_name: str, consumer_group: str):
        self.redis = redis_client
        self.db = db_session_maker
        self.stream = stream_name
        self.group = consumer_group
        self.consumer_name = os.getenv("REDIS_CONSUMER_NAME", "worker-1")
        self.local_analyzer = SentimentAnalyzer(model_type="local")
        self.external_analyzer = SentimentAnalyzer(model_type="external")
        self.processed = 0
        self.errors = 0

    async def ensure_consumer_group(self):
        try:
            await self.redis.xgroup_create(self.stream, self.group, id="0-0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def process_message(self, message_id: str, message_data: dict) -> bool:
        required = {"post_id", "source", "content", "author", "created_at"}
        if not required.issubset(message_data.keys()):
            await self.redis.xack(self.stream, self.group, message_id)
            return False

        try:
            sentiment = await self.local_analyzer.analyze_sentiment(message_data["content"])
            emotion = await self.local_analyzer.analyze_emotion(message_data["content"])
        except Exception:
            try:
                sentiment = await self.external_analyzer.analyze_sentiment(message_data["content"])
                emotion = await self.external_analyzer.analyze_emotion(message_data["content"])
            except Exception:
                logger.exception("Worker sentiment analysis failed")
                self.errors += 1
                return False

        try:
            async with self.db() as session:
                await save_post_and_analysis(session, message_data, sentiment, emotion)
        except Exception:
            logger.exception("Worker DB save failed")
            self.errors += 1
            return False

        await self.redis.xack(self.stream, self.group, message_id)
        await self._publish_new_post(message_data, sentiment, emotion)
        self.processed += 1
        return True

    async def _publish_new_post(self, message_data, sentiment, emotion):
        payload = {
            "type": "new_post",
            "data": {
                "post_id": message_data.get("post_id"),
                "content": str(message_data.get("content", ""))[:100],
                "source": message_data.get("source"),
                "sentiment_label": sentiment.get("sentiment_label"),
                "confidence_score": sentiment.get("confidence_score"),
                "emotion": emotion.get("emotion"),
                "timestamp": datetime.datetime.utcnow().isoformat(),
            },
        }
        try:
            await self.redis.publish("sentiment_channel", json.dumps(payload))
        except Exception:
            pass

    async def run(self, batch_size: int = 10, block_ms: int = 5000):
        await self.ensure_consumer_group()
        backoff = 1

        while True:
            try:
                resp = await self.redis.xreadgroup(
                    self.group,
                    self.consumer_name,
                    {self.stream: ">"},
                    count=batch_size,
                    block=block_ms,
                )
                backoff = 1
            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue

            for _, messages in resp:
                await asyncio.gather(
                    *[self.process_message(mid, data) for mid, data in messages]
                )


async def _create_db_engine():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://sentiment_user:sentiment_password@postgres:5432/sentiment_db",
    )
    engine = create_async_engine(database_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def main():
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    stream_name = os.getenv("REDIS_STREAM_NAME", "social_posts_stream")
    consumer_group = os.getenv("REDIS_CONSUMER_GROUP", "sentiment_workers")

    redis_client = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)

    engine = await _create_db_engine()
    session_maker = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    worker = SentimentWorker(redis_client, session_maker, stream_name, consumer_group)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
