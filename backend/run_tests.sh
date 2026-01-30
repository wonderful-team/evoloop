#!/bin/bash
set -e

echo "Cleaning up..."
rm -rf .venv

echo "Creating venv..."
uv venv

echo "Installing test dependencies..."
# Install requirements in the venv
uv pip install --python .venv -e . pytest pytest-asyncio pydantic sqlmodel sqlalchemy

echo "Running tests..."
uv run pytest tests/test_global_observation.py -v
