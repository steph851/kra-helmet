# KRA Deadline Tracker & Compliance Tool
# Simple single-stage build — dashboard is pre-built and committed to repo

FROM python:3.13-slim

WORKDIR /app

# System deps (curl for health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project (includes pre-built dashboard in output/dashboard-react/)
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
