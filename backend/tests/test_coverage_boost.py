import datetime
import asyncio
import json
import sys

import pytest

from backend import database
from backend import main
from backend.main import ConnectionManager, _cache_distribution_payload, _metrics_broadcaster, _redis_pubsub_forward
from backend.models.models import SocialMediaPost, SentimentAnalysis
from backend.services.alerting import AlertService
from backend.services.sentiment_analyzer import SentimentAnalyzer


@pytest.mark.asyncio
async def test_database_module_initializes():
    assert database.engine is not None
    assert database.AsyncSessionLocal is not None


@pytest.mark.asyncio
async def test_distribution_with_source_filter_no_cache(client, db_session, monkeypatch):
    now = datetime.datetime.utcnow()
    db_session.add(
        SocialMediaPost(
            post_id="dist-1",
            source="reddit",
            content="Great product",
            author="tester",
            created_at=now,
        )
    )
    db_session.add(
        SentimentAnalysis(
            post_id="dist-1",
            model_name="m",
            sentiment_label="positive",
            confidence_score=0.9,
            emotion="joy",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    monkeypatch.setattr(main, "redis_client", None)
    resp = await client.get("/api/sentiment/distribution?hours=24&source=reddit")
    payload = resp.json()
    assert payload["distribution"]["positive"] >= 1
    assert "percentages" in payload
    assert "top_emotions" in payload


@pytest.mark.asyncio
async def test_distribution_cache_hit(client, monkeypatch):
    class CacheRedis:
        async def get(self, _key):
            return json.dumps({
                "timeframe_hours": 24,
                "source": None,
                "distribution": {"positive": 1, "negative": 0, "neutral": 0},
                "total": 1,
                "percentages": {"positive": 100.0, "negative": 0.0, "neutral": 0.0},
                "top_emotions": {"joy": 1},
                "cached": False,
                "cached_at": datetime.datetime.utcnow().isoformat(),
            })

    monkeypatch.setattr(main, "redis_client", CacheRedis())
    resp = await client.get("/api/sentiment/distribution?hours=24")
    payload = resp.json()
    assert payload["cached"] is True


@pytest.mark.asyncio
async def test_aggregate_hour_and_day(client, db_session):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="agg-1",
        source="twitter",
        content="Neutral update",
        author="tester",
        created_at=now,
    )
    db_session.add(post)
    db_session.add(
        SentimentAnalysis(
            post_id="agg-1",
            model_name="m",
            sentiment_label="neutral",
            confidence_score=0.5,
            emotion="neutral",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    resp_hour = await client.get("/api/sentiment/aggregate?period=hour&source=twitter")
    assert resp_hour.status_code == 200
    payload_hour = resp_hour.json()
    assert payload_hour["period"] == "hour"

    resp_day = await client.get("/api/sentiment/aggregate?period=day&source=twitter")
    assert resp_day.status_code == 200
    payload_day = resp_day.json()
    assert payload_day["period"] == "day"


@pytest.mark.asyncio
async def test_aggregate_empty_data(client):
    resp = await client.get("/api/sentiment/aggregate?period=hour")
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload["data"], list)


@pytest.mark.asyncio
async def test_connection_manager_broadcast_error_removes_client():
    class FailingWS:
        async def send_json(self, message):
            raise RuntimeError("send failed")

    manager = ConnectionManager()
    ws = FailingWS()
    manager.active.append(ws)

    await manager.broadcast({"type": "ping"})
    assert ws not in manager.active


@pytest.mark.asyncio
async def test_connection_manager_connect_disconnect():
    class DummyWS:
        async def accept(self):
            return None

    manager = ConnectionManager()
    ws = DummyWS()
    await manager.connect(ws)
    assert ws in manager.active
    manager.disconnect(ws)
    assert ws not in manager.active


@pytest.mark.asyncio
async def test_sentiment_analyzer_external_paths(monkeypatch):
    s = SentimentAnalyzer(model_type="external")

    async def fake_request(_payload):
        return {"sentiment_label": "positive", "confidence_score": 0.8, "emotion": "joy"}

    monkeypatch.setattr(s, "_external_request", fake_request)
    res = await s.analyze_sentiment("Great job")
    assert res["sentiment_label"] == "positive"

    emo = await s.analyze_emotion("I feel great today")
    assert emo["emotion"] == "joy"

    wrapped = s._extract_json("```json\n{\"sentiment_label\":\"neutral\",\"confidence_score\":0.4}\n```")
    assert wrapped.get("sentiment_label") == "neutral"

    s_no_key = SentimentAnalyzer(model_type="external")
    s_no_key.external_api_key = None
    payload = await s_no_key._external_request({})
    assert payload == {}

    s_other = SentimentAnalyzer(model_type="external")
    s_other.provider = "other"
    s_other.external_api_key = "x"
    payload = await s_other._external_request({})
    assert payload == {}


@pytest.mark.asyncio
async def test_sentiment_analyzer_empty_and_short_text():
    s = SentimentAnalyzer(model_type="local")
    result = await s.analyze_sentiment("  ")
    assert result["sentiment_label"] == "neutral"

    with pytest.raises(ValueError):
        await s.analyze_emotion("   ")

    short = await s.analyze_emotion("too short")
    assert short["emotion"] == "neutral"


@pytest.mark.asyncio
async def test_sentiment_analyzer_external_request_success(monkeypatch):
    s = SentimentAnalyzer(model_type="external")
    s.external_api_key = "key"
    s.provider = "groq"

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "{\"sentiment_label\": \"positive\", \"confidence_score\": 0.9}",
                        }
                    }
                ]
            }

    async def fake_post(_url, headers=None, json=None):
        return DummyResponse()

    monkeypatch.setattr(s._client, "post", fake_post)
    data = await s._external_request({"model": "x"})
    assert data["sentiment_label"] == "positive"


