#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/config.sh"

DEV_MODE=false
WITH_MODELS=true
DOWNLOAD_MODELS=false
MODELS_LIST=""
ENVIRONMENT="production"
ENV_FILE=""
TARGET_ARCH=""  # arm64 or x86_64

while [[ $# -gt 0 ]]; do
  case $1 in
    --arch) TARGET_ARCH="$2"; shift 2 ;;
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
      echo "Usage: $0 --arch arm64|x86_64 [options]"
      echo ""
      echo "  --arch ARCH           Target architecture: arm64 or x86_64"
      echo "  --dev, -d             Development mode"
      echo "  --env ENV             Build environment: development|production"
      echo "  --with-models, -m     Bundle core models (classifiers + KWS). Default: true"
      echo "  --without-models      Skip bundling core models"
      echo "  --download-models [LIST]  Download optional speech models (not usually needed)"
      echo "  --clean, -c           Clean artifacts before build"
      echo "  --help, -h            Show this help"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

if [ -z "$TARGET_ARCH" ]; then
  err "--arch is required (arm64 or x86_64)"
  exit 1
fi

# 归一化别名，后续 host 校验与编译参数判断只认 arm64 / x86_64
[ "$TARGET_ARCH" = "aarch64" ] && TARGET_ARCH="arm64"

case "$TARGET_ARCH" in
  arm64|aarch64)
    ARCH="${ARCH:-aarch64-apple-darwin}"
    DMG_SUFFIX="aarch64"
    SIDECAR_ARCH="arm64"
    HOST_ARCH_OK="arm64|aarch64"
    LABEL="Apple Silicon"
    ;;
  x86_64)
    ARCH="x86_64-apple-darwin"
    DMG_SUFFIX="x86_64"
    SIDECAR_ARCH="x86_64"
    HOST_ARCH_OK="x86_64"
    LABEL="Intel"
    export MACOSX_DEPLOYMENT_TARGET="10.15"
    ;;
  *)
    err "Unsupported architecture: $TARGET_ARCH (use arm64 or x86_64)"
    exit 1
    ;;
esac

# Validate host arch matches target (sidecar must be native)
HOST_ARCH=$(uname -m)
case "$TARGET_ARCH" in
  arm64)
    if [ "$HOST_ARCH" != "arm64" ] && [ "$HOST_ARCH" != "aarch64" ]; then
      err "Host CPU is ${HOST_ARCH}, but target is ${TARGET_ARCH}."
      err "The Python sidecar must match the host architecture."
      exit 1
    fi
    ;;
  x86_64)
    if [ "$HOST_ARCH" != "x86_64" ]; then
      err "Host CPU is ${HOST_ARCH}, but target is ${TARGET_ARCH}."
      err "Run this on an Intel Mac / x86_64 CI runner."
      exit 1
    fi
    ;;
esac

load_env
ensure_xattr

if [ -n "$ENV_FILE" ]; then
  env_file_path="$PROJECT_ROOT/$ENV_FILE"
  if [ ! -f "$env_file_path" ]; then
    err "Env file not found: $env_file_path"
    exit 1
  fi
  cp "$env_file_path" "$PROJECT_ROOT/.env"
  ok "Copied env file: $ENV_FILE → .env"
fi

header "Building EvoLoop for macOS (${LABEL})"

echo "  Target:     ${ARCH}"
echo "  Dev Mode:   ${DEV_MODE}"
echo "  With Models: ${WITH_MODELS}"
echo ""

# =============================================================================
# Phase 1: 准备阶段（Python 环境）
# =============================================================================
header "Phase 1: Environment Preparation"

step "Preparing Python environment"
check_numpy "python3"

# =============================================================================
# Phase 2: 下载/准备阶段（模型）
# =============================================================================
header "Phase 2: Model Download / Preparation"

if [ "$WITH_MODELS" = true ]; then
  step "Step 1: Preparing bundled core models (classifiers + KWS)"
  bash "$PROJECT_ROOT/deploy/prepare_bundled_models.sh"
fi

if [ "$DOWNLOAD_MODELS" = true ] && [ -n "$MODELS_LIST" ]; then
  step "Step 2: Downloading optional speech models"
  download_speech_models "$MODELS_LIST"
fi

# =============================================================================
# Phase 3: 构建后端 Sidecar
# =============================================================================
header "Phase 3: Building Backend Sidecar"

step "Building sidecar binary"
bash "$SCRIPT_DIR/sidecar.sh" "$SIDECAR_ARCH" "$ARCH"

# =============================================================================
# Phase 4: 构建前端 + Tauri 打包
# =============================================================================
header "Phase 4: Building Frontend + Tauri"

step "Installing Frontend Dependencies"
install_frontend_deps

cd "$PROJECT_ROOT/frontend"

if [ -z "$VITE_API_URL" ]; then
  VITE_API_URL="http://127.0.0.1:20160"
fi
export VITE_API_URL
info "前端环境: $ENVIRONMENT (VITE_API_URL=${VITE_API_URL})"

if [ "$WITH_MODELS" = true ]; then
  step "Bundling Models"
  patch_tauri_config_for_models
fi

step "Building Tauri Application"
export CPLUS_INCLUDE_PATH="$(xcrun --show-sdk-path)/usr/include/c++/v1"
export SOURCE_DATE_EPOCH=1
if [ "$TARGET_ARCH" = "arm64" ]; then
  export CXXFLAGS_aarch64_apple_darwin="-D_LIBCPP_DISABLE_AVAILABILITY"
else
  export CXXFLAGS_x86_64_apple_darwin="-D_LIBCPP_DISABLE_AVAILABILITY"
fi

if [ "$DEV_MODE" = true ]; then
  info "Starting dev server..."
  npm run tauri dev
else
  rustup target add "$ARCH" 2>/dev/null || true
  info "Building for distribution..."

  load_build_metadata

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
  DMG_PATH="src-tauri/target/${ARCH}/release/bundle/dmg/EvoLoop_${APP_VERSION}_${DMG_SUFFIX}.dmg"

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
