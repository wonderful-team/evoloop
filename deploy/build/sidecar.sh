#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ARCH_PREFIX="${1:-}"
TRIPLE="${2:-}"

if [ -z "$TRIPLE" ]; then
  case "$(uname -m)" in
    arm64) TRIPLE="aarch64-apple-darwin" ;;
    x86_64)
      if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
        TRIPLE="aarch64-apple-darwin"
      else
        TRIPLE="x86_64-apple-darwin"
      fi
      ;;
    *)
      err "Unsupported architecture: $(uname -m)"
      exit 1
      ;;
  esac
fi

IS_WINDOWS=false
case "$TRIPLE" in
  *windows*) IS_WINDOWS=true ;;
esac

BINARY_NAME="evoloop-backend"
EXE_SUFFIX=""
[ "$IS_WINDOWS" = true ] && EXE_SUFFIX=".exe"
TARGET_BINARY="${BINARY_NAME}-${TRIPLE}${EXE_SUFFIX}"
TAURI_BIN_DIR="$PROJECT_ROOT/frontend/src-tauri/binaries"

header "Building Backend Sidecar for ${TRIPLE}"

cd "$PROJECT_ROOT/backend"

info "Cleaning previous build..."
rm -rf dist build __pycache__

PYTHON="python3"
VENV_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
[ "$IS_WINDOWS" = true ] && VENV_PYTHON="$PROJECT_ROOT/backend/.venv/Scripts/python.exe"

detect_arch() {
  "$1" -c "import platform; print(platform.machine())" 2>/dev/null || echo "unknown"
}

if [ -d ".venv" ] && [ -x "$VENV_PYTHON" ]; then
  VENV_ARCH=$(detect_arch "$VENV_PYTHON")
  if [ -n "$ARCH_PREFIX" ] && [ "$VENV_ARCH" != "$ARCH_PREFIX" ]; then
    err "Backend venv is ${VENV_ARCH}, but target sidecar is ${ARCH_PREFIX}."
    err "Refusing to build a mislabeled sidecar."
    err "Build on a ${ARCH_PREFIX} machine, or recreate backend/.venv for ${ARCH_PREFIX}."
    exit 1
  fi
  PYTHON="$VENV_PYTHON"
  if [ -n "$ARCH_PREFIX" ] && command -v arch &>/dev/null; then
    PYTHON="arch -${ARCH_PREFIX} $VENV_PYTHON"
  fi
  ok "Using virtual environment (${VENV_ARCH})"
else
  if [ "$IS_WINDOWS" = true ]; then
    for cmd in python3 python; do
      if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
      fi
    done
  elif [ -n "$ARCH_PREFIX" ] && command -v arch &>/dev/null; then
    PYTHON="arch -${ARCH_PREFIX} python3"
  fi
  ok "Using system Python (${ARCH_PREFIX:-native})"
fi

if ! $PYTHON -c "import PyInstaller" 2>/dev/null; then
  info "Installing PyInstaller..."
  $PYTHON -m pip install pyinstaller
fi

check_numpy "$PYTHON"

if [ ! -f "evoloop-backend.spec" ]; then
  err "PyInstaller spec file not found"
  exit 1
fi

info "Building with PyInstaller (this may take several minutes)..."
$PYTHON -m PyInstaller evoloop-backend.spec --clean --noconfirm

mkdir -p "$TAURI_BIN_DIR"

SOURCE_FILE="dist/${BINARY_NAME}${EXE_SUFFIX}"
if [ -f "$SOURCE_FILE" ]; then
  mv "$SOURCE_FILE" "${TAURI_BIN_DIR}/${TARGET_BINARY}"
  if [ "$IS_WINDOWS" = false ]; then
    chmod +x "${TAURI_BIN_DIR}/${TARGET_BINARY}"
  fi
  ok "Sidecar built: ${TAURI_BIN_DIR}/${TARGET_BINARY}"

  if [ "$IS_WINDOWS" = false ] && command -v codesign &>/dev/null; then
    codesign --force --sign - "${TAURI_BIN_DIR}/${TARGET_BINARY}" 2>/dev/null || \
      warn "Could not sign binary"
  fi

  FILE_SIZE=$(du -h "${TAURI_BIN_DIR}/${TARGET_BINARY}" | cut -f1)
  info "Binary size: ${FILE_SIZE}"
else
  # Fallback: try without .exe
  if [ "$IS_WINDOWS" = true ] && [ -f "dist/${BINARY_NAME}" ]; then
    mv "dist/${BINARY_NAME}" "${TAURI_BIN_DIR}/${TARGET_BINARY}"
    ok "Sidecar built (no .exe): ${TAURI_BIN_DIR}/${TARGET_BINARY}"
  else
    err "Binary not found at ${SOURCE_FILE}"
    err "Contents of dist/:"; ls -la dist/ 2>/dev/null || true
    exit 1
  fi
fi

# Copy macOS App Bundle to resources if it exists (macOS only)
if [ "$IS_WINDOWS" = false ] && [ -d "dist/EvoLoop Backend.app" ]; then
  TAURI_RESOURCES_DIR="$PROJECT_ROOT/frontend/src-tauri/resources"
  mkdir -p "$TAURI_RESOURCES_DIR"
  rm -rf "$TAURI_RESOURCES_DIR/EvoLoop Backend.app"
  cp -R "dist/EvoLoop Backend.app" "$TAURI_RESOURCES_DIR/"
  ok "Sidecar App Bundle copied to $TAURI_RESOURCES_DIR"
fi
