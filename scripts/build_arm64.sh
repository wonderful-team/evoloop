#!/bin/bash
# Build arm64 DMG with libvosk.dylib fix

set -e

echo "=== Building EvoLoop arm64 DMG ==="

# Fix PATH for xattr
export PATH="/usr/bin:$PATH"

cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/frontend

# Build app bundle only (skip DMG for now)
echo "Building app bundle..."
npm run tauri build -- --target aarch64-apple-darwin --bundles app

APP_PATH="src-tauri/target/aarch64-apple-darwin/release/bundle/macos/EvoLoop.app"

# Fix libvosk.dylib
echo "Fixing libvosk.dylib..."
mkdir -p "$APP_PATH/Contents/Frameworks"
cp src-tauri/libs/libvosk.dylib "$APP_PATH/Contents/Frameworks/"
install_name_tool -change "libvosk.dylib" "@executable_path/../Frameworks/libvosk.dylib" "$APP_PATH/Contents/MacOS/EvoLoop"

# Re-sign
echo "Re-signing app..."
codesign --force --deep --sign - "$APP_PATH"

# Create DMG
echo "Creating DMG..."
DMG_PATH="src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/EvoLoop_0.1.0_aarch64.dmg"
mkdir -p "$(dirname "$DMG_PATH")"
rm -f "$DMG_PATH"

TMP_DIR=$(mktemp -d)
cp -R "$APP_PATH" "$TMP_DIR/"
hdiutil create -volname "EvoLoop" -srcfolder "$TMP_DIR" -format UDZO -o "$DMG_PATH" -quiet
rm -rf "$TMP_DIR"

# Copy to dist
mkdir -p ../dist
cp "$DMG_PATH" ../dist/EvoLoop_0.1.0_arm64.dmg

echo "=== Build complete ==="
echo "DMG: ../dist/EvoLoop_0.1.0_arm64.dmg"
ls -lh ../dist/EvoLoop_0.1.0_arm64.dmg
