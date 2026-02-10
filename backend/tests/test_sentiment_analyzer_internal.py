import pytest

from backend.services.sentiment_analyzer import SentimentAnalyzer


@pytest.mark.asyncio
async def test_rule_based_and_extract_json():
    s = SentimentAnalyzer(model_type="local")
    res = await s.analyze_sentiment("This is the worst experience")
    assert res["sentiment_label"] in ("positive", "negative", "neutral")

    blob = "prefix {\"sentiment_label\": \"positive\", \"confidence_score\": 0.9} suffix"
    extracted = s._extract_json(blob)
    assert extracted.get("sentiment_label") == "positive"