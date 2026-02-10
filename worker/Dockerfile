FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV HF_HOME=/app/.hf_cache

COPY worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download HF models for offline evaluation
RUN python - <<'PY'
import os
from huggingface_hub import snapshot_download

models = [
	os.getenv("HUGGINGFACE_MODEL", "distilbert-base-uncased-finetuned-sst-2-english"),
	os.getenv("EMOTION_MODEL", "j-hartmann/emotion-english-distilroberta-base"),
]
for name in models:
	snapshot_download(repo_id=name, allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors", "*.bin", "tokenizer*", "vocab*", "merges*"])
PY

COPY worker/worker.py /app/worker.py
COPY backend /app/backend

CMD ["python", "worker.py"]