@pytest.mark.asyncio
async def test_sentiment_analyzer_batch_fallback_on_error(monkeypatch):
    s = SentimentAnalyzer(model_type="local")

    async def fake_analyze(text):
        if "bad" in text:
            raise RuntimeError("boom")
        return {"sentiment_label": "positive", "confidence_score": 0.9, "model_name": "m"}

    monkeypatch.setattr(s, "analyze_sentiment", fake_analyze)
    results = await s.batch_analyze(["ok", "bad"])
    assert results[0]["sentiment_label"] == "positive"
    assert results[1]["sentiment_label"] is None


@pytest.mark.asyncio
async def test_alert_save_with_invalid_dates(db_session):
    service = AlertService(lambda: db_session)
    alert_id = await service.save_alert(
        {
            "alert_type": "high_negative_ratio",
            "threshold": 2.0,
            "actual_ratio": 3.0,
            "window_start": "bad-date",
            "window_end": "bad-date",
            "post_count": 5,
            "metrics": {"total_count": 5},
        }
    )
    assert isinstance(alert_id, int)


@pytest.mark.asyncio
async def test_alert_check_thresholds_min_posts(db_session):
    now = datetime.datetime.utcnow()
    db_session.add(
        SentimentAnalysis(
            post_id="alert-min-1",
            model_name="m",
            sentiment_label="positive",
            confidence_score=0.9,
            emotion="joy",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    service = AlertService(lambda: db_session)
    service.min_posts = 100000
    alert = await service.check_thresholds()
    assert alert is None


@pytest.mark.asyncio
async def test_alert_check_thresholds_ratio_exceeds(db_session):
    now = datetime.datetime.utcnow()
    db_session.add(
        SentimentAnalysis(
            post_id="alert-neg-1",
            model_name="m",
            sentiment_label="negative",
            confidence_score=0.2,
            emotion="anger",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    service = AlertService(lambda: db_session)
    service.min_posts = 1
    service.threshold = -1.0
    alert = await service.check_thresholds()
    assert alert is not None
    assert alert["alert_triggered"] is True


@pytest.mark.asyncio
async def test_alert_check_thresholds_ratio_not_exceed(db_session):
    now = datetime.datetime.utcnow()
    db_session.add(
        SentimentAnalysis(
            post_id="alert-pos-1",
            model_name="m",
            sentiment_label="positive",
            confidence_score=0.8,
            emotion="joy",
            analyzed_at=now,
        )
    )
    db_session.add(
        SentimentAnalysis(
            post_id="alert-pos-2",
            model_name="m",
            sentiment_label="positive",
            confidence_score=0.7,
            emotion="joy",
            analyzed_at=now,
        )
    )
    db_session.add(
        SentimentAnalysis(
            post_id="alert-neg-2",
            model_name="m",
            sentiment_label="negative",
            confidence_score=0.3,
            emotion="sadness",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    service = AlertService(lambda: db_session)
    service.min_posts = 1
    service.threshold = float("inf")
    alert = await service.check_thresholds()
    assert alert is None


@pytest.mark.asyncio
async def test_health_endpoint_db_failure(client, db_session, monkeypatch):
    async def raise_exec(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(db_session, "execute", raise_exec)
    monkeypatch.setattr(main, "redis_client", None)

    resp = await client.get("/api/health")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_health_degraded_when_redis_down(client, monkeypatch):
    class BadRedis:
        async def ping(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(main, "redis_client", BadRedis())
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["services"]["redis"] == "disconnected"


@pytest.mark.asyncio
async def test_health_counts_present(client, db_session):
    now = datetime.datetime.utcnow()
    db_session.add(
        SocialMediaPost(
            post_id="health-1",
            source="reddit",
            content="Great",
            author="tester",
            created_at=now,
        )
    )
    db_session.add(
        SentimentAnalysis(
            post_id="health-1",
            model_name="m",
            sentiment_label="positive",
            confidence_score=0.9,
            emotion="joy",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    resp = await client.get("/api/health")
    payload = resp.json()
    assert payload["stats"]["total_posts"] >= 1


@pytest.mark.asyncio
async def test_posts_without_analysis_returns_nulls(client, db_session):
    now = datetime.datetime.utcnow()
    db_session.add(
        SocialMediaPost(
            post_id="post-no-analysis",
            source="reddit",
            content="Content",
            author="tester",
            created_at=now,
        )
    )
    await db_session.commit()

    resp = await client.get("/api/posts?limit=5")
    payload = resp.json()
    assert payload["total"] >= 1


@pytest.mark.asyncio
async def test_metrics_broadcaster_sends_once(monkeypatch):
    class DummyWS:
        async def send_json(self, message):
            self.message = message

    dummy = DummyWS()
    main.manager.active = [dummy]

    async def fake_collect(_db):
        return {"last_minute": {"positive": 1, "negative": 0, "neutral": 0, "total": 1}}

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "_collect_metrics", fake_collect)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await _metrics_broadcaster()

    assert dummy.message["type"] == "metrics_update"


@pytest.mark.asyncio
async def test_metrics_broadcaster_no_clients(monkeypatch):
    main.manager.active = []
    called = {"count": 0}

    async def fake_collect(_db):
        called["count"] += 1
        return {}

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "_collect_metrics", fake_collect)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await _metrics_broadcaster()

    assert called["count"] == 0


@pytest.mark.asyncio
async def test_redis_pubsub_forwarder(monkeypatch):
    messages = [
        {"type": "message", "data": json.dumps({"type": "new_post", "data": {"post_id": "x"}})},
        {"type": "message", "data": "not-json"},
    ]

    class DummyPubSub:
        async def subscribe(self, _channel):
            return None

        async def listen(self):
            for item in messages:
                yield item

    class DummyRedis:
        def pubsub(self):
            return DummyPubSub()

    received = []

    async def fake_broadcast(payload):
        received.append(payload)

    monkeypatch.setattr(main, "redis_client", DummyRedis())
    monkeypatch.setattr(main.manager, "broadcast", fake_broadcast)

    await _redis_pubsub_forward()
    assert received[0]["type"] == "new_post"
    assert received[1]["type"] == "raw"


@pytest.mark.asyncio
async def test_redis_pubsub_forwarder_ignores_non_messages(monkeypatch):
    messages = [
        {"type": "subscribe", "data": 1},
        None,
        {"type": "message", "data": json.dumps({"type": "ping"})},
    ]

    class DummyPubSub:
        async def subscribe(self, _channel):
            return None

        async def listen(self):
            for item in messages:
                yield item

    class DummyRedis:
        def pubsub(self):
            return DummyPubSub()

    received = []

    async def fake_broadcast(payload):
        received.append(payload)

    monkeypatch.setattr(main, "redis_client", DummyRedis())
    monkeypatch.setattr(main.manager, "broadcast", fake_broadcast)

    await _redis_pubsub_forward()
    assert received == [{"type": "ping"}]


@pytest.mark.asyncio
async def test_redis_pubsub_forwarder_returns_when_no_redis(monkeypatch):
    monkeypatch.setattr(main, "redis_client", None)
    await _redis_pubsub_forward()


@pytest.mark.asyncio
async def test_debug_endpoint_error_branch(client, db_session, monkeypatch):
    async def raise_exec(*args, **kwargs):
        raise RuntimeError("db error")

    monkeypatch.setattr(db_session, "execute", raise_exec)
    resp = await client.get("/api/debug")
    assert resp.status_code == 200
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_sentiment_mapping_edges():
    s = SentimentAnalyzer(model_type="local")
    neutral_low = s._map_sentiment({"label": "POSITIVE", "score": 0.1}, "m")
    assert neutral_low["sentiment_label"] == "neutral"

    emotion = s._map_emotion({"label": "confused", "score": 0.9}, "m")
    assert emotion["emotion"] == "neutral"


def test_extract_json_returns_empty_when_missing_payload():
    s = SentimentAnalyzer(model_type="external")
    assert s._extract_json("no json here") == {}


@pytest.mark.asyncio
async def test_lifespan_success_starts_tasks_and_closes_redis(monkeypatch):
    tasks = []

    class DummyConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run_sync(self, _fn):
            return None

    class DummyEngine:
        def begin(self):
            return DummyConn()

    class DummyRedis:
        def __init__(self):
            self.closed = False

        async def ping(self):
            return True

        async def close(self):
            self.closed = True

    class DummyAlertService:
        def __init__(self, *_args, **_kwargs):
            return None
        def fake_create_task(coro):
            coro.close()
        async def run_monitoring_loop(self):
            return None

    async def noop_forward():
        return None

    async def noop_metrics():
        return None

    def fake_create_task(coro):
        coro.close()
        tasks.append(coro)

        class DummyTask:
            def cancel(self):
                return None

        return DummyTask()

    dummy_redis = DummyRedis()
    monkeypatch.setattr(main, "engine", DummyEngine())
    monkeypatch.setattr(main.aioredis, "Redis", lambda **_kwargs: dummy_redis)
    monkeypatch.setattr(main, "AlertService", DummyAlertService)
    monkeypatch.setattr(main, "_redis_pubsub_forward", noop_forward)
    monkeypatch.setattr(main, "_metrics_broadcaster", noop_metrics)
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    async with main.lifespan(main.app):
        assert len(tasks) >= 3

    assert dummy_redis.closed is True
    main.redis_client = None


@pytest.mark.asyncio
async def test_lifespan_redis_init_failure(monkeypatch):
    tasks = []

    class DummyConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run_sync(self, _fn):
            return None

    class DummyEngine:
        def begin(self):
            return DummyConn()

    class BadRedis:
        async def ping(self):
            raise RuntimeError("redis down")

    class DummyAlertService:
        def __init__(self, *_args, **_kwargs):
            return None

        async def run_monitoring_loop(self):
            return None

    def fake_create_task(coro):
        coro.close()
        tasks.append(coro)

        class DummyTask:
            def cancel(self):
                return None

        return DummyTask()

    monkeypatch.setattr(main, "engine", DummyEngine())
    monkeypatch.setattr(main.aioredis, "Redis", lambda **_kwargs: BadRedis())
    monkeypatch.setattr(main, "AlertService", DummyAlertService)
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    async with main.lifespan(main.app):
        assert main.redis_client is None

    assert len(tasks) == 1


@pytest.mark.asyncio
async def test_redis_pubsub_forwarder_handles_exception(monkeypatch):
    class DummyPubSub:
        async def subscribe(self, _channel):
            raise RuntimeError("subscribe error")

    class DummyRedis:
        def pubsub(self):
            return DummyPubSub()

    monkeypatch.setattr(main, "redis_client", DummyRedis())
    await _redis_pubsub_forward()


@pytest.mark.asyncio
async def test_health_counts_exception(client, db_session, monkeypatch):
    calls = {"count": 0}

    class DummyResult:
        def scalar(self):
            return 1

    async def fake_execute(_stmt):
        calls["count"] += 1
        if calls["count"] == 1:
            return DummyResult()
        raise RuntimeError("count fail")

    class GoodRedis:
        async def ping(self):
            return True

    monkeypatch.setattr(db_session, "execute", fake_execute)
    monkeypatch.setattr(main, "redis_client", GoodRedis())

    resp = await client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["stats"]["total_posts"] == 0


@pytest.mark.asyncio
async def test_posts_filters_include_analysis(client, db_session):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="post-filter-1",
        source="reddit",
        content="Great product",
        author="tester",
        created_at=now,
    )
    analysis = SentimentAnalysis(
        post_id="post-filter-1",
        model_name="m",
        sentiment_label="positive",
        confidence_score=0.9,
        emotion="joy",
        analyzed_at=now,
    )
    db_session.add(post)
    db_session.add(analysis)
    await db_session.commit()

    start = (now - datetime.timedelta(hours=1)).isoformat()
    end = (now + datetime.timedelta(hours=1)).isoformat()
    resp = await client.get(
        f"/api/posts?limit=5&offset=0&source=reddit&sentiment=positive&start_date={start}&end_date={end}"
    )
    payload = resp.json()
    assert payload["total"] >= 1
    assert payload["posts"][0]["sentiment"]["label"] == "positive"


@pytest.mark.asyncio
async def test_distribution_cache_set_success(client, monkeypatch):
    class CacheRedis:
        def __init__(self):
            self.set_called = False

        async def get(self, _key):
            return None

        async def set(self, _key, _value, ex=None):
            self.set_called = True

    cache = CacheRedis()
    monkeypatch.setattr(main, "redis_client", cache)
    resp = await client.get("/api/sentiment/distribution?hours=1")
    assert resp.status_code == 200
    assert cache.set_called is True


@pytest.mark.asyncio
async def test_aggregate_minute_period(client, db_session):
    now = datetime.datetime.utcnow().replace(second=15, microsecond=0)
    db_session.add(
        SentimentAnalysis(
            post_id="agg-minute-1",
            model_name="m",
            sentiment_label="negative",
            confidence_score=0.2,
            emotion="sadness",
            analyzed_at=now,
        )
    )
    await db_session.commit()

    resp = await client.get("/api/sentiment/aggregate?period=minute")
    payload = resp.json()
    assert payload["period"] == "minute"
    assert payload["data"]


@pytest.mark.asyncio
async def test_websocket_disconnect_removes_client(monkeypatch):
    class DummyWS:
        def __init__(self):
            self.sent = []

        async def accept(self):
            return None

        async def send_json(self, message):
            self.sent.append(message)

        async def receive_text(self):
            raise main.WebSocketDisconnect()

    main.manager.active = []
    ws = DummyWS()
    await main.websocket_sentiment(ws)
    assert ws not in main.manager.active


def test_sentiment_analyzer_init_local_pipeline(monkeypatch):
    class DummyPipeline:
        def __init__(self, result):
            self.result = result

        def __call__(self, _text, truncation=False):
            return [self.result]

    def fake_pipeline(task, model=None, device=None):
        if task == "sentiment-analysis":
            return DummyPipeline({"label": "POSITIVE", "score": 0.9})
        return DummyPipeline({"label": "joy", "score": 0.8})

    class DummyTransformers:
        pipeline = staticmethod(fake_pipeline)

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setitem(sys.modules, "transformers", DummyTransformers())

    s = SentimentAnalyzer(model_type="local")
    assert s.sentiment_pipeline is not None
    assert s.emotion_pipeline is not None


def test_sentiment_analyzer_init_local_pipeline_failure(monkeypatch):
    class DummyTransformers:
        @staticmethod
        def pipeline(*_args, **_kwargs):
            raise RuntimeError("init fail")

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setitem(sys.modules, "transformers", DummyTransformers())

    s = SentimentAnalyzer(model_type="local")
    assert s.sentiment_pipeline is None
    assert s.emotion_pipeline is None


@pytest.mark.asyncio
async def test_sentiment_analyzer_pipeline_typeerror_paths():
    class TypeErrorPipeline:
        def __call__(self, _text, truncation=False):
            if truncation:
                raise TypeError("no truncation")
            return [{"label": "POSITIVE", "score": 0.9}]

    class EmotionPipeline:
        def __call__(self, _text, truncation=False):
            if truncation:
                raise TypeError("no truncation")
            return [{"label": "joy", "score": 0.8}]

    s = SentimentAnalyzer(model_type="local")
    s.sentiment_pipeline = TypeErrorPipeline()
    s.emotion_pipeline = EmotionPipeline()

    sentiment = await s.analyze_sentiment("Great work")
    emotion = await s.analyze_emotion("This is a long enough sentence")
    assert sentiment["sentiment_label"] == "positive"
    assert emotion["emotion"] == "joy"


@pytest.mark.asyncio
async def test_sentiment_analyzer_batch_pipeline_success():
    class BatchPipeline:
        def __call__(self, _texts, truncation=False):
            return [
                {"label": "POSITIVE", "score": 0.9},
                {"label": "NEGATIVE", "score": 0.8},
            ]

    s = SentimentAnalyzer(model_type="local")
    s.sentiment_pipeline = BatchPipeline()

    results = await s.batch_analyze(["good", "bad"])
    assert results[0]["sentiment_label"] == "positive"
    assert results[1]["sentiment_label"] == "negative"


def test_sentiment_mapping_positive_negative():
    s = SentimentAnalyzer(model_type="local")
    pos = s._map_sentiment({"label": "POSITIVE", "score": 0.9}, "m")
    neg = s._map_sentiment({"label": "NEGATIVE", "score": 0.9}, "m")
    assert pos["sentiment_label"] == "positive"
    assert neg["sentiment_label"] == "negative"


def test_extract_json_with_wrapped_payload():
    s = SentimentAnalyzer(model_type="external")
    content = "Here is data: {\"emotion\": \"joy\", \"confidence_score\": 0.7}"
    data = s._extract_json(content)
    assert data["emotion"] == "joy"


@pytest.mark.asyncio
async def test_alert_monitoring_loop_alert_and_error(monkeypatch):
    service = AlertService(lambda: None)
    called = {"save": 0, "check": 0}

    async def fake_check():
        called["check"] += 1
        if called["check"] == 1:
            return {"alert_type": "high_negative_ratio"}
        raise RuntimeError("boom")

    async def fake_save(_alert):
        called["save"] += 1

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "check_thresholds", fake_check)
    monkeypatch.setattr(service, "save_alert", fake_save)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await service.run_monitoring_loop(check_interval_seconds=0)

    assert called["save"] == 1


@pytest.mark.asyncio
async def test_lifespan_alert_service_failure(monkeypatch):
    class DummyConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run_sync(self, _fn):
            return None

    class DummyEngine:
        def begin(self):
            return DummyConn()

    class DummyRedis:
        async def ping(self):
            return True

        async def close(self):
            return None

    def bad_alert_service(*_args, **_kwargs):
        raise RuntimeError("alert init fail")

    def fake_create_task(coro):
        coro.close()

        class DummyTask:
            def cancel(self):
                return None

        return DummyTask()

    monkeypatch.setattr(main, "engine", DummyEngine())
    monkeypatch.setattr(main.aioredis, "Redis", lambda **_kwargs: DummyRedis())
    monkeypatch.setattr(main, "AlertService", bad_alert_service)
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    async with main.lifespan(main.app):
        assert main.redis_client is not None

    main.redis_client = None


@pytest.mark.asyncio
async def test_get_db_yields_session(monkeypatch):
    class DummyContext:
        async def __aenter__(self):
            return "session"

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: DummyContext())

    agen = main.get_db()
    session = await agen.__anext__()
    assert session == "session"
    await agen.aclose()


@pytest.mark.asyncio
async def test_metrics_broadcaster_handles_exception(monkeypatch):
    class DummyWS:
        async def send_json(self, _message):
            return None

    main.manager.active = [DummyWS()]

    async def fake_collect(_db):
        raise RuntimeError("collect error")

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "_collect_metrics", fake_collect)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await _metrics_broadcaster()


@pytest.mark.asyncio
async def test_health_degraded_status(client, monkeypatch):
    class BadRedis:
        async def ping(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(main, "redis_client", BadRedis())
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_counts_success(client, db_session, monkeypatch):
    now = datetime.datetime.utcnow()
    db_session.add(
        SocialMediaPost(
            post_id="health-counts-1",
            source="reddit",
            content="Great",
            author="tester",
            created_at=now,
        )
    )
    await db_session.commit()

    class GoodRedis:
        async def ping(self):
            return True

    monkeypatch.setattr(main, "redis_client", GoodRedis())
    resp = await client.get("/api/health")
    payload = resp.json()
    assert payload["stats"]["total_posts"] >= 1


@pytest.mark.asyncio
async def test_distribution_cache_read_exception(client, monkeypatch):
    class CacheRedis:
        async def get(self, _key):
            raise RuntimeError("cache read error")

    monkeypatch.setattr(main, "redis_client", CacheRedis())
    resp = await client.get("/api/sentiment/distribution?hours=1")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_distribution_counts_and_emotions(client, db_session, monkeypatch):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="dist-full-1",
        source="twitter",
        content="Love it",
        author="tester",
        created_at=now,
    )
    analysis = SentimentAnalysis(
        post_id="dist-full-1",
        model_name="m",
        sentiment_label="positive",
        confidence_score=0.9,
        emotion="joy",
        analyzed_at=now,
    )
    db_session.add(post)
    db_session.add(analysis)
    await db_session.commit()

    monkeypatch.setattr(main, "redis_client", None)
    resp = await client.get("/api/sentiment/distribution?hours=24&source=twitter")
    payload = resp.json()
    assert payload["distribution"]["positive"] >= 1
    assert payload["top_emotions"].get("joy") >= 1


@pytest.mark.asyncio
async def test_aggregate_with_source_filter(client, db_session):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="agg-source-1",
        source="reddit",
        content="ok",
        author="tester",
        created_at=now,
    )
    analysis = SentimentAnalysis(
        post_id="agg-source-1",
        model_name="m",
        sentiment_label="neutral",
        confidence_score=0.6,
        emotion="neutral",
        analyzed_at=now,
    )
    db_session.add(post)
    db_session.add(analysis)
    await db_session.commit()

    resp = await client.get("/api/sentiment/aggregate?period=hour&source=reddit")
    payload = resp.json()
    assert payload["summary"]["total_posts"] >= 1


@pytest.mark.asyncio
async def test_debug_endpoint_success(client, db_session):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="debug-full-1",
        source="reddit",
        content="ok",
        author="tester",
        created_at=now,
        ingested_at=now,
    )
    analysis = SentimentAnalysis(
        post_id="debug-full-1",
        model_name="m",
        sentiment_label="neutral",
        confidence_score=0.4,
        emotion="neutral",
        analyzed_at=now,
    )
    db_session.add(post)
    db_session.add(analysis)
    await db_session.commit()

    resp = await client.get("/api/debug")
    payload = resp.json()
    assert payload["total_posts"] >= 1


@pytest.mark.asyncio
async def test_sentiment_analyzer_pipeline_exception_paths():
    class ErrorPipeline:
        def __call__(self, _text, truncation=False):
            raise RuntimeError("pipeline error")

    s = SentimentAnalyzer(model_type="local")
    s.sentiment_pipeline = ErrorPipeline()
    s.emotion_pipeline = ErrorPipeline()

    sentiment = await s.analyze_sentiment("I love this")
    emotion = await s.analyze_emotion("This is a long enough sentence")
    assert sentiment["sentiment_label"] in {"positive", "negative", "neutral"}
    assert emotion["emotion"] == "neutral"


@pytest.mark.asyncio
async def test_sentiment_analyzer_batch_pipeline_exception():
    class ErrorPipeline:
        def __call__(self, _texts, truncation=False):
            raise RuntimeError("batch error")

    s = SentimentAnalyzer(model_type="local")
    s.sentiment_pipeline = ErrorPipeline()
    results = await s.batch_analyze(["ok", "ok"])
    assert len(results) == 2


def test_sentiment_mapping_unknown_label():
    s = SentimentAnalyzer(model_type="local")
    neutral = s._map_sentiment({"label": "mixed", "score": 0.9}, "m")
    assert neutral["sentiment_label"] == "neutral"


def test_rule_based_sentiment_tie():
    s = SentimentAnalyzer(model_type="local")
    result = s._rule_based_sentiment("love hate")
    assert result["sentiment_label"] == "neutral"


@pytest.mark.asyncio
async def test_external_request_exception(monkeypatch):
    s = SentimentAnalyzer(model_type="external")
    s.external_api_key = "key"
    s.provider = "groq"

    async def bad_post(_url, headers=None, json=None):
        raise RuntimeError("request fail")

    monkeypatch.setattr(s._client, "post", bad_post)
    result = await s._external_request({"model": "x"})
    assert result == {}


def test_extract_json_invalid_wrapped_payload():
    s = SentimentAnalyzer(model_type="external")
    data = s._extract_json("{not json}")
    assert data == {}


@pytest.mark.asyncio
async def test_alert_monitoring_loop_exception_only(monkeypatch):
    service = AlertService(lambda: None)

    async def bad_check():
        raise RuntimeError("boom")

    async def fake_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "check_thresholds", bad_check)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await service.run_monitoring_loop(check_interval_seconds=0)


def test_parse_dt_variants():
    from backend.services.alerting import _parse_dt

    assert _parse_dt(None) is None
    now = datetime.datetime.utcnow()
    assert _parse_dt(now) == now


@pytest.mark.asyncio
async def test_alert_save_refresh(db_session):
    service = AlertService(lambda: db_session)
    alert_id = await service.save_alert(
        {
            "alert_type": "high_negative_ratio",
            "threshold": 2.0,
            "actual_ratio": 3.0,
            "window_start": datetime.datetime.utcnow().isoformat(),
            "window_end": datetime.datetime.utcnow().isoformat(),
            "post_count": 1,
            "metrics": {"total_count": 1},
        }
    )
    assert isinstance(alert_id, int)


@pytest.mark.asyncio
async def test_health_direct_counts_and_degraded(monkeypatch):
    class DummyResult:
        def __init__(self, value):
            self._value = value

        def scalar(self):
            return self._value

    class DummyDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return DummyResult(None)
            if self.calls == 2:
                return DummyResult(2)
            if self.calls == 3:
                return DummyResult(1)
            return DummyResult(1)

    class BadRedis:
        async def ping(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(main, "redis_client", BadRedis())
    response = await main.health(db=DummyDB())
    payload = json.loads(response.body)
    assert payload["status"] == "degraded"
    assert payload["stats"]["total_posts"] == 2


@pytest.mark.asyncio
async def test_get_posts_direct_with_analysis(db_session):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="post-direct-1",
        source="reddit",
        content="Nice",
        author="tester",
        created_at=now,
    )
    analysis = SentimentAnalysis(
        post_id="post-direct-1",
        model_name="m",
        sentiment_label="positive",
        confidence_score=0.9,
        emotion="joy",
        analyzed_at=now,
    )
    db_session.add(post)
    db_session.add(analysis)
    await db_session.commit()

    payload = await main.get_posts(
        limit=5,
        offset=0,
        source="reddit",
        sentiment="positive",
        start_date=now - datetime.timedelta(hours=1),
        end_date=now + datetime.timedelta(hours=1),
        db=db_session,
    )
    assert payload["posts"]
    assert payload["posts"][0]["sentiment"]["label"] == "positive"


@pytest.mark.asyncio
async def test_distribution_direct_counts(db_session, monkeypatch):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="dist-direct-1",
        source="reddit",
        content="Great",
        author="tester",
        created_at=now,
    )
    analysis = SentimentAnalysis(
        post_id="dist-direct-1",
        model_name="m",
        sentiment_label="positive",
        confidence_score=0.9,
        emotion="joy",
        analyzed_at=now,
    )
    db_session.add(post)
    db_session.add(analysis)
    await db_session.commit()

    monkeypatch.setattr(main, "redis_client", None)
    payload = await main.sentiment_distribution(hours=24, source="reddit", db=db_session)
    assert payload["distribution"]["positive"] >= 1
    assert payload["top_emotions"]["joy"] >= 1


