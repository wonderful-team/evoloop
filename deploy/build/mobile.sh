#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || grep -hs ^APP_VERSION= "$PROJECT_ROOT/mobile/.env" "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 | head -1 || echo "0.1.0")

BUILD_ANDROID=false
BUILD_IOS=false
BUILD_HARMONY=false
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
    --harmony) BUILD_HARMONY=true; shift ;;
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
      echo "  --harmony             Build HarmonyOS"
      echo "  --all                 Build Android + iOS"
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

if [ "$BUILD_ANDROID" = false ] && [ "$BUILD_IOS" = false ] && [ "$BUILD_HARMONY" = false ]; then
  BUILD_ANDROID=true
  BUILD_IOS=true
fi

load_env
header "Building EvoLoop Mobile"
MOBILE_DIR="$PROJECT_ROOT/mobile"

echo "  Android:   ${BUILD_ANDROID}"
echo "  iOS:       ${BUILD_IOS}"
echo "  HarmonyOS: ${BUILD_HARMONY}"
echo "  Release:   ${RELEASE}"
echo ""

cd "$MOBILE_DIR"

# 移动端通过 react-native-dotenv 读取 mobile/.env，这是配置的唯一来源。
# 注意：不要传 --env-file=.env.prod.desktop（桌面 sidecar，会指向 127.0.0.1）。
if [ -n "$ENV_FILE" ]; then
  env_file_path="$PROJECT_ROOT/$ENV_FILE"
  if [ ! -f "$env_file_path" ]; then
    err "Env file not found: $env_file_path"
    exit 1
  fi
  if [[ "$ENV_FILE" == *"desktop"* ]]; then
    err "Refusing to use desktop env ($ENV_FILE) for mobile build."
    err "Mobile reads mobile/.env; provide a mobile config instead."
    exit 1
  fi
  cp "$env_file_path" "$MOBILE_DIR/.env"
  ok "Copied env file: $ENV_FILE → mobile/.env"
fi

if [ ! -f "$MOBILE_DIR/.env" ]; then
  err "mobile/.env not found. Create it from your mobile config before building."
  exit 1
fi

if grep -qE "EVOCLOUD_API_URL=http://(127\.0\.0\.1|localhost)" "$MOBILE_DIR/.env"; then
  warn "mobile/.env points EVOCLOUD_API_URL at localhost — this looks like a desktop config."
  warn "The packaged app will not be able to reach a backend on a real device."
fi

if [ "$CLEAN" = true ]; then
  step "Cleaning build artifacts"
  cd android && ./gradlew clean 2>/dev/null || true
  cd "$MOBILE_DIR"
  rm -rf node_modules ios/build
  ok "Clean complete"
fi

header "Phase 1: Dependencies"
step "Installing dependencies"
if [ ! -d "node_modules" ]; then
  yarn install --frozen-lockfile
else
  ok "node_modules exists"
fi

header "Phase 2: Assets (download / generate before build)"
if [ "$DOWNLOAD_MODELS" = true ]; then
  step "Downloading Sherpa-ONNX ASR model"
  bash "$PROJECT_ROOT/deploy/mobile-download-sherpa-asr-model.sh"
fi

if [ "$GENERATE_ICONS" = true ]; then
  step "Generating app icons"
  bash "$PROJECT_ROOT/deploy/mobile-generate-icons.sh"
fi

ANDROID_ARGS=()
if [ "$RELEASE" = true ]; then
  ANDROID_ARGS+=("--release")
  [ "$BUILD_AAB" = true ] && ANDROID_ARGS+=("--aab") || ANDROID_ARGS+=("--apk")
fi
[ "$CLEAN" = true ] && ANDROID_ARGS+=("--clean")

IOS_ARGS=()
[ "$RELEASE" = true ] && IOS_ARGS+=("--release")
[ "$CLEAN" = true ] && IOS_ARGS+=("--clean")

if [ "$BUILD_ANDROID" = true ]; then
  header "Phase 3: Building Android"
  bash "$SCRIPT_DIR/android.sh" "${ANDROID_ARGS[@]}"
  ok "Android build complete"
fi

if [ "$BUILD_IOS" = true ]; then
  header "Phase 4: Building iOS"
  bash "$SCRIPT_DIR/ios.sh" "${IOS_ARGS[@]}"
  ok "iOS build complete"
fi

if [ "$BUILD_HARMONY" = true ]; then
  header "Phase 5: Building HarmonyOS"
  bash "$SCRIPT_DIR/harmony.sh" --env "$ENVIRONMENT"
  ok "HarmonyOS build complete"
fi

ok "Mobile build complete!"
echo ""
info "Output:"
echo "  Android: $MOBILE_DIR/android/app/build/outputs/"
echo "  iOS:     $MOBILE_DIR/ios/build/"
if [ "$RELEASE" = true ]; then
  echo "  Dist:    $PROJECT_ROOT/deploy/dist/"
fi
