# KRA Deadline Tracker & Compliance Tool
# Supports Neon PostgreSQL for persistent storage

FROM python:3.14-slim

WORKDIR /app

# System deps (curl + build tools for psycopg2-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Ensure data directories exist
RUN mkdir -p data/confirmed/sme_profiles \
             data/processed/obligations \
             data/filings \
             data/learning/proposals \
             data/monitoring \
             staging/review \
             staging/alerts \
             output/reports \
             logs \
             memory/decisions \
             config

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}