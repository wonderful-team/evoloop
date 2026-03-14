#!/bin/bash
set -e

# Configuration
CLIENT_DIR="client"
TAURI_BIN_DIR="frontend/src-tauri/binaries"
BINARY_NAME="evoloop-client"

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
rm -rf "$CLIENT_DIR/dist" "$CLIENT_DIR/build"

# 2. Build with PyInstaller
echo "📦 Running PyInstaller..."
cd "$CLIENT_DIR"
uv run pyinstaller evoloop-client.spec
cd ..

# 3. Prepare Tauri Binaries Directory
mkdir -p "$TAURI_BIN_DIR"

# 4. Move and Rename Binary
if [ -f "$CLIENT_DIR/dist/$BINARY_NAME" ]; then
  mv "$CLIENT_DIR/dist/$BINARY_NAME" "$TAURI_BIN_DIR/$TARGET_BINARY"
  echo "✅ Sidecar built and placed at: $TAURI_BIN_DIR/$TARGET_BINARY"
else
  echo "❌ Error: Binary not found at $CLIENT_DIR/dist/$BINARY_NAME"
  exit 1
fi

# 5. Permission
chmod +x "$TAURI_BIN_DIR/$TARGET_BINARY"

echo "🎉 Build Complete!"
