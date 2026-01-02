import os
from typing import List, Dict, Any

try:
    from transformers import pipeline
    HAS_TRANSFORMERS = True
except Exception:
    pipeline = None  # type: ignore
    HAS_TRANSFORMERS = False


class SentimentAnalyzer:
    def __init__(self, model_type: str = "local", model_name: str = None):
        self.model_type = model_type
        self.model_name = model_name or os.getenv("HUGGINGFACE_MODEL")
        self.emotion_model_name = os.getenv("EMOTION_MODEL")
        self.sentiment_pipeline: Any = None
        self.emotion_pipeline: Any = None

        if self.model_type == "local" and HAS_TRANSFORMERS:
            try:
                self.sentiment_pipeline = pipeline("sentiment-analysis", model=self.model_name)
            except Exception:
                self.sentiment_pipeline = None

            try:
                self.emotion_pipeline = pipeline("text-classification", model=self.emotion_model_name)
            except Exception:
                self.emotion_pipeline = None

    async def analyze_sentiment(self, text: str) -> Dict:
        if not text:
            raise ValueError("Empty text")

        if self.model_type == "local" and self.sentiment_pipeline:
            out = self.sentiment_pipeline(text[:512])
            label = out[0]["label"].lower()
            score = float(out[0].get("score", 0.0))
            if label == "neutral":
                label = "neutral"
            elif label in ("positive", "pos", "5 stars"):
                label = "positive"
            elif label in ("negative", "neg", "1 star"):
                label = "negative"
            return {"sentiment_label": label, "confidence_score": score, "model_name": self.model_name}

        # fallback simple rule-based
        lower = text.lower()
        if any(w in lower for w in ["love", "amazing", "great", "happy", "excited"]):
            return {"sentiment_label": "positive", "confidence_score": 0.7, "model_name": "rule-based"}
        if any(w in lower for w in ["hate", "terrible", "disappointed", "bad"]):
            return {"sentiment_label": "negative", "confidence_score": 0.7, "model_name": "rule-based"}
        return {"sentiment_label": "neutral", "confidence_score": 0.5, "model_name": "rule-based"}

    async def analyze_emotion(self, text: str) -> Dict:
        if not text:
            raise ValueError("Empty text")
        if len(text) < 10:
            return {"emotion": "neutral", "confidence_score": 0.5, "model_name": "heuristic"}

        if self.model_type == "local" and self.emotion_pipeline:
            out = self.emotion_pipeline(text[:512])
            label = out[0]["label"].lower()
            score = float(out[0].get("score", 0.0))
            # map to allowed set
            mapping = {"joy": "joy", "anger": "anger", "sadness": "sadness", "fear": "fear", "surprise": "surprise"}
            emotion = mapping.get(label, "neutral")
            return {"emotion": emotion, "confidence_score": score, "model_name": self.emotion_model_name}

        # fallback heuristic
        lower = text.lower()
        if any(w in lower for w in ["love", "happy", "joy", "excited"]):
            return {"emotion": "joy", "confidence_score": 0.7, "model_name": "heuristic"}
        if any(w in lower for w in ["angry", "anger", "furious"]):
            return {"emotion": "anger", "confidence_score": 0.7, "model_name": "heuristic"}
        if any(w in lower for w in ["sad", "sadness", "depressed"]):
            return {"emotion": "sadness", "confidence_score": 0.7, "model_name": "heuristic"}
        return {"emotion": "neutral", "confidence_score": 0.5, "model_name": "heuristic"}

    async def batch_analyze(self, texts: List[str]) -> List[Dict]:
        if not texts:
            return []
        results = []
        for t in texts:
            try:
                res = await self.analyze_sentiment(t)
            except Exception:
                res = {"sentiment_label": None, "confidence_score": 0.0, "model_name": None}
            results.append(res)
        return results
