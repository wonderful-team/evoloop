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
  
  export CPLUS_INCLUDE_PATH="$(xcrun --show-sdk-path)/usr/include/c++/v1"
  export SOURCE_DATE_EPOCH=1
  export CXXFLAGS_x86_64_apple_darwin="-D_LIBCPP_DISABLE_AVAILABILITY"

  LIBRARY_PATH="$PROJECT_ROOT/frontend/src-tauri/libs:$LIBRARY_PATH" EVOLOOP_BACKEND_PORT="$BACKEND_PORT" VITE_API_URL="$VITE_API_URL" npm run tauri build -- --target "$ARCH" --bundles app || {
    warn "Tauri build failed, attempting manual bundling..."
  }

  APP_BUNDLE="src-tauri/target/${ARCH}/release/bundle/macos/EvoLoop.app"
  DMG_PATH="src-tauri/target/${ARCH}/release/bundle/dmg/EvoLoop_0.1.0_x86_64.dmg"

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
