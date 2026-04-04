# KRA Deadline Tracker & Compliance Tool
# Multi-stage build: Node (dashboard) + Python (API)

# Stage 1: Build React dashboard
FROM node:20-slim AS frontend
WORKDIR /app/dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --production=false
COPY dashboard/ .
RUN npx vite build

# Stage 2: Python API + built dashboard
FROM python:3.11-slim

WORKDIR /app

# Install runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Copy built dashboard from stage 1
COPY --from=frontend /app/output/dashboard-react ./output/dashboard-react

# Create data dirs
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
             config && \
    chmod -R 755 data staging output logs memory config

# Non-root user
RUN useradd -m -u 1000 kradtc && \
    chown -R kradtc:kradtc /app
USER kradtc

# Port (overridden by platform via $PORT)
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