@pytest.mark.asyncio
async def test_distribution_cache_set_exception(db_session):
    class CacheRedis:
        def __init__(self):
            self.set_called = False

        async def get(self, _key):
            return None

        async def set(self, _key, _value, ex=None):
            self.set_called = True
            raise RuntimeError("set failed")

    cache = CacheRedis()
    main.redis_client = cache
    payload = await main.sentiment_distribution(hours=24, source=None, db=db_session)
    assert payload["cached"] is False
    assert cache.set_called is True
    main.redis_client = None


@pytest.mark.asyncio
async def test_cache_distribution_payload_success():
    class CacheRedis:
        def __init__(self):
            self.set_called = False

        async def set(self, _key, _value, ex=None):
            self.set_called = True

    cache = CacheRedis()
    main.redis_client = cache
    await _cache_distribution_payload("cache-key", {"ok": True})
    assert cache.set_called is True
    main.redis_client = None


@pytest.mark.asyncio
async def test_cache_distribution_payload_exception():
    class CacheRedis:
        async def set(self, _key, _value, ex=None):
            raise RuntimeError("cache fail")

    main.redis_client = CacheRedis()
    await _cache_distribution_payload("cache-key", {"ok": True})
    main.redis_client = None


@pytest.mark.asyncio
async def test_aggregate_direct_minute(db_session):
    now = datetime.datetime.utcnow().replace(second=22, microsecond=0)
    analysis = SentimentAnalysis(
        post_id="agg-direct-1",
        model_name="m",
        sentiment_label="neutral",
        confidence_score=0.5,
        emotion="neutral",
        analyzed_at=now,
    )
    db_session.add(analysis)
    await db_session.commit()

    payload = await main.sentiment_aggregate(
        period="minute",
        start_date=now - datetime.timedelta(hours=1),
        end_date=now + datetime.timedelta(hours=1),
        source=None,
        db=db_session,
    )
    assert payload["data"]


