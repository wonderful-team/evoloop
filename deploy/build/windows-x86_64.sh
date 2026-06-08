#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

DEV_MODE=false
WITH_MODELS=false
DOWNLOAD_MODELS=false
MODELS_LIST="paraformer-zh"
ARCH="x86_64-pc-windows-msvc"

# Validate: building Windows from macOS requires x86_64 for cross-compilation
HOST_ARCH=$(uname -m)
if [ "$HOST_ARCH" != "x86_64" ] && [ "$HOST_ARCH" != "arm64" ]; then
  warn "Unsupported host CPU: ${HOST_ARCH}. Windows builds may not work."
fi

while [[ $# -gt 0 ]]; do
  case $1 in
    --dev|-d) DEV_MODE=true; shift ;;
    --with-models|-m) WITH_MODELS=true; shift ;;
    --download-models)
      DOWNLOAD_MODELS=true
      if [[ $2 != --* ]] && [[ -n $2 ]]; then MODELS_LIST="$2"; shift 2; else shift; fi
      ;;
    --clean|-c) clean_artifacts; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --dev, -d                 Development mode"
      echo "  --with-models, -m         Bundle pre-downloaded models"
      echo "  --download-models [LIST]  Download models before build"
      echo "  --clean, -c               Clean artifacts before build"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

load_env

header "Building EvoLoop for Windows"

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
PYTHON="python3"
if [ -d "$PROJECT_ROOT/backend/.venv" ]; then
  PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
fi

cd "$PROJECT_ROOT/backend"
rm -rf dist build __pycache__

if ! $PYTHON -c "import PyInstaller" 2>/dev/null; then
  $PYTHON -m pip install pyinstaller
fi

check_numpy "$PYTHON"

if [ ! -f "evoloop-backend.spec" ]; then
  err "PyInstaller spec file not found"
  exit 1
fi

TAURI_BIN_DIR="$PROJECT_ROOT/frontend/src-tauri/binaries"
BINARY_NAME="evoloop-backend"
TARGET_BINARY="${BINARY_NAME}-${ARCH}"

$PYTHON -m PyInstaller evoloop-backend.spec --clean --noconfirm

mkdir -p "$TAURI_BIN_DIR"

if [ -f "dist/${BINARY_NAME}.exe" ]; then
  mv "dist/${BINARY_NAME}.exe" "${TAURI_BIN_DIR}/${TARGET_BINARY}.exe"
  ok "Sidecar built: ${TAURI_BIN_DIR}/${TARGET_BINARY}.exe"
elif [ -f "dist/${BINARY_NAME}" ]; then
  mv "dist/${BINARY_NAME}" "${TAURI_BIN_DIR}/${TARGET_BINARY}.exe"
  ok "Sidecar built: ${TAURI_BIN_DIR}/${TARGET_BINARY}.exe"
else
  err "Binary not found"
  exit 1
fi

step "Step 2: Installing Frontend Dependencies"
install_frontend_deps

cd "$PROJECT_ROOT/frontend"

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
