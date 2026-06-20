#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

show_help() {
  echo "EvoLoop Development Mode"
  echo ""
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --help, -h    Show this help message"
  echo ""
  echo "Description:"
  echo "  Starts the backend (FastAPI) and frontend (Vite) development servers"
  echo "  simultaneously with hot-reload enabled."
  echo ""
  echo "  Backend:  http://localhost:8000"
  echo "  Frontend: http://localhost:5173"
  echo "  API docs: http://localhost:8000/docs"
  exit 0
}

for arg in "$@"; do
  [ "$arg" = "--help" ] || [ "$arg" = "-h" ] && show_help
done

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          EvoLoop Development Mode                            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Function to cleanup processes on exit
cleanup() {
  echo ""
  echo -e "${YELLOW}🛑 Shutting down...${NC}"
  if [ -n "$BACKEND_PID" ]; then
    kill $BACKEND_PID 2>/dev/null || true
  fi
  exit 0
}

trap cleanup INT TERM

BACKEND_PORT=20160

# Check if Backend is already running
echo -e "${YELLOW}🔍 Checking if Backend is already running...${NC}"
if curl -s http://localhost:$BACKEND_PORT/api/v1/system/health > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Backend is already running on port $BACKEND_PORT${NC}"
  BACKEND_ALREADY_RUNNING=true
else
  BACKEND_ALREADY_RUNNING=false
fi

# Start Backend if not running
if [ "$BACKEND_ALREADY_RUNNING" = false ]; then
  echo -e "${YELLOW}🚀 Starting Backend...${NC}"
  cd backend

  # Check for Python environment
  if [ -d ".venv" ]; then
    PYTHON=".venv/bin/python"
  else
    PYTHON="python3"
  fi

  # Start backend in background
  $PYTHON -m uvicorn app.main:app --host 127.0.0.1 --port $BACKEND_PORT --reload &
  BACKEND_PID=$!

  cd ..

  # Wait for backend to be ready
  echo -e "${YELLOW}⏳ Waiting for Backend to be ready...${NC}"
  for i in {1..30}; do
    if curl -s http://localhost:$BACKEND_PORT/api/v1/system/health > /dev/null 2>&1; then
      echo -e "${GREEN}✅ Backend is ready!${NC}"
      break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
      echo -e "${RED}❌ Backend failed to start within 30 seconds${NC}"
      exit 1
    fi
  done
fi

echo ""
echo -e "${BLUE}🖥️  Starting Tauri Frontend...${NC}"
echo -e "${YELLOW}  API → http://localhost:$BACKEND_PORT${NC}"
cd frontend
npm run tauri dev

# Cleanup will be called on exit
