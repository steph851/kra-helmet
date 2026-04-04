#!/usr/bin/env bash
# Build script for Render / Koyeb / Railway free deployments
set -e

echo "=== Installing Python dependencies ==="
pip install --no-cache-dir -r requirements.txt

echo "=== Building React dashboard ==="
cd dashboard
npm ci
npx vite build
cd ..

echo "=== Creating data directories ==="
mkdir -p data/confirmed/sme_profiles \
         data/processed/obligations \
         data/filings \
         data/learning/proposals \
         data/monitoring \
         staging/review \
         staging/alerts \
         output/reports \
         logs \
         config

echo "=== Build complete ==="
