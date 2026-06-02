#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ENVIRONMENT="production"
VITE_API_URL=""
OUTPUT_DIR="dist"

while [[ $# -gt 0 ]]; do
  case $1 in
    --api-url) VITE_API_URL="$2"; shift 2 ;;
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --dev) ENVIRONMENT="development"; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Build frontend static assets for server deployment."
      echo "Output is a static site served by Nginx (or any web server)."
      echo ""
      echo "Options:"
      echo "  --api-url URL     Backend API URL (e.g. https://api.your-domain.com)"
      echo "  --output DIR      Output directory (default: dist/)"
      echo "  --dev             Build in development mode"
      echo "  --help, -h        Show this help"
      echo ""
      echo "Examples:"
      echo "  $0 --api-url https://api.evoloop.ai"
      echo "  $0 --api-url http://localhost:20160 --dev"
      echo "  VITE_API_URL=https://api.evoloop.ai $0"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

init_config "server"
load_env

cd "$PROJECT_ROOT/frontend"

header "Building Frontend for Server Deployment"

if [ -z "$VITE_API_URL" ]; then
  VITE_API_URL="http://backend:20160"
fi

info "API URL: $VITE_API_URL"
info "Environment: $ENVIRONMENT"

step "Installing dependencies"
if [ ! -d "node_modules" ]; then
  npm install
else
  ok "node_modules exists"
fi

step "Building frontend"
if [ "$OUTPUT_DIR" != "dist" ]; then
  info "Output dir: $OUTPUT_DIR (VITE_OUTPUT_DIR=$OUTPUT_DIR)"
  VITE_API_URL="$VITE_API_URL" VITE_OUTPUT_DIR="$OUTPUT_DIR" npm run build
  if [ -d "dist" ]; then
    rm -rf "$OUTPUT_DIR"
    mv dist "$OUTPUT_DIR"
  fi
else
  VITE_API_URL="$VITE_API_URL" npm run build
fi

if [ -d "dist" ]; then
  ok "Frontend built: $(du -sh dist | cut -f1)"
  info "Output: $PROJECT_ROOT/frontend/dist/"
  echo ""
  echo "Deployment options:"
  echo "  1. Docker: docker compose up --build frontend"
  echo "  2. Nginx:  Copy dist/ to /usr/share/nginx/html/"
  echo "  3. Baota:  Point website root to dist/"
else
  err "Build failed"
  exit 1
fi
