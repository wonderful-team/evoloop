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

BINARY_NAME="evoloop-backend"
TARGET_BINARY="${BINARY_NAME}-${TRIPLE}"
TAURI_BIN_DIR="$PROJECT_ROOT/frontend/src-tauri/binaries"

header "Building Backend Sidecar for ${TRIPLE}"

cd "$PROJECT_ROOT/backend"

info "Cleaning previous build..."
rm -rf dist build __pycache__

PYTHON="python3"
if [ -n "$ARCH_PREFIX" ]; then
  if command -v arch &>/dev/null; then
    PYTHON="arch -${ARCH_PREFIX} python3"
  fi
fi

if [ -d ".venv" ]; then
  PYTHON=".venv/bin/python"
  if [ -n "$ARCH_PREFIX" ] && command -v arch &>/dev/null; then
    PYTHON_ARCH=$($PYTHON -c "import platform; print(platform.machine())" 2>/dev/null || echo "unknown")
    if [ "$PYTHON_ARCH" != "$ARCH_PREFIX" ]; then
      warn "Python is ${PYTHON_ARCH}, cannot force ${ARCH_PREFIX} — using native arch"
    else
      PYTHON="arch -${ARCH_PREFIX} .venv/bin/python"
    fi
  fi
  ok "Using virtual environment (${ARCH_PREFIX:-native})"
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

if [ -f "dist/${BINARY_NAME}" ]; then
  mv "dist/${BINARY_NAME}" "${TAURI_BIN_DIR}/${TARGET_BINARY}"
  chmod +x "${TAURI_BIN_DIR}/${TARGET_BINARY}"
  ok "Sidecar built: ${TAURI_BIN_DIR}/${TARGET_BINARY}"

  if command -v codesign &>/dev/null; then
    codesign --force --sign - "${TAURI_BIN_DIR}/${TARGET_BINARY}" 2>/dev/null || \
      warn "Could not sign binary"
  fi

  FILE_SIZE=$(du -h "${TAURI_BIN_DIR}/${TARGET_BINARY}" | cut -f1)
  info "Binary size: ${FILE_SIZE}"
else
  err "Binary not found at dist/${BINARY_NAME}"
  exit 1
fi

# Copy macOS App Bundle to resources if it exists
if [ -d "dist/EvoLoop Backend.app" ]; then
  TAURI_RESOURCES_DIR="$PROJECT_ROOT/frontend/src-tauri/resources"
  mkdir -p "$TAURI_RESOURCES_DIR"
  # Remove old bundle if exists
  rm -rf "$TAURI_RESOURCES_DIR/EvoLoop Backend.app"
  cp -R "dist/EvoLoop Backend.app" "$TAURI_RESOURCES_DIR/"
  ok "Sidecar App Bundle copied to $TAURI_RESOURCES_DIR"
fi
