#!/bin/bash
set -e
export MACOSX_DEPLOYMENT_TARGET="10.15"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/config.sh"

DEV_MODE=false
WITH_MODELS=false
DOWNLOAD_MODELS=false
MODELS_LIST="paraformer-zh"
ARCH="x86_64-apple-darwin"
ENVIRONMENT="production"
ENV_FILE=""

# Validate: this script requires Intel Mac (x86_64)
HOST_ARCH=$(uname -m)
if [ "$HOST_ARCH" != "x86_64" ]; then
  warn "Host CPU is ${HOST_ARCH}, but this script builds for Intel (x86_64)."
  warn "The resulting Rust binary will be cross-compiled and may not run natively."
  warn ""
  warn "  ✓ Use 'macos-arm64' for Apple Silicon Macs"
  warn "  ✓ Use 'current' for auto-detection"
  echo ""
fi

while [[ $# -gt 0 ]]; do
  case $1 in
    --dev|-d) DEV_MODE=true; ENVIRONMENT="development"; shift ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --env-file=*) ENV_FILE="${1#*=}"; shift ;;
    --with-models|-m) WITH_MODELS=true; shift ;;
    --download-models)
      DOWNLOAD_MODELS=true
      if [[ $2 != --* ]] && [[ -n $2 ]]; then MODELS_LIST="$2"; shift 2; else shift; fi
      ;;
    --clean|-c) clean_artifacts; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --dev, -d                 Development mode"
      echo "  --env ENV                 Build environment: development|production"
      echo "  --with-models, -m         Bundle pre-downloaded models"
      echo "  --download-models [LIST]  Download models before build"
      echo "  --clean, -c               Clean artifacts before build"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

load_env
ensure_xattr

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

header "Building EvoLoop for macOS (Intel)"

echo "  Target:     ${ARCH}"
echo "  Dev Mode:   ${DEV_MODE}"
echo "  With Models: ${WITH_MODELS}"
echo ""

step "Step 0: Ensuring embedding model (required)"
ensure_embedding

if [ "$DOWNLOAD_MODELS" = true ]; then
  step "Step 0b: Downloading speech models (for desktop client)"
  download_speech_models "$MODELS_LIST"
fi

step "Pre-build: Checking Python environment"
check_numpy "python3"

step "Step 1: Building Backend Sidecar"
bash "$SCRIPT_DIR/sidecar.sh" "x86_64" "$ARCH"

step "Step 2: Installing Frontend Dependencies"
install_frontend_deps

cd "$PROJECT_ROOT/frontend"

# 设置并导出 VITE_API_URL 给前端使用
if [ -z "$VITE_API_URL" ]; then
  VITE_API_URL="http://127.0.0.1:20160"
fi
export VITE_API_URL
info "前端环境: $ENVIRONMENT (VITE_API_URL=${VITE_API_URL})"

if [ "$WITH_MODELS" = true ]; then
  step "Step 3: Bundling Models"
  bundle_models "$APP_DATA_DIR/models" "src-tauri/models"
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

  export CPLUS_INCLUDE_PATH="$(xcrun --show-sdk-path)/usr/include/c++/v1"
  export SOURCE_DATE_EPOCH=1
  export CXXFLAGS_x86_64_apple_darwin="-D_LIBCPP_DISABLE_AVAILABILITY"

  LIBRARY_PATH="$PROJECT_ROOT/frontend/src-tauri/libs:$LIBRARY_PATH" \
  EVOLOOP_BACKEND_PORT="$BACKEND_PORT" \
  VITE_API_URL="$VITE_API_URL" \
  BUILD_NUMBER="$BUILD_NUMBER" \
  BUILD_TIME="$BUILD_TIME" \
  GIT_COMMIT="$GIT_COMMIT" \
  RELEASE_STAGE="$RELEASE_STAGE" \
    npm run tauri build -- --target "$ARCH" --bundles app || {
    warn "Tauri build failed"
    exit 1
  }

  APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || grep ^APP_VERSION= "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 || echo "0.1.0")
  APP_BUNDLE="src-tauri/target/${ARCH}/release/bundle/macos/EvoLoop.app"
  DMG_PATH="src-tauri/target/${ARCH}/release/bundle/dmg/EvoLoop_${APP_VERSION}_x86_64.dmg"

  if [ ! -d "$APP_BUNDLE" ]; then
    if [ -d "src-tauri/target/release/EvoLoop.app" ]; then
      mkdir -p "src-tauri/target/${ARCH}/release/bundle/macos"
      mv "src-tauri/target/release/EvoLoop.app" "$APP_BUNDLE"
    fi
  fi

  if [ -d "$APP_BUNDLE" ]; then
    fix_libvosk "$APP_BUNDLE"

    if [ "$WITH_MODELS" = true ] && [ -d "src-tauri/models" ]; then
      mkdir -p "$APP_BUNDLE/Contents/Resources/models"
      cp -R "src-tauri/models/." "$APP_BUNDLE/Contents/Resources/models/"
    fi

    sign_bundle "$APP_BUNDLE"
    create_dmg "$APP_BUNDLE" "$DMG_PATH"
    show_output "$APP_BUNDLE" "${DMG_PATH}"
  else
    err "App bundle not found"
    exit 1
  fi
fi

cd "$PROJECT_ROOT"
if [ "$WITH_MODELS" = true ]; then
  restore_tauri_config
  rm -rf "$PROJECT_ROOT/frontend/src-tauri/models"
fi

ok "Build complete!"
