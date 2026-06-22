#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || grep ^APP_VERSION= "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 || echo "0.1.0")

BUILD_ANDROID=false
BUILD_IOS=false
DOWNLOAD_MODELS=false
GENERATE_ICONS=false
RELEASE=false
BUILD_AAB=false
CLEAN=false
ENVIRONMENT="production"
ENV_FILE=""

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
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --env-file=*) ENV_FILE="${1#*=}"; shift ;;
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
      echo "  --env-file FILE       Use specified env file (e.g. .env.prod.desktop)"
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

load_env
header "Building EvoLoop Mobile"
MOBILE_DIR="$PROJECT_ROOT/mobile"

echo "  Android:    ${BUILD_ANDROID}"
echo "  iOS:        ${BUILD_IOS}"
echo "  Release:    ${RELEASE}"
echo ""

cd "$MOBILE_DIR"

# 如果指定了 --env-file，先复制到根目录 .env
if [ -n "$ENV_FILE" ]; then
  env_file_path="$PROJECT_ROOT/$ENV_FILE"
  if [ ! -f "$env_file_path" ]; then
    err "Env file not found: $env_file_path"
    exit 1
  fi
  cp "$env_file_path" "$PROJECT_ROOT/.env"
  ok "Copied env file: $ENV_FILE → .env"
fi

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
  bash "$PROJECT_ROOT/deploy/mobile-download-sherpa-asr-model.sh"
fi

if [ "$GENERATE_ICONS" = true ]; then
  step "Generating app icons"
  bash "$PROJECT_ROOT/deploy/mobile-generate-icons.sh"
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
      mkdir -p "$PROJECT_ROOT/deploy/dist"
      local dest_name
      if [ "$BUILD_AAB" = true ]; then
        dest_name="Evoloop_mobile_${APP_VERSION}.aab"
      else
        dest_name="Evoloop_mobile_${APP_VERSION}.apk"
      fi
      mv "$artifact_path" "$PROJECT_ROOT/deploy/dist/$dest_name"
      ok "$artifact_type: $PROJECT_ROOT/deploy/dist/$dest_name"
    fi
  else
    info "Building debug APK..."
    ./gradlew assembleDebug
    apk_path=$(find app/build/outputs/apk/debug -name "*.apk" 2>/dev/null | head -1)
    if [ -n "$apk_path" ]; then
      ok "APK: $apk_path"
      mkdir -p "$PROJECT_ROOT/deploy/dist"
      local debug_dest_name="Evoloop_mobile_${APP_VERSION}-debug.apk"
      mv "$apk_path" "$PROJECT_ROOT/deploy/dist/$debug_dest_name"
      ok "APK moved to $PROJECT_ROOT/deploy/dist/$debug_dest_name"
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
      -archivePath "$PROJECT_ROOT/deploy/dist/EvoLoopMobile_${APP_VERSION}.xcarchive" \
      archive | xcpretty
    xcodebuild -exportArchive \
      -archivePath "$PROJECT_ROOT/deploy/dist/EvoLoopMobile_${APP_VERSION}.xcarchive" \
      -exportPath "$PROJECT_ROOT/deploy/dist" \
      -exportOptionsPlist "$MOBILE_DIR/ios/ExportOptions.plist" 2>/dev/null || \
    xcodebuild -exportArchive \
      -archivePath "$PROJECT_ROOT/deploy/dist/EvoLoopMobile_${APP_VERSION}.xcarchive" \
      -exportPath "$PROJECT_ROOT/deploy/dist" \
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
  echo "  Dist:    $PROJECT_ROOT/deploy/dist/"
fi
