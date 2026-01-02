import pytest
import datetime
from backend.models.models import SentimentAnalysis, SocialMediaPost


@pytest.mark.asyncio
async def test_aggregate_and_alerts(client, db_session):
    # create posts and analyses
    now = datetime.datetime.utcnow()
    posts = []
    for i in range(5):
        p = SocialMediaPost(post_id=f"p{i}", source="twitter", content="test", author="u", created_at=now - datetime.timedelta(minutes=i))
        db_session.add(p)
        posts.append(p)
    await db_session.commit()

    # add sentiment analyses (more negatives to trigger alert threshold)
    analyses = []
    for i in range(12):
        label = "negative" if i < 9 else "positive"
        a = SentimentAnalysis(post_id=f"p{ i%5 }", model_name="m", sentiment_label=label, confidence_score=0.9, emotion="anger", analyzed_at=now - datetime.timedelta(minutes=i))
        db_session.add(a)
        analyses.append(a)
    await db_session.commit()

    # test aggregate endpoint
    r = await client.get("/api/sentiment/aggregate?period=hour")
    assert r.status_code == 200
    j = r.json()
    assert "data" in j and "summary" in j

    # test distribution endpoint
    r2 = await client.get("/api/sentiment/distribution?hours=24")
    assert r2.status_code == 200
    dist = r2.json()
    assert "distribution" in dist
