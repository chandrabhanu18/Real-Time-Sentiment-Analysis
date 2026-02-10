import datetime
import json

import pytest

from backend import main
from backend.models.models import SocialMediaPost, SentimentAnalysis


class FakeRedis:
    def __init__(self):
        self._data = {}

    async def get(self, key):
        return self._data.get(key)

    async def set(self, key, value, ex=None):
        self._data[key] = value


@pytest.mark.asyncio
async def test_distribution_filters_and_cache(client, db_session, monkeypatch):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="cache-1",
        source="reddit",
        content="Neutral update",
        author="tester",
        created_at=now,
    )
    db_session.add(post)
    db_session.add(
        SentimentAnalysis(
            post_id="cache-1",
            model_name="m",
            sentiment_label="neutral",
            confidence_score=0.7,
            emotion="neutral",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    fake_redis = FakeRedis()
    monkeypatch.setattr(main, "redis_client", fake_redis)

    resp = await client.get("/api/sentiment/distribution?hours=24&source=reddit")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["distribution"]["neutral"] >= 1
    assert "percentages" in payload

    cached = json.dumps(payload)
    await fake_redis.set("sentiment_cache:distribution:24:reddit", cached, ex=60)
    resp2 = await client.get("/api/sentiment/distribution?hours=24&source=reddit")
    assert resp2.status_code == 200
    payload2 = resp2.json()
    assert payload2["cached"] is True


@pytest.mark.asyncio
async def test_posts_filters_and_aggregate(client, db_session):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="filter-1",
        source="twitter",
        content="This is fantastic",
        author="tester",
        created_at=now,
    )
    db_session.add(post)
    db_session.add(
        SentimentAnalysis(
            post_id="filter-1",
            model_name="m",
            sentiment_label="positive",
            confidence_score=0.82,
            emotion="joy",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    start = (now - datetime.timedelta(minutes=5)).isoformat()
    end = (now + datetime.timedelta(minutes=5)).isoformat()
    resp = await client.get(
        f"/api/posts?limit=5&offset=0&source=twitter&sentiment=positive&start_date={start}&end_date={end}"
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert payload["filters"]["source"] == "twitter"

    agg = await client.get("/api/sentiment/aggregate?period=minute&source=twitter")
    assert agg.status_code == 200
    agg_payload = agg.json()
    assert agg_payload["period"] == "minute"