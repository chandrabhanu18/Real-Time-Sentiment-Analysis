import datetime
import pytest

from backend.models.models import SocialMediaPost, SentimentAnalysis


@pytest.mark.asyncio
async def test_end_to_end_flow(client, db_session):
  now = datetime.datetime.utcnow()
  post = SocialMediaPost(
    post_id="integration_1",
    source="reddit",
    content="I love this new product!",
    author="tester",
    created_at=now,
  )
  db_session.add(post)
  await db_session.commit()

  analysis = SentimentAnalysis(
    post_id="integration_1",
    model_name="distilbert-base-uncased-finetuned-sst-2-english",
    sentiment_label="positive",
    confidence_score=0.9,
    emotion="joy",
    analyzed_at=now,
  )
  db_session.add(analysis)
  await db_session.commit()

  resp = await client.get("/api/posts?limit=5&sentiment=positive")
  assert resp.status_code == 200
  payload = resp.json()
  assert payload["total"] >= 1
  assert payload["posts"][0]["sentiment"]["label"] == "positive"

  dist = await client.get("/api/sentiment/distribution?hours=24")
  assert dist.status_code == 200
  assert "percentages" in dist.json()
