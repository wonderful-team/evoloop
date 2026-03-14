#!/bin/bash
# EvoLoop Client Sidecar Build Script
# Usage: ./bin/build_sidecar.sh

set -e

# Navigate to client directory
cd "$(dirname "$0")/.."

echo "Building EvoLoop Client Sidecar with PyInstaller..."

# 1. Run PyInstaller
# Ensure dependencies are installed: pip install pyinstaller
pyinstaller evoloop-client.spec --clean --noconfirm

# 2. Determine Platform Triple
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

if [ "$OS" = "darwin" ]; then
    OS="apple-darwin"
    if [ "$ARCH" = "arm64" ]; then ARCH="aarch64"; fi
elif [ "$OS" = "linux" ]; then
    OS="unknown-linux-gnu"
    if [ "$ARCH" = "x86_64" ]; then ARCH="x86_64"; fi
else
    echo "Unsupported OS: $OS"
    exit 1
fi

TRIPLE="${ARCH}-${OS}"
BINARY_NAME="evoloop-client"
SOURCE_EXE="dist/${BINARY_NAME}"
TARGET_DIR="../frontend/src-tauri/binaries"
TARGET_EXE="${TARGET_DIR}/${BINARY_NAME}-${TRIPLE}"

# 3. Move to Tauri Binaries Folder
mkdir -p "$TARGET_DIR"
echo "Moving binary to ${TARGET_EXE}"
cp "$SOURCE_EXE" "$TARGET_EXE"

echo "Sidecar build complete!"
echo "Binary located at: ${TARGET_EXE}"