@pytest.mark.asyncio
async def test_debug_status_direct(db_session):
    now = datetime.datetime.utcnow()
    post = SocialMediaPost(
        post_id="debug-direct-1",
        source="reddit",
        content="ok",
        author="tester",
        created_at=now,
        ingested_at=now,
    )
    analysis = SentimentAnalysis(
        post_id="debug-direct-1",
        model_name="m",
        sentiment_label="neutral",
        confidence_score=0.4,
        emotion="neutral",
        analyzed_at=now,
    )
    db_session.add(post)
    db_session.add(analysis)
    await db_session.commit()

    payload = await main.debug_status(db=db_session)
    assert payload["total_posts"] >= 1


@pytest.mark.asyncio
async def test_alert_save_refresh_with_dummy_db():
    class DummyDB:
        def __init__(self):
            self.refreshed = False

        def add(self, _obj):
            return None

        async def commit(self):
            return None

        async def refresh(self, obj):
            obj.id = 1
            self.refreshed = True

    class DummyContext:
        async def __aenter__(self):
            return DummyDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    service = AlertService(lambda: DummyContext())
    alert_id = await service.save_alert(
        {
            "alert_type": "high_negative_ratio",
            "threshold": 2.0,
            "actual_ratio": 3.0,
            "window_start": datetime.datetime.utcnow().isoformat(),
            "window_end": datetime.datetime.utcnow().isoformat(),
            "post_count": 1,
            "metrics": {"total_count": 1},
        }
    )
    assert alert_id == 1
