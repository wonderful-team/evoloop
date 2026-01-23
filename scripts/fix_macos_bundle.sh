#!/bin/bash

# Configuration
# Run this script from the project root (evoloop)
APP_PATH="frontend/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/EvoLoop.app"
LIB_VOSK="/usr/local/lib/libvosk.dylib"
OUTPUT_DMG="frontend/src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/EvoLoop_0.1.0_aarch64_fixed.dmg"

# Check if App exists
if [ ! -d "$APP_PATH" ]; then
    echo "Error: App bundle not found at $APP_PATH"
    echo "Please run 'npm run tauri build -- --target aarch64-apple-darwin' in frontend/ first."
    exit 1
fi

# Check if libvosk exists
if [ ! -f "$LIB_VOSK" ]; then
    echo "Error: libvosk.dylib not found at $LIB_VOSK"
    exit 1
fi

echo "Found App at $APP_PATH"
echo "Found libvosk at $LIB_VOSK"

# 1. Create Frameworks directory
echo "Creating Frameworks directory..."
mkdir -p "$APP_PATH/Contents/Frameworks"

# 2. Copy Library
echo "Copying libvosk.dylib..."
cp "$LIB_VOSK" "$APP_PATH/Contents/Frameworks/"
chmod 644 "$APP_PATH/Contents/Frameworks/libvosk.dylib"

# 3. Patch the Library ID
echo "Patching library ID..."
install_name_tool -id @rpath/libvosk.dylib "$APP_PATH/Contents/Frameworks/libvosk.dylib"

# 4. Patch the Executable
echo "Patching executable paths..."
EXECUTABLE="$APP_PATH/Contents/MacOS/EvoLoop"
install_name_tool -change libvosk.dylib @rpath/libvosk.dylib "$EXECUTABLE"

# Add rpath if not present (ignoring error if it exists)
install_name_tool -add_rpath @executable_path/../Frameworks "$EXECUTABLE" 2>/dev/null || echo "rpath @executable_path/../Frameworks might already exist or failed to add."

# 5. Re-sign
echo "Re-signing application..."
codesign --force --sign - --verbose=2 --preserve-metadata=identifier,entitlements "$APP_PATH/Contents/Frameworks/libvosk.dylib"
codesign --force --sign - --verbose=2 --preserve-metadata=identifier,entitlements "$EXECUTABLE"
codesign --force --sign - --verbose=2 --deep "$APP_PATH"

echo "App bundle patched successfully."

# 6. Create new DMG
echo "Creating new DMG installer..."
rm -f "$OUTPUT_DMG"
hdiutil create -volname "EvoLoop" -srcfolder "$APP_PATH" -ov -format UDZO "$OUTPUT_DMG"

echo "--------------------------------------------------------"
echo "SUCCESS: New DMG created at:"
echo "$OUTPUT_DMG"
echo "--------------------------------------------------------"
