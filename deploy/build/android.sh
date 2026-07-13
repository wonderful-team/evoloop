#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || echo "0.1.0")
BUILD_AAB=false
RELEASE=false
CLEAN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --release|-r) RELEASE=true; shift ;;
    --apk) RELEASE=true; BUILD_AAB=false; shift ;;
    --aab) RELEASE=true; BUILD_AAB=true; shift ;;
    --clean|-c) CLEAN=true; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --release, -r     Release build (signed)"
      echo "  --apk             Build APK (default)"
      echo "  --aab             Build AAB (Google Play)"
      echo "  --clean, -c       Clean before build"
      echo "  --help, -h        Show this help"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

MOBILE_DIR="$PROJECT_ROOT/mobile"
cd "$MOBILE_DIR/android"

if [ "$CLEAN" = true ]; then
  ./gradlew clean
fi

if [ "$RELEASE" = true ]; then
  if [ "$BUILD_AAB" = true ]; then
    info "Building release AAB..."
    ./gradlew bundleRelease
    artifact_path=$(find app/build/outputs/bundle/release -name "*.aab" 2>/dev/null | head -1)
    ext="aab"
  else
    info "Building release APK..."
    ./gradlew assembleRelease
    artifact_path=$(find app/build/outputs/apk/release -name "*.apk" 2>/dev/null | head -1)
    ext="apk"
  fi
else
  info "Building debug APK..."
  ./gradlew assembleDebug
  artifact_path=$(find app/build/outputs/apk/debug -name "*.apk" 2>/dev/null | head -1)
  ext="apk"
fi

if [ -n "$artifact_path" ]; then
  mkdir -p "$PROJECT_ROOT/deploy/dist"
  dest_name="Evoloop_mobile_${APP_VERSION}.${ext}"
  mv "$artifact_path" "$PROJECT_ROOT/deploy/dist/$dest_name"
  ok "$(echo $ext | tr '[:lower:]' '[:upper:]'): $PROJECT_ROOT/deploy/dist/$dest_name"
else
  err "Android build artifact not found"
  exit 1
fi
