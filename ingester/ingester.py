import time
import uuid
from datetime import datetime
import redis
from faker import Faker
import os

fake = Faker()

# Redis config
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_NAME = os.getenv("REDIS_STREAM_NAME", "social_posts_stream")
POSTS_PER_MINUTE = int(os.getenv("POSTS_PER_MINUTE", "20"))

print("INGESTER BOOTED", flush=True)

def generate_post():
    # Send ONE guaranteed joy post (demo purpose)
    if not hasattr(generate_post, "sent_demo"):
        generate_post.sent_demo = True
        return {
            "post_id": str(uuid.uuid4()),
            "source": "twitter",
            "content": "I am extremely happy and excited about this product!",
            "author": "demo_user",
            "created_at": datetime.utcnow().isoformat()
        }

    # Normal fake post with varied sentiment
    templates = {
        "positive": [
            "I absolutely love {product}!",
            "This is amazing, {product} exceeded expectations!",
            "So happy with {product}, highly recommend it."
        ],
        "neutral": [
            "Just tried {product} today.",
            "Received {product} today.",
            "Using {product} for the first time."
        ],
        "negative": [
            "Very disappointed with {product}.",
            "Terrible experience with {product}.",
            "Would not recommend {product}."
        ]
    }

    product = fake.word().capitalize()
    sentiment_choice = fake.random_choices(elements=["positive","neutral","negative"], length=1)[0]
    content = fake.random_element(templates[sentiment_choice]).format(product=product)

    return {
        "post_id": str(uuid.uuid4()),
        "source": fake.random_element(["twitter", "reddit", "facebook"]),
        "content": content,
        "author": fake.user_name(),
        "created_at": datetime.utcnow().isoformat()
    }


def connect_redis(retries=5, delay=2):
    for i in range(retries):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            return r
        except Exception as e:
            print(f"Redis connect failed ({i+1}/{retries}): {e}", flush=True)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("Unable to connect to Redis")


def run():
    r = connect_redis()
    interval = 60.0 / POSTS_PER_MINUTE if POSTS_PER_MINUTE > 0 else 1.0
    try:
        while True:
            post = generate_post()
            try:
                r.xadd(STREAM_NAME, post)
                print("PUBLISHED:", post, flush=True)
            except Exception as e:
                print("Failed to publish post:", e, flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Ingester stopped", flush=True)


if __name__ == '__main__':
    run()
