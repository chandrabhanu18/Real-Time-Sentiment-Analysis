FROM python:3.9-slim

WORKDIR /app

COPY requirements-clean.txt .
RUN pip install --no-cache-dir -r requirements-clean.txt

COPY . .

CMD ["python", "ingester.py"]
