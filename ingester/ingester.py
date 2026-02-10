import asyncio
import os
import random
import time
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from faker import Faker


fake = Faker()

POSITIVE_TEMPLATES = [
    "I absolutely love {product}! It is amazing and exceeded my expectations.",
    "{product} is great. Best experience I've had this year.",
    "So happy with {product}. Brilliant quality and fantastic support!",
    "{product} just made my day. Wonderful and delightful to use.",
]

NEGATIVE_TEMPLATES = [
    "Very disappointed with {product}. Terrible experience overall.",
    "{product} is the worst purchase I've made. Awful quality.",
    "I hate how {product} performs. It is broken and frustrating.",
    "Regret buying {product}. Not recommended at all.",
]

NEUTRAL_TEMPLATES = [
    "Just tried {product} for the first time.",
    "Received {product} today and set it up.",
    "Using {product} now. Testing the features.",
    "Saw an ad for {product}. Curious about it.",
]

PRODUCTS = [
    "iPhone 16",
    "Tesla Model 3",
    "ChatGPT",
    "Netflix",
    "Amazon Prime",
    "PlayStation 6",
    "Meta Quest",
    "OpenAI API",
]

SOURCES = ["reddit", "twitter", "threads", "hackernews", "youtube"]


class DataIngester:
    """
    Publishes simulated social media posts to Redis Stream.
    """

    def __init__(self, redis_client, stream_name: str, posts_per_minute: int = 60):
        self.redis = redis_client
        self.stream = stream_name
        self.rate = posts_per_minute

    def generate_post(self) -> dict:
        sentiment_bucket = random.choices(
            ["positive", "neutral", "negative"],
            weights=[0.4, 0.3, 0.3],
        )[0]

        if sentiment_bucket == "positive":
            template = random.choice(POSITIVE_TEMPLATES)
        elif sentiment_bucket == "negative":
            template = random.choice(NEGATIVE_TEMPLATES)
        else:
            template = random.choice(NEUTRAL_TEMPLATES)

        product = random.choice(PRODUCTS)
        content = template.format(product=product)
        return {
            "post_id": f"post_{int(time.time() * 1000)}_{random.randint(1000,9999)}",
            "source": random.choice(SOURCES),
            "content": content,
            "author": fake.user_name(),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    async def publish_post(self, post_data: dict) -> bool:
        try:
            await self.redis.xadd(self.stream, post_data)
            return True
        except Exception:
            return False

    async def start(self, duration_seconds: Optional[int] = None):
        interval = 60 / max(self.rate, 1)
        start_ts = time.time()

        while True:
            if duration_seconds and time.time() - start_ts > duration_seconds:
                break
            post = self.generate_post()
            published = await self.publish_post(post)
            if published:
                print(f"Published {post['post_id']} -> {post['source']}", flush=True)
            await asyncio.sleep(interval)


async def main():
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    stream_name = os.getenv("REDIS_STREAM_NAME", "social_posts_stream")
    posts_per_minute = int(os.getenv("INGESTER_POSTS_PER_MINUTE", "60"))

    redis_client = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)

    ingester = DataIngester(redis_client, stream_name, posts_per_minute)
    try:
        await ingester.start()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    asyncio.run(main())
