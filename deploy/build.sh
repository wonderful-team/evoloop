#!/bin/bash
# EvoLoop Build System
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/build/common.sh"

show_usage() {
  echo "EvoLoop Build System"
  echo ""
  echo "Usage: $0 [platform] [options]"
  echo ""
  echo "If no platform is specified, an interactive menu will be shown."
  echo ""
  echo "Platforms:"
  echo "  all                  Build for all supported platforms"
  echo "  macos-arm64          macOS Apple Silicon (M1/M2/M3)"
  echo "  macos-x86_64         macOS Intel"
  echo "  windows              Windows x86_64"
  echo "  android              React Native (Android)"
  echo "  ios                  React Native (iOS)"
  echo "  mobile               React Native (Android & iOS & HarmonyOS)"
  echo "  harmony              HarmonyOS HAP"
  echo "  web                  Static frontend for server deployment"
  echo "  current              Auto-detect and build for current platform"
  echo ""
  echo "Options:"
  echo "  --dev, -d                 Run in development mode"
  echo "  --env ENV                 Build environment: development|production"
  echo "  --env-file FILE           Use specified env file (e.g. .env.prod.desktop)"
  echo "  --with-models, -m         Include pre-downloaded models in the bundle"
  echo "  --download-models [LIST]  Download models before building"
  echo "  --clean, -c               Clean build artifacts before building"
  echo "  --help, -h                Show this help message"
  echo ""
}

for arg in "$@"; do
  if [ "$arg" = "--help" ] || [ "$arg" = "-h" ]; then
    show_usage
    exit 0
  fi
done

INTERACTIVE="false"
ENVIRONMENT="production"
WITH_MODELS="false"
ENV_FILE=""
TARGETS=()
BUILD_ARGS=()

if [ $# -eq 0 ]; then
  INTERACTIVE="true"
else
  # Parse arguments
  PLATFORM="$1"
  if [[ "$PLATFORM" != -* ]]; then
    TARGETS=("$PLATFORM")
    shift
  fi

  while [[ $# -gt 0 ]]; do
    case $1 in
      --dev|-d) ENVIRONMENT="development"; BUILD_ARGS+=("--dev"); shift ;;
      --env=*) ENVIRONMENT="${1#*=}"; BUILD_ARGS+=("--env" "$ENVIRONMENT"); shift ;;
      --env) ENVIRONMENT="$2"; BUILD_ARGS+=("--env" "$ENVIRONMENT"); shift 2 ;;
      --env-file) ENV_FILE="$2"; BUILD_ARGS+=("--env-file" "$ENV_FILE"); shift 2 ;;
      --env-file=*) ENV_FILE="${1#*=}"; BUILD_ARGS+=("--env-file" "$ENV_FILE"); shift ;;
      --prod|--production) ENVIRONMENT="production"; BUILD_ARGS+=("--env" "production"); shift ;;
      --with-models|-m) WITH_MODELS="true"; BUILD_ARGS+=("--with-models"); shift ;;
      --download-models)
        BUILD_ARGS+=("--download-models")
        if [[ $2 != --* ]] && [[ -n $2 ]]; then BUILD_ARGS+=("$2"); shift 2; else shift; fi
        ;;
      --clean|-c) BUILD_ARGS+=("--clean"); shift ;;
      *) BUILD_ARGS+=("$1"); shift ;;
    esac
  done
fi

