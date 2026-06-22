#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ENVIRONMENT="production"
ENV_FILE=""
NO_PACKAGER="--no-packager"

while [[ $# -gt 0 ]]; do
  case $1 in
    --dev|-d) ENVIRONMENT="development"; shift ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --env-file=*) ENV_FILE="${1#*=}"; shift ;;
    --with-packager) NO_PACKAGER=""; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --dev, -d             Development mode"
      echo "  --env ENV             Build environment: development|production"
      echo "  --env-file FILE       Use specified env file (e.g. .env.prod.desktop)"
      echo "  --with-packager       Keep Metro packager running"
      echo "  --help, -h            Show this help"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

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

APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || grep ^APP_VERSION= "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 || echo "0.1.0")

header "Building EvoLoop for HarmonyOS"

echo "  Environment: ${ENVIRONMENT}"
echo "  App Version: ${APP_VERSION}"
echo ""

cd "$PROJECT_ROOT/mobile"

step "Installing dependencies"
if [ ! -d "node_modules" ]; then
  yarn install --frozen-lockfile
else
  ok "node_modules exists"
fi

step "Bundling JS and building HAP"
if [ "$ENVIRONMENT" = "development" ]; then
  ENVFILE=../.env npx react-native run-harmony $NO_PACKAGER
else
  ENVFILE=../.env npx react-native run-harmony --build-mode Release $NO_PACKAGER
fi

step "Collecting HAP artifact"
HAP_OUTPUT_DIR="$PROJECT_ROOT/mobile/ios/build/outputs/default"
if [ ! -d "$HAP_OUTPUT_DIR" ]; then
  err "HAP output directory not found: $HAP_OUTPUT_DIR"
  exit 1
fi

HAP_FILE=$(find "$HAP_OUTPUT_DIR" -name "*.hap" -type f 2>/dev/null | head -1)
if [ -z "$HAP_FILE" ]; then
  err "No HAP file found in $HAP_OUTPUT_DIR"
  exit 1
fi

DEST_NAME="EvoLoop_${APP_VERSION}.hap"
mkdir -p "$PROJECT_ROOT/deploy/dist"
cp "$HAP_FILE" "$PROJECT_ROOT/deploy/dist/$DEST_NAME"
ok "HAP copied: $PROJECT_ROOT/deploy/dist/$DEST_NAME"

# 同时同步到 member-center bundle 目录
MEMBER_CENTER_BUNDLE="$PROJECT_ROOT/../member-center/website/bundle"
if [ -d "$MEMBER_CENTER_BUNDLE" ]; then
  mkdir -p "$MEMBER_CENTER_BUNDLE"
  cp "$HAP_FILE" "$MEMBER_CENTER_BUNDLE/$DEST_NAME"
  ok "HAP synced: $MEMBER_CENTER_BUNDLE/$DEST_NAME"
fi

cd "$PROJECT_ROOT"
ok "HarmonyOS build complete!"
