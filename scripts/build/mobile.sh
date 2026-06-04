#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

BUILD_ANDROID=false
BUILD_IOS=false
DOWNLOAD_MODELS=false
GENERATE_ICONS=false
RELEASE=false
BUILD_AAB=false
CLEAN=false
ENVIRONMENT="production"

while [[ $# -gt 0 ]]; do
  case $1 in
    --android|-a) BUILD_ANDROID=true; shift ;;
    --ios|-i) BUILD_IOS=true; shift ;;
    --all) BUILD_ANDROID=true; BUILD_IOS=true; shift ;;
    --download-models|-m) DOWNLOAD_MODELS=true; shift ;;
    --generate-icons|-g) GENERATE_ICONS=true; shift ;;
    --release|-r) RELEASE=true; shift ;;
    --apk) RELEASE=true; BUILD_AAB=false; shift ;;
    --aab) RELEASE=true; BUILD_AAB=true; shift ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --clean|-c) CLEAN=true; shift ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --android, -a         Build Android"
      echo "  --ios, -i             Build iOS"
      echo "  --all                 Build both Android and iOS"
      echo "  --download-models, -m Download Sherpa-ONNX ASR model"
      echo "  --generate-icons, -g  Generate app icons"
      echo "  --release, -r         Release build (signed)"
      echo "  --apk                 Build APK (default for release)"
      echo "  --aab                 Build AAB (Google Play)"
      echo "  --env ENV             Environment: development|production"
      echo "  --clean, -c           Clean before build"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

if [ "$BUILD_ANDROID" = false ] && [ "$BUILD_IOS" = false ]; then
  BUILD_ANDROID=true
  BUILD_IOS=true
fi

init_config "mobile"
load_env

MOBILE_DIR="$PROJECT_ROOT/mobile"

header "Building EvoLoop Mobile"

# 选择移动端环境配置
case "$ENVIRONMENT" in
  development) cp "$MOBILE_DIR/.env.development" "$MOBILE_DIR/.env" ;;
  production)  cp "$MOBILE_DIR/.env.production" "$MOBILE_DIR/.env" ;;
esac
info "环境: $ENVIRONMENT"

echo "  Android:    ${BUILD_ANDROID}"
echo "  iOS:        ${BUILD_IOS}"
echo "  Release:    ${RELEASE}"
echo ""

cd "$MOBILE_DIR"

if [ "$CLEAN" = true ]; then
  step "Cleaning build artifacts"
  cd android && ./gradlew clean 2>/dev/null || true
  cd "$MOBILE_DIR"
  rm -rf node_modules ios/build
  ok "Clean complete"
fi

step "Installing dependencies"
if [ ! -d "node_modules" ]; then
  yarn install --frozen-lockfile
else
  ok "node_modules exists"
fi

if [ "$DOWNLOAD_MODELS" = true ]; then
  step "Downloading Sherpa-ONNX ASR model"
  bash "$MOBILE_DIR/scripts/download-sherpa-asr-model.sh"
fi

if [ "$GENERATE_ICONS" = true ]; then
  step "Generating app icons"
  bash "$MOBILE_DIR/scripts/generate-icons.sh"
fi

if [ "$BUILD_ANDROID" = true ]; then
  step "Building Android"
  cd android
  if [ "$CLEAN" = true ]; then
    ./gradlew clean
  fi
  aab_path=""
  if [ "$RELEASE" = true ]; then
    if [ "$BUILD_AAB" = true ]; then
      info "Building release AAB..."
      ./gradlew bundleRelease
      artifact_path=$(find app/build/outputs/bundle/release -name "*.aab" 2>/dev/null | head -1)
      artifact_type="AAB"
    else
      info "Building release APK..."
      ./gradlew assembleRelease
      artifact_path=$(find app/build/outputs/apk/release -name "*.apk" 2>/dev/null | head -1)
      artifact_type="APK"
    fi
    if [ -n "$artifact_path" ]; then
      mkdir -p "$PROJECT_ROOT/dist"
      cp "$artifact_path" "$PROJECT_ROOT/dist/"
      ok "$artifact_type: $PROJECT_ROOT/dist/$(basename "$artifact_path")"
    fi
  else
    info "Building debug APK..."
    ./gradlew assembleDebug
    apk_path=$(find app/build/outputs/apk/debug -name "*.apk" 2>/dev/null | head -1)
    if [ -n "$apk_path" ]; then
      ok "APK: $apk_path"
      mkdir -p "$PROJECT_ROOT/dist"
      cp "$apk_path" "$PROJECT_ROOT/dist/"
      ok "APK copied to $PROJECT_ROOT/dist/$(basename "$apk_path")"
    fi
  fi
  cd "$MOBILE_DIR"
  ok "Android build complete"
fi

if [ "$BUILD_IOS" = true ]; then
  step "Building iOS"
  cd ios
  if [ ! -d "Pods" ]; then
    info "Installing CocoaPods..."
    pod install --repo-update
  fi

  if [ "$RELEASE" = true ]; then
    info "Building release IPA..."
    xcodebuild -workspace EvoLoopMobile.xcworkspace \
      -scheme EvoLoopMobile \
      -configuration Release \
      -archivePath "$PROJECT_ROOT/dist/EvoLoopMobile.xcarchive" \
      archive | xcpretty
    xcodebuild -exportArchive \
      -archivePath "$PROJECT_ROOT/dist/EvoLoopMobile.xcarchive" \
      -exportPath "$PROJECT_ROOT/dist" \
      -exportOptionsPlist "$MOBILE_DIR/ios/ExportOptions.plist" 2>/dev/null || \
    xcodebuild -exportArchive \
      -archivePath "$PROJECT_ROOT/dist/EvoLoopMobile.xcarchive" \
      -exportPath "$PROJECT_ROOT/dist" \
      -exportOptionsPlist "$MOBILE_DIR/ios/ExportOptions.plist" 2>/dev/null
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
  cd "$MOBILE_DIR"
  ok "iOS build complete"
fi

ok "Mobile build complete!"
echo ""
info "Output:"
echo "  Android: $MOBILE_DIR/android/app/build/outputs/"
echo "  iOS:     $MOBILE_DIR/ios/build/"
if [ "$RELEASE" = true ]; then
  echo "  Dist:    $PROJECT_ROOT/dist/"
fi
