#!/bin/bash
set -e

echo "Checking for critical errors (Undefined names, Syntax errors)..."
uv run ruff check app/ --select E9,F63,F7,F821

if [ $? -eq 0 ]; then
    echo "✅ No critical errors found."
else
    echo "❌ Critical errors found!"
    exit 1
fi
