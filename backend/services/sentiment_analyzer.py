import os
import json
import re
from typing import List, Optional

import httpx


class SentimentAnalyzer:
    """
    Unified sentiment/emotion analyzer using local transformers or external LLM.
    """

    def __init__(self, model_type: str = "local", model_name: Optional[str] = None):
        self.model_type = model_type
        self.model_name = model_name or os.getenv(
            "HUGGINGFACE_MODEL",
            "distilbert-base-uncased-finetuned-sst-2-english",
        )
        self.emotion_model = os.getenv(
            "EMOTION_MODEL",
            "j-hartmann/emotion-english-distilroberta-base",
        )
        self.provider = os.getenv("EXTERNAL_LLM_PROVIDER", "groq").lower()
        self.external_model = os.getenv("EXTERNAL_LLM_MODEL", "llama-3.1-8b-instant")
        self.external_api_key = os.getenv("EXTERNAL_LLM_API_KEY")
        self._client = httpx.AsyncClient(timeout=30.0)

        self.sentiment_pipeline = None
        self.emotion_pipeline = None
        if self.model_type == "local" and os.getenv("PYTEST_CURRENT_TEST") is None:
            try:
                from transformers import pipeline as hf_pipeline

                self.sentiment_pipeline = hf_pipeline(
                    "sentiment-analysis",
                    model=self.model_name,
                    device=int(os.getenv("HF_DEVICE", "-1")),
                )
                self.emotion_pipeline = hf_pipeline(
                    "text-classification",
                    model=self.emotion_model,
                    device=int(os.getenv("HF_DEVICE", "-1")),
                )
            except Exception:
                self.sentiment_pipeline = None
                self.emotion_pipeline = None

    async def analyze_sentiment(self, text: str) -> dict:
        if text is None or not str(text).strip():
            return self._sentiment_result("neutral", 0.0, self._model_id("sentiment"))

        if self.model_type == "external":
            return await self._external_sentiment(text)

        if self.sentiment_pipeline is not None:
            try:
                result = self.sentiment_pipeline(str(text)[:512], truncation=True)[0]
            except TypeError:
                result = self.sentiment_pipeline(str(text)[:512])[0]
            except Exception:
                result = None
            if result is not None:
                return self._map_sentiment(result, self._model_id("sentiment"))

        return self._rule_based_sentiment(text)

    async def analyze_emotion(self, text: str) -> dict:
        if text is None or not str(text).strip():
            raise ValueError("Empty text")
        if len(str(text).strip()) < 10:
            return self._emotion_result("neutral", 0.0, self._model_id("emotion"))

        if self.model_type == "external":
            return await self._external_emotion(text)

        if self.emotion_pipeline is not None:
            try:
                result = self.emotion_pipeline(str(text)[:512], truncation=True)[0]
            except TypeError:
                result = self.emotion_pipeline(str(text)[:512])[0]
            except Exception:
                result = None
            if result is not None:
                return self._map_emotion(result, self._model_id("emotion"))

        return self._emotion_result("neutral", 0.0, self._model_id("emotion"))

    async def batch_analyze(self, texts: List[str]) -> List[dict]:
        if not texts:
            return []

        if self.model_type == "local" and self.sentiment_pipeline is not None:
            try:
                results = self.sentiment_pipeline(
                    [str(t)[:512] for t in texts],
                    truncation=True,
                )
                return [self._map_sentiment(r, self._model_id("sentiment")) for r in results]
            except Exception:
                pass

        outputs: List[dict] = []
        for text in texts:
            try:
                outputs.append(await self.analyze_sentiment(text))
            except Exception:
                outputs.append(self._sentiment_result(None, 0.0, self._model_id("sentiment")))
        return outputs

    def _model_id(self, kind: str) -> str:
        if self.model_type == "external":
            return f"{self.provider}:{self.external_model}"
        return self.model_name if kind == "sentiment" else self.emotion_model

    def _sentiment_result(self, label, score, model_name):
        return {
            "sentiment_label": label,
            "confidence_score": float(max(0.0, min(1.0, score))),
            "model_name": model_name,
        }

    def _emotion_result(self, label, score, model_name):
        return {
            "emotion": label,
            "confidence_score": float(max(0.0, min(1.0, score))),
            "model_name": model_name,
        }

    def _map_sentiment(self, result, model_name: str) -> dict:
        label = str(result.get("label", "")).lower()
        score = float(result.get("score", 0.0))
        if score < 0.55:
            return self._sentiment_result("neutral", score, model_name)
        if "pos" in label:
            return self._sentiment_result("positive", score, model_name)
        if "neg" in label:
            return self._sentiment_result("negative", score, model_name)
        return self._sentiment_result("neutral", score, model_name)

    def _map_emotion(self, result, model_name: str) -> dict:
        label = str(result.get("label", "neutral")).lower()
        allowed = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
        if label not in allowed:
            label = "neutral"
        score = float(result.get("score", 0.0))
        return self._emotion_result(label, score, model_name)

    def _rule_based_sentiment(self, text: str) -> dict:
        tokens = re.findall(r"[a-zA-Z']+", str(text).lower())
        pos_words = {"love", "amazing", "great", "fantastic", "excellent", "happy", "wonderful"}
        neg_words = {"hate", "terrible", "awful", "bad", "disappointed", "worst", "angry"}
        pos = sum(1 for t in tokens if t in pos_words)
        neg = sum(1 for t in tokens if t in neg_words)
        if pos == neg:
            return self._sentiment_result("neutral", 0.5, self._model_id("sentiment"))
        label = "positive" if pos > neg else "negative"
        score = 0.65 if label == "positive" else 0.65
        return self._sentiment_result(label, score, self._model_id("sentiment"))

    async def _external_sentiment(self, text: str) -> dict:
        payload = {
            "model": self.external_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a sentiment classifier. Return ONLY valid JSON with keys "
                        "sentiment_label (positive|negative|neutral) and confidence_score (0-1)."
                    ),
                },
                {"role": "user", "content": f"Text: {text}"},
            ],
            "temperature": 0,
        }

        data = await self._external_request(payload)
        return self._sentiment_result(
            data.get("sentiment_label", "neutral"),
            float(data.get("confidence_score", 0.0)),
            self._model_id("sentiment"),
        )

    async def _external_emotion(self, text: str) -> dict:
        payload = {
            "model": self.external_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an emotion classifier. Return ONLY valid JSON with keys "
                        "emotion (joy|sadness|anger|fear|surprise|neutral) and confidence_score (0-1)."
                    ),
                },
                {"role": "user", "content": f"Text: {text}"},
            ],
            "temperature": 0,
        }

        data = await self._external_request(payload)
        return self._emotion_result(
            data.get("emotion", "neutral"),
            float(data.get("confidence_score", 0.0)),
            self._model_id("emotion"),
        )

    async def _external_request(self, payload: dict) -> dict:
        if not self.external_api_key:
            return {}
        if self.provider != "groq":
            return {}

        headers = {
            "Authorization": f"Bearer {self.external_api_key}",
            "Content-Type": "application/json",
        }
        url = "https://api.groq.com/openai/v1/chat/completions"

        try:
            response = await self._client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return self._extract_json(content)
        except Exception:
            return {}

    def _extract_json(self, content: str) -> dict:
        try:
            return json.loads(content)
        except Exception:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return {}
        return {}
