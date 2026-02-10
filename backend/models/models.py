from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class SocialMediaPost(Base):
    __tablename__ = "social_media_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(String(255), unique=True, index=True, nullable=False)
    source = Column(String(50), index=True)
    content = Column(Text)
    author = Column(String(255))
    created_at = Column(DateTime)
    ingested_at = Column(DateTime, server_default=func.now())


class SentimentAnalysis(Base):
    __tablename__ = "sentiment_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(String(255), ForeignKey("social_media_posts.post_id", ondelete="CASCADE"), index=True)
    model_name = Column(String(100))
    sentiment_label = Column(String(20), index=True)
    confidence_score = Column(Float)
    emotion = Column(String(50), nullable=True)
    analyzed_at = Column(DateTime, server_default=func.now(), index=True)


class SentimentAlert(Base):
    __tablename__ = "sentiment_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(String(50))
    threshold_value = Column(Float)
    actual_value = Column(Float)
    window_start = Column(DateTime)
    window_end = Column(DateTime)
    post_count = Column(Integer)
    triggered_at = Column(DateTime, server_default=func.now(), index=True)
    details = Column(JSON)


# Indexes for frequently queried columns
Index("idx_social_created_at", SocialMediaPost.created_at)
Index("idx_sentiment_analyzed_at", SentimentAnalysis.analyzed_at)
Index("idx_alerts_triggered_at", SentimentAlert.triggered_at)

