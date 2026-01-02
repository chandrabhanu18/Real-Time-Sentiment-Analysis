import redis
import psycopg2
import os
import json
from datetime import datetime
import time

# lazy import transformers (optional)
try:
    from transformers import pipeline
except Exception:
    pipeline = None
from datetime import datetime
import os
import json

# ---------------- Redis config ----------------
REDIS_HOST = "redis"
REDIS_PORT = 6379
STREAM_NAME = "social_posts_stream"
GROUP_NAME = "sentiment_workers"
CONSUMER_NAME = "worker-1"

# ---------------- Postgres config ----------------
# ---------------- Postgres config ----------------
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "sentiment_db")
DB_USER = os.getenv("POSTGRES_USER", "sentiment_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "sentiment_password")

# ---------------- Connections ----------------
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

conn = psycopg2.connect(
    host=DB_HOST,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
conn.autocommit = True
cursor = conn.cursor()

print("WORKER STARTED (DB CONNECTED)", flush=True)

# ---------------- Redis Consumer Group ----------------
try:
    r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
except redis.exceptions.ResponseError:
    pass

# Wait for DB tables to exist before processing messages
def wait_for_tables(cursor, initial_timeout=60, retry_interval=5):
    """
    Wait until the `social_media_posts` table exists.
    First wait up to `initial_timeout` seconds, then keep retrying every `retry_interval` seconds.
    This helps avoid race conditions on cold starts where the backend creates tables.
    """
    start = time.time()
    tried = 0
    while True:
        try:
            cursor.execute("SELECT 1 FROM social_media_posts LIMIT 1")
            print("DB tables detected - proceeding with worker.", flush=True)
            return True
        except Exception as e:
            tried += 1
            elapsed = time.time() - start
            if elapsed < initial_timeout:
                # initial rapid retry
                time.sleep(1)
            else:
                # longer-term retry with informative logging
                print(f"Waiting for DB tables (attempt {tried})... still not available: {e}", flush=True)
                time.sleep(retry_interval)

wait_for_tables(cursor, initial_timeout=60, retry_interval=5)

# ---------------- AI Models ----------------
if pipeline is not None:
    try:
        sentiment_model = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
        )
    except Exception:
        sentiment_model = None

    try:
        emotion_model = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            return_all_scores=False,
        )
    except Exception:
        emotion_model = None
else:
    sentiment_model = None
    emotion_model = None

# ---------------- Main Loop ----------------
while True:
    messages = r.xreadgroup(
        GROUP_NAME,
        CONSUMER_NAME,
        {STREAM_NAME: ">"},
        count=1,
        block=5000
    )

    if not messages:
        continue

    for _, msgs in messages:
        for msg_id, data in msgs:
            try:
                post_id = data["post_id"]
                content = data["content"]

                # -------- Sentiment (model or fallback) --------
                if sentiment_model:
                    try:
                        sentiment_result = sentiment_model(content)[0]
                        sentiment = sentiment_result.get("label", "neutral").lower()
                        confidence = float(sentiment_result.get("score", 0.0))
                    except Exception:
                        sentiment = "neutral"
                        confidence = 0.0
                else:
                    # simple rule-based fallback
                    lc = content.lower()
                    if any(w in lc for w in ("good", "great", "happy", "love", "nice", "excellent")):
                        sentiment = "positive"
                        confidence = 0.6
                    elif any(w in lc for w in ("bad", "sad", "hate", "terrible", "awful")):
                        sentiment = "negative"
                        confidence = 0.6
                    else:
                        sentiment = "neutral"
                        confidence = 0.5

                # -------- Emotion (model or fallback) --------
                if emotion_model:
                    try:
                        emotion_result = emotion_model(content)[0]
                        emotion = emotion_result.get("label", "neutral").lower()
                    except Exception:
                        emotion = "neutral"
                else:
                    emotion = "neutral"

                # -------- Insert or update post using post_id --------
                cursor.execute(
                    """
                    INSERT INTO social_media_posts
                    (post_id, source, content, author, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (post_id) DO UPDATE SET ingested_at = NOW()
                    """,
                    (
                        post_id,
                        data.get("source"),
                        content,
                        data.get("author"),
                        data.get("created_at"),
                    ),
                )

                # -------- Insert analysis --------
                cursor.execute(
                    """
                    INSERT INTO sentiment_analysis
                    (post_id, model_name, sentiment_label, confidence_score, emotion, analyzed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        post_id,
                        "distilbert-fallback" if not sentiment_model else "distilbert-sst2 + roberta-emotion",
                        sentiment,
                        confidence,
                        emotion,
                        datetime.utcnow(),
                    ),
                )

                r.xack(STREAM_NAME, GROUP_NAME, msg_id)

                # publish a lightweight event for websocket/backend
                event = {
                    "type": "new_post",
                    "data": {
                        "post_id": post_id,
                        "content": content[:200],
                        "source": data.get("source"),
                        "sentiment_label": sentiment,
                        "confidence_score": confidence,
                        "emotion": emotion,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
                try:
                    r.publish("sentiment_channel", json.dumps(event))
                except Exception:
                    pass

                print(f"PROCESSED {post_id} → {sentiment} | {emotion}", flush=True)

            except Exception as e:
                print("ERROR PROCESSING MESSAGE:", e, flush=True)
