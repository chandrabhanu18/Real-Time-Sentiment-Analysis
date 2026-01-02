import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert "status" in r.json()


@pytest.mark.asyncio
async def test_posts_endpoint_empty(client):
    r = await client.get("/api/posts")
    assert r.status_code == 200
    j = r.json()
    assert isinstance(j, dict)
    assert "posts" in j
