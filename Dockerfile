FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run: usa PORT o 8080 por defecto
CMD exec gunicorn -k uvicorn.workers.UvicornWorker \
    --timeout 120 \
    --bind 0.0.0.0:${PORT:-8080} app.main:app