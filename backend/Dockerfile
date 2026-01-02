FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Install runtime dependencies (avoid heavy ML deps by default)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/backend

# Run the package-qualified app entrypoint
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
