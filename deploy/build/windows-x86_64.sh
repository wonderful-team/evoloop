#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/config.sh"

DEV_MODE=false
WITH_MODELS=true
DOWNLOAD_MODELS=false
MODELS_LIST=""
ARCH="x86_64-pc-windows-msvc"
ENVIRONMENT="production"
ENV_FILE=""

# Validate: building Windows from macOS requires x86_64 for cross-compilation
HOST_ARCH=$(uname -m)
if [ "$HOST_ARCH" != "x86_64" ] && [ "$HOST_ARCH" != "arm64" ]; then
  warn "Unsupported host CPU: ${HOST_ARCH}. Windows builds may not work."
fi

while [[ $# -gt 0 ]]; do
  case $1 in
    --dev|-d) DEV_MODE=true; ENVIRONMENT="development"; shift ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --env-file=*) ENV_FILE="${1#*=}"; shift ;;
    --with-models|-m) WITH_MODELS=true; shift ;;
    --without-models) WITH_MODELS=false; shift ;;
    --download-models)
      DOWNLOAD_MODELS=true
      if [[ $2 != --* ]] && [[ -n $2 ]]; then MODELS_LIST="$2"; shift 2; else shift; fi
      ;;
    --clean|-c) clean_artifacts; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --dev, -d                 Development mode"
      echo "  --with-models, -m         Bundle core models (classifiers + KWS). Default: true"
      echo "  --without-models          Skip bundling core models"
      echo "  --download-models [LIST]  Download optional speech models (not usually needed)"
      echo "  --clean, -c               Clean artifacts before build"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

load_env

if [ -n "$ENV_FILE" ]; then
  env_file_path="$PROJECT_ROOT/$ENV_FILE"
  if [ ! -f "$env_file_path" ]; then
    err "Env file not found: $env_file_path"
    exit 1
  fi
  cp "$env_file_path" "$PROJECT_ROOT/.env"
  ok "Copied env file: $ENV_FILE → .env"
fi

header "Building EvoLoop for Windows"

echo "  Target:     ${ARCH}"
echo "  Dev Mode:   ${DEV_MODE}"
echo "  With Models: ${WITH_MODELS}"
echo ""

if [ "$WITH_MODELS" = true ]; then
  step "Step 0: Preparing bundled core models (classifiers + KWS)"
  bash "$PROJECT_ROOT/deploy/prepare_bundled_models.sh"
fi

if [ "$DOWNLOAD_MODELS" = true ] && [ -n "$MODELS_LIST" ]; then
  step "Step 0b: Downloading optional speech models"
  download_speech_models "$MODELS_LIST"
fi

step "Step 1: Building Backend Sidecar"
bash "$SCRIPT_DIR/sidecar.sh" "x86_64" "$ARCH"

step "Step 2: Installing Frontend Dependencies"
install_frontend_deps

cd "$PROJECT_ROOT/frontend"

if [ "$WITH_MODELS" = true ]; then
  step "Step 3: Bundling Models"
  patch_tauri_config_for_models
fi

step "Step 4: Building Tauri Application"
if [ "$DEV_MODE" = true ]; then
  info "Starting dev server..."
  npm run tauri dev
else
  rustup target add "$ARCH" 2>/dev/null || true
  info "Building for distribution..."

  load_build_metadata

  BUILD_NUMBER="$BUILD_NUMBER" \
  BUILD_TIME="$BUILD_TIME" \
  GIT_COMMIT="$GIT_COMMIT" \
  RELEASE_STAGE="$RELEASE_STAGE" \
    npm run tauri build -- --target "$ARCH" || {
    err "Tauri build failed"
    exit 1
  }

  MSI_PATH="src-tauri/target/${ARCH}/release/bundle/msi"
  NSIS_PATH="src-tauri/target/${ARCH}/release/bundle/nsis"

  echo ""
  info "Output locations:"
  if [ -d "$MSI_PATH" ]; then
    find "$MSI_PATH" -name "*.msi" -type f 2>/dev/null | while read -r f; do
      fs=$(du -h "$f" 2>/dev/null | cut -f1)
      echo "   $(basename "$f") (${fs:-?})"
    done
  fi
  if [ -d "$NSIS_PATH" ]; then
    find "$NSIS_PATH" -name "*.exe" -type f 2>/dev/null | while read -r f; do
      fs=$(du -h "$f" 2>/dev/null | cut -f1)
      echo "   $(basename "$f") (${fs:-?})"
    done
  fi
fi

cd "$PROJECT_ROOT"
if [ "$WITH_MODELS" = true ]; then
  restore_tauri_config
  rm -rf "$PROJECT_ROOT/frontend/src-tauri/models"
fi

ok "Build complete!"
