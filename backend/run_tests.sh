#!/bin/bash
# EvoLoop Test Runner Script
# Usage: ./run_tests.sh [category] [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default settings
CATEGORY=${1:-all}
EXTRA_ARGS=${@:2}

echo -e "${GREEN}EvoLoop Test Suite${NC}"
echo "================================"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Set Python path
export PYTHONPATH=.

# Function to run tests by category
run_tests() {
    local category=$1
    local marker=$2
    
    echo -e "\n${YELLOW}Running $category tests...${NC}"
    
    if [ -n "$marker" ]; then
        uv run pytest tests/ -m "$marker" $EXTRA_ARGS
    else
        uv run pytest tests/$category/ $EXTRA_ARGS
    fi
}

case $CATEGORY in
    api)
        run_tests "api"
        ;;
    engine)
        run_tests "engine"
        ;;
    nodes)
        run_tests "nodes"
        ;;
    tools)
        run_tests "tools"
        ;;
    infrastructure)
        run_tests "infrastructure"
        ;;
    e2e)
        run_tests "e2e" "e2e"
        ;;
    performance)
        run_tests "performance" "performance"
        ;;
    security)
        run_tests "security" "security"
        ;;
    unit)
        echo -e "\n${YELLOW}Running unit tests (excluding e2e, performance, security)...${NC}"
        uv run pytest tests/ -m "not e2e and not performance and not security and not slow" $EXTRA_ARGS
        ;;
    all)
        echo -e "\n${YELLOW}Running all tests...${NC}"
        uv run pytest tests/ $EXTRA_ARGS
        ;;
    quick)
        echo -e "\n${YELLOW}Running quick tests (unit only, no slow tests)...${NC}"
        uv run pytest tests/ -m "not e2e and not performance and not security and not slow" --tb=line $EXTRA_ARGS
        ;;
    coverage)
        echo -e "\n${YELLOW}Running tests with coverage...${NC}"
        uv run pytest tests/ --cov=app --cov-report=html --cov-report=term-missing $EXTRA_ARGS
        echo -e "\n${GREEN}Coverage report generated at htmlcov/index.html${NC}"
        ;;
    *)
        echo -e "${RED}Unknown category: $CATEGORY${NC}"
        echo ""
        echo "Usage: ./run_tests.sh [category] [options]"
        echo ""
        echo "Categories:"
        echo "  api           - API layer tests"
        echo "  engine        - Engine layer tests"
        echo "  nodes         - Workflow node tests"
        echo "  tools         - Tool layer tests"
        echo "  infrastructure - Infrastructure tests"
        echo "  e2e           - End-to-end tests"
        echo "  performance   - Performance tests"
        echo "  security      - Security tests"
        echo "  unit          - All unit tests (excludes e2e, performance, security)"
        echo "  all           - All tests"
        echo "  quick         - Quick unit tests (no slow tests)"
        echo "  coverage      - Run with coverage report"
        echo ""
        echo "Examples:"
        echo "  ./run_tests.sh api -v"
        echo "  ./run_tests.sh quick"
        echo "  ./run_tests.sh coverage"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Done!${NC}"
