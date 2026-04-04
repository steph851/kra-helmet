# KRA Deadline Tracker — Tax Compliance Autopilot for Kenyan SMEs
# Multi-stage build for production deployment

FROM python:3.13-slim AS builder

WORKDIR /app

# Install system dependencies for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project files
COPY . .

# Create data directories with proper permissions
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

# Create non-root user for security
RUN useradd -m -u 1000 helmet && \
    chown -R helmet:helmet /app

USER helmet

# Database configuration environment variables
ENV DATABASE_URL=postgresql://helmet:helmet@db:5432/kra_helmet
ENV DB_HOST=db
ENV DB_PORT=5432
ENV DB_NAME=kra_helmet
ENV DB_USER=helmet
ENV DB_PASSWORD=helmet

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default command: run API server
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
