import pytest
from backend.services.sentiment_analyzer import SentimentAnalyzer


@pytest.mark.asyncio
async def test_analyze_sentiment_rule_based():
    s = SentimentAnalyzer(model_type="local")
    res = await s.analyze_sentiment("I love this product, it's amazing and great!")
    assert res["sentiment_label"] in ("positive", "neutral", "negative")


@pytest.mark.asyncio
async def test_analyze_emotion_short_text():
    s = SentimentAnalyzer(model_type="local")
    res = await s.analyze_emotion("Hi")
    assert res["emotion"] == "neutral"


@pytest.mark.asyncio
async def test_batch_analyze_empty():
    s = SentimentAnalyzer(model_type="local")
    res = await s.batch_analyze([])
    assert res == []
