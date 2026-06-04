#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/build/common.sh"

show_usage() {
  echo "EvoLoop Build System"
  echo ""
  echo "Usage: $0 <platform> [options]"
  echo ""
  echo "Platforms:"
  echo "  all                  Build for all supported platforms"
  echo "  macos-arm64          macOS Apple Silicon (M1/M2/M3)"
  echo "  macos-x86_64         macOS Intel"
  echo "  windows              Windows x86_64"
  echo "  mobile               React Native (Android/iOS)"
  echo "  server-frontend      Static frontend for server deployment"
  echo "  current              Auto-detect and build for current platform"
  echo ""
  echo "Options:"
  echo "  --dev, -d                 Run in development mode"
  echo "  --env ENV                 Build environment: development|production"
  echo "  --with-models, -m         Include pre-downloaded models in the bundle"
  echo "  --download-models [LIST]  Download models before building"
  echo "  --clean, -c               Clean build artifacts before building"
  echo "  --init-config             Initialize .env from platform config template"
  echo "  --help, -h                Show this help message"
  echo ""
  echo "Examples:"
  echo "  $0 macos-arm64 --init-config              Init .env + build for Apple Silicon"
  echo "  $0 macos-arm64 --with-models              Build with models"
  echo "  $0 current --dev                          Dev mode for current platform"
  echo "  $0 macos-x86_64 --download-models         Build Intel Mac with model download"
  echo ""
  echo "Configuration templates:"
  echo "  config/server/.env.example       CentOS deployment"
  echo "  config/desktop/.env.example      Tauri desktop client"
  echo "  config/mobile/.env.example       React Native mobile"
}

# Check for --help before platform arg
for arg in "$@"; do
  if [ "$arg" = "--help" ] || [ "$arg" = "-h" ]; then
    show_usage
    exit 0
  fi
done

if [ $# -lt 1 ]; then
  show_usage
  exit 1
fi

PLATFORM="$1"
shift

BUILD_ARGS=()
INIT_CONFIG=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --dev|-d) BUILD_ARGS+=("--dev"); shift ;;
    --with-models|-m) BUILD_ARGS+=("--with-models"); shift ;;
    --download-models)
      BUILD_ARGS+=("--download-models")
      if [[ $2 != --* ]] && [[ -n $2 ]]; then BUILD_ARGS+=("$2"); shift 2; else shift; fi
      ;;
    --clean|-c) BUILD_ARGS+=("--clean"); shift ;;
    --init-config) INIT_CONFIG=true; shift ;;
    --help|-h) show_usage; exit 0 ;;
    *) BUILD_ARGS+=("$1"); shift ;;  # pass through to platform script
  esac
done

detect_current_platform() {
  case "$(uname -s)" in
    Darwin)
      case "$(uname -m)" in
        arm64) echo "macos-arm64" ;;
        x86_64) echo "macos-x86_64" ;;
      esac
      ;;
    MINGW*|MSYS*) echo "windows" ;;
    *) err "Unknown platform: $(uname -s)"; exit 1 ;;
  esac
}

# Initialize config if requested
if [ "$INIT_CONFIG" = true ]; then
  case "$PLATFORM" in
    macos-arm64|macos-x86_64|current) init_config "desktop" ;;
    windows) init_config "desktop" ;;
    server-frontend) init_config "server" ;;
    all) init_config "desktop" ;;
  esac
fi

build_platform() {
  local platform_script
  case "$1" in
    macos-arm64) platform_script="$SCRIPT_DIR/build/macos-arm64.sh" ;;
    macos-x86_64) platform_script="$SCRIPT_DIR/build/macos-x86_64.sh" ;;
    windows) platform_script="$SCRIPT_DIR/build/windows-x86_64.sh" ;;
    mobile) platform_script="$SCRIPT_DIR/build/mobile.sh" ;;
    server-frontend) platform_script="$SCRIPT_DIR/build/server-frontend.sh" ;;
    current) platform_script="$SCRIPT_DIR/build/$(detect_current_platform).sh" ;;
    *)
      err "Unknown platform: $1"
      show_usage
      exit 1
      ;;
  esac

  if [ ! -f "$platform_script" ]; then
    err "Build script not found: $platform_script"
    exit 1
  fi

  header "Building for: $1"
  bash "$platform_script" "${BUILD_ARGS[@]}"
  ok "Platform build complete: $1"
}

case "$PLATFORM" in
  all)
    build_platform "macos-arm64"
    build_platform "macos-x86_64"
    build_platform "windows"
    ok "All platform builds complete!"
    ;;
  macos-arm64|macos-x86_64|windows|mobile|server-frontend|current)
    build_platform "$PLATFORM"
    ;;
  *)
    err "Unknown platform: $PLATFORM"
    show_usage
    exit 1
    ;;
esac
