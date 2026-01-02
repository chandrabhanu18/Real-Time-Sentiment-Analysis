-- ===============================
-- Social Media Posts
-- ===============================
CREATE TABLE IF NOT EXISTS social_media_posts (
    id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    author TEXT,
    created_at TIMESTAMP NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_posts_created_at
ON social_media_posts (created_at);

CREATE INDEX IF NOT EXISTS idx_posts_source
ON social_media_posts (source);


-- ===============================
-- Sentiment Analysis Results
-- ===============================
CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id SERIAL PRIMARY KEY,
    post_id UUID NOT NULL,
    model_name TEXT NOT NULL,
    sentiment_label TEXT NOT NULL,
    confidence_score FLOAT,
    emotion TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_post
        FOREIGN KEY (post_id)
        REFERENCES social_media_posts (id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sentiment_post_id
ON sentiment_analysis (post_id);

CREATE INDEX IF NOT EXISTS idx_sentiment_label
ON sentiment_analysis (sentiment_label);


-- ===============================
-- Sentiment Alerts
-- ===============================
CREATE TABLE IF NOT EXISTS sentiment_alerts (
    id SERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,
    threshold_value FLOAT NOT NULL,
    actual_value FLOAT NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    post_count INT NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at
ON sentiment_alerts (triggered_at);
