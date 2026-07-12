#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ENVIRONMENT="production"
ENV_FILE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --dev|-d) ENVIRONMENT="development"; shift ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --env-file=*) ENV_FILE="${1#*=}"; shift ;;
    --with-packager) shift ;;  # kept for backward compat, no-op
    --help|-h)
      echo "Usage: $0 [options]"
      echo "  --dev, -d             Development mode"
      echo "  --env ENV             Build environment: development|production"
      echo "  --env-file FILE       Use specified env file (e.g. .env.prod.desktop)"
      echo "  --with-packager       (obsolete) kept for backward compatibility"
      echo "  --help, -h            Show this help"
      exit 0
      ;;
    *) err "Unknown: $1"; exit 1 ;;
  esac
done

# 如果指定了 --env-file，同步到所有需要的 .env 位置
if [ -n "$ENV_FILE" ]; then
  env_file_path="$PROJECT_ROOT/$ENV_FILE"
  if [ ! -f "$env_file_path" ]; then
    err "Env file not found: $env_file_path"
    exit 1
  fi
  if [[ "$ENV_FILE" == *"desktop"* ]]; then
    err "Refusing to use desktop env ($ENV_FILE) for HarmonyOS build."
    err "HarmonyOS reads mobile/.env; provide a mobile config instead."
    exit 1
  fi
  cp "$env_file_path" "$PROJECT_ROOT/.env"
  cp "$env_file_path" "$PROJECT_ROOT/mobile/.env"
  ok "Copied env file: $ENV_FILE → .env (root + mobile)"
fi

APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || grep -hs ^APP_VERSION= "$PROJECT_ROOT/mobile/.env" "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 | head -1 || echo "0.1.0")

# =============================================================================
# Detect DevEco Studio (provides HOS SDK + hvigor toolchain)
# =============================================================================
DEVELO_STUDIO=""
for candidate in "/Applications/DevEco-Studio.app" "$HOME/Applications/DevEco-Studio.app"; do
  if [ -d "$candidate" ]; then
    DEVELO_STUDIO="$candidate"
    break
  fi
done

if [ -z "$DEVELO_STUDIO" ]; then
  err "DevEco Studio not found."
  err "Please install DevEco Studio from https://developer.huawei.com/consumer/cn/download/"
  exit 1
fi

HOS_SDK_HOME="${HOS_SDK_HOME:-$DEVELO_STUDIO/Contents/sdk}"
HVIGORW="$DEVELO_STUDIO/Contents/tools/hvigor/bin/hvigorw"

if [ ! -d "$HOS_SDK_HOME" ]; then
  err "HOS SDK not found at: $HOS_SDK_HOME"
  err "Open DevEco Studio, go to Settings → SDK Manager, and install the HarmonyOS SDK."
  exit 1
fi

if [ ! -f "$HVIGORW" ]; then
  err "hvigorw not found at: $HVIGORW"
  err "This usually means DevEco Studio installation is incomplete."
  exit 1
fi

export HOS_SDK_HOME

header "Building EvoLoop for HarmonyOS"

echo "  Environment:  ${ENVIRONMENT}"
echo "  App Version:  ${APP_VERSION}"
echo "  DevEco Studio: ${DEVELO_STUDIO}"
echo "  HOS SDK:       ${HOS_SDK_HOME}"
echo ""

cd "$PROJECT_ROOT/mobile"

step "Installing npm dependencies"
if [ ! -d "node_modules" ]; then
  yarn install --frozen-lockfile
else
  ok "node_modules exists"
fi

HARMONY_DIR="$PROJECT_ROOT/mobile/harmony"

# ---------------------------------------------------------------------------
# 1. Bundle JS → Hermes bytecode
# ---------------------------------------------------------------------------
step "Bundling JavaScript (Hermes)"
if [ "$ENVIRONMENT" = "development" ]; then
  npx react-native bundle-harmony \
    --js-engine hermes \
    --bundle-output "$HARMONY_DIR/entry/src/main/resources/rawfile/hermes_bundle.hbc" \
    --dev true
else
  npx react-native bundle-harmony \
    --js-engine hermes \
    --bundle-output "$HARMONY_DIR/entry/src/main/resources/rawfile/hermes_bundle.hbc" \
    --dev false
fi
ok "JS bundle ready"

# ---------------------------------------------------------------------------
# 2. Build HAP via hvigorw (from DevEco Studio)
# ---------------------------------------------------------------------------
step "Building HAP"
cd "$HARMONY_DIR"
if [ "$ENVIRONMENT" = "development" ]; then
  "$HVIGORW" assembleHap -p mode=debug --no-daemon
else
  "$HVIGORW" assembleHap -p mode=release --no-daemon
fi
ok "HAP build complete"
cd "$PROJECT_ROOT/mobile"

# ---------------------------------------------------------------------------
# 3. Collect signed HAP artifact
# ---------------------------------------------------------------------------
step "Collecting HAP artifact"
HAP_OUTPUT_DIR="$HARMONY_DIR/entry/build/default/outputs/default"

# 优先取 signed 版本，fallback 到 unsigned
HAP_FILE=$(find "$HAP_OUTPUT_DIR" -name "*-signed.hap" -type f 2>/dev/null | head -1)
if [ -z "$HAP_FILE" ]; then
  HAP_FILE=$(find "$HAP_OUTPUT_DIR" -name "*.hap" -type f 2>/dev/null | head -1)
fi

if [ -z "$HAP_FILE" ]; then
  err "No HAP file found in $HAP_OUTPUT_DIR"
  exit 1
fi

DEST_NAME="EvoLoop_${APP_VERSION}.hap"
mkdir -p "$PROJECT_ROOT/deploy/dist"
cp "$HAP_FILE" "$PROJECT_ROOT/deploy/dist/$DEST_NAME"
ok "HAP copied → $PROJECT_ROOT/deploy/dist/$DEST_NAME"

# 同步到 member-center bundle 目录（可选，通过 MEMBER_CENTER_BUNDLE_DIR 环境变量指定）
if [ -n "$MEMBER_CENTER_BUNDLE_DIR" ]; then
  mkdir -p "$MEMBER_CENTER_BUNDLE_DIR"
  cp "$HAP_FILE" "$MEMBER_CENTER_BUNDLE_DIR/$DEST_NAME"
  ok "HAP synced → $MEMBER_CENTER_BUNDLE_DIR/$DEST_NAME"
fi

cd "$PROJECT_ROOT"
ok "HarmonyOS build complete!"