if [ "$INTERACTIVE" = "true" ]; then
  echo ""
  echo "╔══════════════════════════════════╗"
  echo "║    EvoLoop 构建助手              ║"
  echo "╚══════════════════════════════════╝"
  echo ""
  echo "请选择构建环境:"
  echo "  1) 生产环境 (production)"
  echo "  2) 开发环境 (development)"
  echo ""
  read -p "输入 1 或 2 [默认: 1]: " env_choice
  case "$env_choice" in
    2|dev|development) ENVIRONMENT="development"; BUILD_ARGS+=("--dev") ;;
    *) ENVIRONMENT="production"; BUILD_ARGS+=("--env" "production") ;;
  esac

  echo ""
  echo "请选择构建目标（可多选，逗号分隔，如: 1,3,4）:"
  echo "  1) 服务端前端 (web)"
  echo "  2) 桌面端 arm64 (macOS Apple Silicon)"
  echo "  3) 桌面端 x86_64 (macOS Intel)"
  echo "  4) 移动端 Android"
  echo "  5) 移动端 iOS"
  echo "  6) 鸿蒙 HarmonyOS"
  echo "  7) 移动端全部 (Android + iOS + HarmonyOS)"
  echo "  8) 全部"
  echo ""
  read -p "输入编号 [默认: 1]: " targets_input

  if [ -z "$targets_input" ] || [[ "$targets_input" == "1" ]]; then
    TARGETS=("web")
  else
    IFS=',' read -ra SELECTED <<< "$targets_input"
    for s in "${SELECTED[@]}"; do
      s=$(echo "$s" | xargs)
      case "$s" in
        8|all) TARGETS=("all"); break ;;
        1) TARGETS+=("web") ;;
        2) TARGETS+=("macos-arm64") ;;
        3) TARGETS+=("macos-x86_64") ;;
        4) TARGETS+=("android") ;;
        5) TARGETS+=("ios") ;;
        6) TARGETS+=("harmony") ;;
        7) TARGETS+=("mobile") ;;
      esac
    done
  fi

  NEEDS_MODEL_PROMPT="false"
  for t in "${TARGETS[@]}"; do
    if [[ "$t" == "macos-arm64" || "$t" == "macos-x86_64" || "$t" == "windows" || "$t" == "all" ]]; then
      NEEDS_MODEL_PROMPT="true"
      break
    fi
  done

  if [ "$NEEDS_MODEL_PROMPT" == "true" ]; then
    echo ""
    echo "是否将模型一起打包进桌面端应用中？ (体积较大，但可离线使用)"
    echo "  1) 否 (默认)"
    echo "  2) 是"
    echo ""
    read -p "输入 1 或 2 [默认: 1]: " model_choice
    case "$model_choice" in
      2|yes|y|Y|Yes) WITH_MODELS="true"; BUILD_ARGS+=("--with-models") ;;
      *) WITH_MODELS="false" ;;
    esac
  fi

  ANDROID_FORMAT="--apk"  # default for non-interactive
  NEEDS_MOBILE_PROMPT="false"
  NEEDS_ANDROID_PROMPT="false"
  for t in "${TARGETS[@]}"; do
    if [[ "$t" == "android" || "$t" == "mobile" || "$t" == "all" ]]; then
      NEEDS_ANDROID_PROMPT="true"
      NEEDS_MOBILE_PROMPT="true"
    elif [[ "$t" == "ios" ]]; then
      NEEDS_MOBILE_PROMPT="true"
    fi
  done

  ANDROID_FORMAT="--apk"
  if [ "$NEEDS_ANDROID_PROMPT" == "true" ]; then
    echo ""
    echo "请选择 Android 产物格式:"
    echo "  1) APK (适合本地安装, 默认)"
    echo "  2) AAB (适合上架 Google Play)"
    echo ""
    read -p "输入 1 或 2 [默认: 1]: " android_choice
    case "$android_choice" in
      2) ANDROID_FORMAT="--aab" ;;
      *) ANDROID_FORMAT="--apk" ;;
    esac
  fi

  if [ "$NEEDS_MOBILE_PROMPT" == "true" ]; then
    echo ""
    echo "移动端附属项配置:"
    echo "是否下载/打包移动端离线语音 ASR 模型？"
    echo "  1) 否 (默认)"
    echo "  2) 是"
    read -p "输入 1 或 2 [默认: 1]: " mobile_model_choice
    if [[ "$mobile_model_choice" == "2" || "$mobile_model_choice" == "y" || "$mobile_model_choice" == "Y" ]]; then
      BUILD_ARGS+=("--download-models")
    fi
    
    echo "是否根据 master_logo 重新生成各尺寸 App 图标？"
    echo "  1) 否 (默认)"
    echo "  2) 是"
    read -p "输入 1 或 2 [默认: 1]: " mobile_icon_choice
    if [[ "$mobile_icon_choice" == "2" || "$mobile_icon_choice" == "y" || "$mobile_icon_choice" == "Y" ]]; then
      BUILD_ARGS+=("--generate-icons")
    fi
  fi
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
  err "No target specified."
  show_usage
  exit 1
fi

# 如果指定了 --env-file，先复制到根目录 .env
copy_env_file() {
  if [ -n "$ENV_FILE" ]; then
    local src="$PROJECT_ROOT/$ENV_FILE"
    if [ ! -f "$src" ]; then
      err "Env file not found: $src"
      exit 1
    fi
    cp "$src" "$PROJECT_ROOT/.env"
    ok "Copied env file: $ENV_FILE → .env"
  fi
}

echo ""
echo "🔴 环境: $ENVIRONMENT"
echo "📦 目标: ${TARGETS[*]}"
echo ""

cd "$PROJECT_ROOT"
copy_env_file

detect_current_platform() {
  case "$(uname -s)" in
    Darwin)
      case "$(uname -m)" in
        arm64) echo "macos-arm64" ;;
        x86_64) echo "macos-x86_64" ;;
      esac
      ;;
    MINGW*|MSYS*) echo "windows-x86_64" ;;
    *) err "Unknown platform: $(uname -s)"; exit 1 ;;
  esac
}

build_platform() {
  local target="$1"
  echo "═══════════════════════════════════════"
  echo "  开始构建: $target ($ENVIRONMENT)"
  echo "═══════════════════════════════════════"
  echo ""

  local platform_script
  case "$target" in
    macos-arm64) platform_script="$SCRIPT_DIR/build/macos-arm64.sh" ;;
    macos-x86_64) platform_script="$SCRIPT_DIR/build/macos-x86_64.sh" ;;
    windows) platform_script="$SCRIPT_DIR/build/windows-x86_64.sh" ;;
    mobile)
      build_platform "android"
      build_platform "ios"
      build_platform "harmony"
      return
      ;;
    android)
      platform_script="$SCRIPT_DIR/build/mobile.sh"
      BUILD_ARGS+=("--android" "--release")
      if [ -n "$ANDROID_FORMAT" ]; then
        BUILD_ARGS+=("$ANDROID_FORMAT")
      fi
      ;;
    ios) platform_script="$SCRIPT_DIR/build/mobile.sh"; BUILD_ARGS+=("--ios" "--release") ;;
    harmony) platform_script="$SCRIPT_DIR/build/harmony.sh" ;;
    web) platform_script="$SCRIPT_DIR/build/web.sh" ;;
    current) platform_script="$SCRIPT_DIR/build/$(detect_current_platform).sh" ;;
    all)
      build_platform "macos-arm64"
      build_platform "macos-x86_64"
      build_platform "windows"
      build_platform "harmony"
      build_platform "web"
      return
      ;;
    *)
      err "Unknown target: $target"
      exit 1
      ;;
  esac

  if [ ! -f "$platform_script" ]; then
    err "Build script not found: $platform_script"
    exit 1
  fi

  bash "$platform_script" "${BUILD_ARGS[@]}"
  ok "Platform build complete: $target"
}

for target in "${TARGETS[@]}"; do
  build_platform "$target"
done

echo ""
echo "✅ 全部构建完成"
