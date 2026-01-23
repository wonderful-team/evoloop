#!/bin/bash
set -e

echo "🚀 Starting Project Health Check..."

# 1. Formatting & Linting (Ruff)
echo "🔍 Running Ruff check..."
uv run ruff check app

# 2. Type Checking (Pyright)
echo "✨ Running Pyright analysis..."
uv run pyright app

echo "✅ All checks passed!"
