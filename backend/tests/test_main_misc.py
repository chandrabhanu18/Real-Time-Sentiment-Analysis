import datetime

import pytest
from fastapi.testclient import TestClient

from backend.main import app, _collect_metrics
from backend import main as main_module
from backend.models.models import SentimentAnalysis, SentimentAlert
from backend.services.alerting import AlertService


@pytest.mark.asyncio
async def test_collect_metrics(db_session):
    now = datetime.datetime.utcnow()
    db_session.add(
        SentimentAnalysis(
            post_id="metrics-1",
            model_name="m",
            sentiment_label="positive",
            confidence_score=0.8,
            emotion="joy",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    data = await _collect_metrics(db_session)
    assert "last_hour" in data
    assert data["last_hour"]["total"] >= 1


def test_websocket_connects():
    client = TestClient(app)
    with client.websocket_connect("/ws/sentiment") as websocket:
        msg = websocket.receive_json()
        assert msg["type"] == "connected"


@pytest.mark.asyncio
async def test_alert_save(db_session):
    service = AlertService(lambda: db_session)
    alert_id = await service.save_alert(
        {
            "alert_type": "high_negative_ratio",
            "threshold": 2.0,
            "actual_ratio": 3.5,
            "window_start": datetime.datetime.utcnow().isoformat(),
            "window_end": datetime.datetime.utcnow().isoformat(),
            "post_count": 12,
            "metrics": {"total_count": 12},
        }
    )
    assert isinstance(alert_id, int)
    saved = (await db_session.get(SentimentAlert, alert_id))
    assert saved is not None


@pytest.mark.asyncio
async def test_debug_endpoint(client, db_session):
    now = datetime.datetime.utcnow()
    db_session.add(
        SentimentAnalysis(
            post_id="debug-1",
            model_name="m",
            sentiment_label="neutral",
            confidence_score=0.5,
            emotion="neutral",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    resp = await client.get("/api/debug")
    assert resp.status_code == 200
    payload = resp.json()
    assert "total_posts" in payload


@pytest.mark.asyncio
async def test_health_with_fake_redis(client, monkeypatch):
    class PingRedis:
        async def ping(self):
            return True

    monkeypatch.setattr(main_module, "redis_client", PingRedis())
    resp = await client.get("/api/health")
    assert resp.status_code in (200, 503)