#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || echo "0.1.0")
RELEASE=false
CLEAN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --release|-r) RELEASE=true; shift ;;
    --clean|-c) CLEAN=true; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --release, -r     Release build"
      echo "  --clean, -c       Clean before build"
      echo "  --help, -h        Show this help"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

MOBILE_DIR="$PROJECT_ROOT/mobile"
cd "$MOBILE_DIR/ios"

if [ ! -d "Pods" ]; then
  info "Installing CocoaPods..."
  pod install --repo-update
fi

if [ "$RELEASE" = true ]; then
  info "Building release IPA..."
  xcodebuild -workspace EvoLoopMobile.xcworkspace \
    -scheme EvoLoopMobile \
    -configuration Release \
    -archivePath "$PROJECT_ROOT/deploy/dist/EvoLoopMobile_${APP_VERSION}.xcarchive" \
    archive | xcpretty 2>/dev/null || \
  xcodebuild -workspace EvoLoopMobile.xcworkspace \
    -scheme EvoLoopMobile \
    -configuration Release \
    -archivePath "$PROJECT_ROOT/deploy/dist/EvoLoopMobile_${APP_VERSION}.xcarchive" \
    archive

  xcodebuild -exportArchive \
    -archivePath "$PROJECT_ROOT/deploy/dist/EvoLoopMobile_${APP_VERSION}.xcarchive" \
    -exportPath "$PROJECT_ROOT/deploy/dist" \
    -exportOptionsPlist "$MOBILE_DIR/ios/ExportOptions.plist" 2>/dev/null || \
  xcodebuild -exportArchive \
    -archivePath "$PROJECT_ROOT/deploy/dist/EvoLoopMobile_${APP_VERSION}.xcarchive" \
    -exportPath "$PROJECT_ROOT/deploy/dist" \
    -exportOptionsPlist "$MOBILE_DIR/ios/ExportOptions.plist"
else
  info "Building debug app..."
  xcodebuild -workspace EvoLoopMobile.xcworkspace \
    -scheme EvoLoopMobile \
    -configuration Debug \
    -sdk iphonesimulator \
    -derivedDataPath build | xcpretty 2>/dev/null || \
  xcodebuild -workspace EvoLoopMobile.xcworkspace \
    -scheme EvoLoopMobile \
    -configuration Debug \
    -sdk iphonesimulator \
    -derivedDataPath build
fi

ok "iOS build complete"
