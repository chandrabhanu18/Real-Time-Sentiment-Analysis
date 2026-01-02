import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import SentimentAlert, SentimentAnalysis


class AlertService:
    def __init__(self, db_session_maker, redis_client=None):
        self.db_session_maker = db_session_maker
        self.redis = redis_client
        self.threshold = float(os.getenv("ALERT_NEGATIVE_RATIO_THRESHOLD", "2.0"))
        self.window_minutes = int(os.getenv("ALERT_WINDOW_MINUTES", "5"))
        self.min_posts = int(os.getenv("ALERT_MIN_POSTS", "10"))

    async def check_thresholds(self) -> Optional[dict]:
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=self.window_minutes)

        async with self.db_session_maker() as db:
            stmt = select(SentimentAnalysis).where(SentimentAnalysis.analyzed_at >= window_start)
            rows = (await db.execute(stmt)).scalars().all()

            pos = sum(1 for r in rows if r.sentiment_label == "positive")
            neg = sum(1 for r in rows if r.sentiment_label == "negative")
            neu = sum(1 for r in rows if r.sentiment_label == "neutral")
            total = pos + neg + neu

            if total < self.min_posts:
                return None

            ratio = (neg / pos) if pos > 0 else float('inf')
            if ratio > self.threshold:
                alert = {
                    "alert_triggered": True,
                    "alert_type": "high_negative_ratio",
                    "threshold": self.threshold,
                    "actual_ratio": ratio,
                    "window_minutes": self.window_minutes,
                    "metrics": {"positive_count": pos, "negative_count": neg, "neutral_count": neu, "total_count": total},
                    "timestamp": now.isoformat(),
                }
                return alert

            return None

    async def save_alert(self, alert_data: dict) -> int:
        async with self.db_session_maker() as db:
            a = SentimentAlert(
                alert_type=alert_data.get("alert_type"),
                threshold_value=alert_data.get("threshold"),
                actual_value=alert_data.get("actual_ratio"),
                window_start=alert_data.get("window_start"),
                window_end=alert_data.get("window_end"),
                post_count=alert_data.get("metrics", {}).get("total_count", 0),
                details=alert_data,
            )
            db.add(a)
            await db.commit()
            await db.refresh(a)
            return a.id

    async def run_monitoring_loop(self, check_interval_seconds: int = 60):
        while True:
            try:
                alert = await self.check_thresholds()
                if alert:
                    # annotate window times
                    now = datetime.utcnow()
                    alert["window_start"] = (now - timedelta(minutes=self.window_minutes)).isoformat()
                    alert["window_end"] = now.isoformat()
                    await self.save_alert(alert)
                    print("ALERT TRIGGERED:", alert, flush=True)
            except Exception as e:
                print("Error in alerting loop:", e, flush=True)
            await asyncio.sleep(check_interval_seconds)
