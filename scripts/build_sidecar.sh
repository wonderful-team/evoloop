#!/bin/bash
set -e

# Configuration
BACKEND_DIR="backend"
TAURI_BIN_DIR="frontend/src-tauri/binaries"
BINARY_NAME="evoloop-backend"

# Detect Architecture
ARCH=$(uname -m)
if [ "$ARCH" == "x86_64" ]; then
  TRIPLE="x86_64-apple-darwin"
elif [ "$ARCH" == "arm64" ]; then
  TRIPLE="aarch64-apple-darwin"
else
  echo "Unsupported architecture: $ARCH"
  exit 1
fi

TARGET_BINARY="${BINARY_NAME}-${TRIPLE}"

echo "🚀 Building Sidecar for ${TRIPLE}..."

# 1. Clean previous build
rm -rf "$BACKEND_DIR/dist" "$BACKEND_DIR/build"

# 2. Build with PyInstaller
echo "📦 Running PyInstaller..."
cd "$BACKEND_DIR"
uv run pyinstaller evoloop-backend.spec
cd ..

# 3. Prepare Tauri Binaries Directory
mkdir -p "$TAURI_BIN_DIR"

# 4. Move and Rename Binary
if [ -f "$BACKEND_DIR/dist/$BINARY_NAME" ]; then
  mv "$BACKEND_DIR/dist/$BINARY_NAME" "$TAURI_BIN_DIR/$TARGET_BINARY"
  echo "✅ Sidecar built and placed at: $TAURI_BIN_DIR/$TARGET_BINARY"
else
  echo "❌ Error: Binary not found at $BACKEND_DIR/dist/$BINARY_NAME"
  exit 1
fi

# 5. Permission
chmod +x "$TAURI_BIN_DIR/$TARGET_BINARY"

echo "🎉 Build Complete!"
