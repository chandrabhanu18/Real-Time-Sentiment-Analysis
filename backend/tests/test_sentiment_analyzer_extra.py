import pytest

from backend.services.sentiment_analyzer import SentimentAnalyzer


class DummyPipeline:
    def __init__(self, outputs):
        self.outputs = outputs

    def __call__(self, text):
        return self.outputs


@pytest.mark.asyncio
async def test_local_pipeline_sentiment_mapping():
    s = SentimentAnalyzer(model_type="local")
    # inject a dummy pipeline that returns a positive label
    s.sentiment_pipeline = DummyPipeline([{"label": "POSITIVE", "score": 0.95}])
    res = await s.analyze_sentiment("I love this")
    assert res["sentiment_label"] == "positive"
    assert res["confidence_score"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_local_pipeline_emotion_mapping():
    s = SentimentAnalyzer(model_type="local")
    s.emotion_pipeline = DummyPipeline([{"label": "joy", "score": 0.8}])
    res = await s.analyze_emotion("I am very happy today!")
    assert res["emotion"] == "joy"
    assert res["confidence_score"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_batch_analyze_handles_empty_and_errors():
    s = SentimentAnalyzer(model_type="local")
    # empty input returns []
    assert await s.batch_analyze([]) == []

    # simulate analyze_sentiment raising for one item
    async def bad_analyze(text):
        raise RuntimeError("boom")

    s.analyze_sentiment = bad_analyze
    res = await s.batch_analyze(["x"])
    assert isinstance(res, list)
    assert res[0]["sentiment_label"] is None
