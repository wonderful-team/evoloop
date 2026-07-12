#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ENVIRONMENT="production"
VITE_API_URL=""
OUTPUT_DIR="dist"
ENV_FILE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --api-url) VITE_API_URL="$2"; shift 2 ;;
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --env-file=*) ENV_FILE="${1#*=}"; shift ;;
    --dev) ENVIRONMENT="development"; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Build frontend static assets for server deployment."
      echo ""
      echo "Options:"
      echo "  --api-url URL     Backend API URL (overrides .env)"
      echo "  --output DIR      Output directory (default: dist/)"
      echo "  --env ENV         Environment: development|production (default: production)"
      echo "  --env-file FILE   Use specified env file (e.g. .env.prod.web.multi)"
      echo "  --dev             Shortcut for --env development"
      echo "  --help, -h        Show this help"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

cd "$PROJECT_ROOT/frontend"

# 生产构建必须隔离本地覆盖文件：vite 的 loadEnv 会让 .env.local 覆盖 .env，
# 若不隔离，.env.local 里的开发地址会盖掉 prod 模板，污染日志甚至 bundle。
STASHED_ENVS=()
stash_local_envs() {
  for f in .env.local .env.production.local; do
    if [ -f "$PROJECT_ROOT/$f" ]; then
      mv "$PROJECT_ROOT/$f" "$PROJECT_ROOT/$f.build-stash"
      STASHED_ENVS+=("$f")
      info "Stashed $f for isolated production build"
    fi
  done
}
restore_local_envs() {
  for f in "${STASHED_ENVS[@]}"; do
    if [ -f "$PROJECT_ROOT/$f.build-stash" ]; then
      mv "$PROJECT_ROOT/$f.build-stash" "$PROJECT_ROOT/$f"
    fi
  done
}
trap restore_local_envs EXIT INT TERM

# 如果指定了 --env-file，先复制到根目录 .env
if [ -n "$ENV_FILE" ]; then
  env_file_path="$PROJECT_ROOT/$ENV_FILE"
  if [ ! -f "$env_file_path" ]; then
    err "Env file not found: $env_file_path"
    exit 1
  fi
  cp "$env_file_path" "$PROJECT_ROOT/.env"
  ok "Copied env file: $ENV_FILE → .env"
fi

stash_local_envs

header "Building Frontend for Server Deployment ($ENVIRONMENT)"

# Vite will automatically read from the root .env
cd "$PROJECT_ROOT/frontend"
step "Installing dependencies"
install_frontend_deps

if [ -z "$VITE_API_URL" ]; then
  VITE_API_URL=$(grep ^VITE_API_URL= "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2-)
fi
info "Effective VITE_API_URL=${VITE_API_URL:-<relative/same-origin>}"

step "Building frontend"
BUILD_ENV=()
[ -n "$VITE_API_URL" ] && BUILD_ENV+=(VITE_API_URL="$VITE_API_URL")
if [ "$OUTPUT_DIR" != "dist" ]; then
  env "${BUILD_ENV[@]}" VITE_OUTPUT_DIR="$OUTPUT_DIR" npm run build
  if [ -d "dist" ]; then
    rm -rf "$OUTPUT_DIR"
    mv dist "$OUTPUT_DIR"
  fi
else
  env "${BUILD_ENV[@]}" npm run build
fi

if [ -d "$OUTPUT_DIR" ]; then
  ok "Frontend built ($ENVIRONMENT): $(du -sh "$OUTPUT_DIR" | cut -f1)"
  info "Output: $PROJECT_ROOT/frontend/$OUTPUT_DIR/"
else
  err "Build failed"
  exit 1
fi
