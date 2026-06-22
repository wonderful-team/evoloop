#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ${NC} $1"; }
ok()    { echo -e "${GREEN}✅${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠️${NC} $1"; }
err()   { echo -e "${RED}❌${NC} $1"; }
step()  { echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
          echo -e "${YELLOW}│ $1${NC}"
          echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"; }
header(){ echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
          echo -e "${BLUE}║  $1${NC}"
          echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

load_env() {
  if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep '^EVOLOOP_APP_DATA_DIR=' "$PROJECT_ROOT/.env" | xargs) 2>/dev/null || true
  fi
  APP_DATA_DIR="${EVOLOOP_APP_DATA_DIR:-$HOME/.evoloop}"
  # Expand leading ~ to $HOME
  APP_DATA_DIR="${APP_DATA_DIR/#\~/$HOME}"
}

# 从 .env 加载构建元数据，支持环境变量覆盖
load_build_metadata() {
  if [ -f "$PROJECT_ROOT/.env" ]; then
    BUILD_NUMBER="${BUILD_NUMBER:-$(grep '^BUILD_NUMBER=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2)}"
    BUILD_TIME="${BUILD_TIME:-$(grep '^BUILD_TIME=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2)}"
    GIT_COMMIT="${GIT_COMMIT:-$(grep '^GIT_COMMIT=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2)}"
    RELEASE_STAGE="${RELEASE_STAGE:-$(grep '^RELEASE_STAGE=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2)}"
  fi

  BUILD_NUMBER="${BUILD_NUMBER:-1}"
  BUILD_TIME="${BUILD_TIME:-$(date +%Y%m%d%H%M%S)}"
  GIT_COMMIT="${GIT_COMMIT:-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")}"
  RELEASE_STAGE="${RELEASE_STAGE:-production}"
}

ensure_xattr() {
  if [ -f "/usr/bin/xattr" ]; then
    export PATH="/usr/bin:$PATH"
  fi
}

ensure_embedding() {
  if [ -z "$APP_DATA_DIR" ]; then
    APP_DATA_DIR="${EVOLOOP_APP_DATA_DIR:-$HOME/.evoloop}"
  fi
  local model_dir="$APP_DATA_DIR/models"
  if [ -d "$model_dir/sentence_transformers" ] || [ -d "$model_dir/huggingface" ]; then
    local found
    found=$(find "$model_dir" -name "*nomic-embed*" -maxdepth 4 2>/dev/null | head -1)
    if [ -n "$found" ]; then
      ok "Embedding model already cached locally"
      return 0
    fi
  fi
  info "Embedding model (nomic-embed) not found locally, downloading..."
  if [ -f "$PROJECT_ROOT/deploy/download_models.sh" ]; then
    chmod +x "$PROJECT_ROOT/deploy/download_models.sh"
    "$PROJECT_ROOT/deploy/download_models.sh" --models "nomic-embed" --skip-funasr-check
    ok "Embedding model ready"
  else
    warn "download_models.sh not found, cannot download embedding model"
  fi
}

download_speech_models() {
  local models_list="${1:-paraformer-zh}"
  if [ -f "$PROJECT_ROOT/deploy/download_models.sh" ]; then
    chmod +x "$PROJECT_ROOT/deploy/download_models.sh"
    "$PROJECT_ROOT/deploy/download_models.sh" --models "$models_list" --skip-funasr-check
  else
    warn "download_models.sh not found, skipping speech model download"
  fi
}

check_numpy() {
  local python_cmd="${1:-python3}"
  local numpy_version
  numpy_version=$($python_cmd -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "")
  if [ -n "$numpy_version" ]; then
    local major
    major=$(echo "$numpy_version" | cut -d. -f1)
    if [ "$major" = "2" ]; then
      warn "NumPy 2.x detected ($numpy_version), downgrading to 1.26.4..."
      if command -v uv &>/dev/null; then
        if [ -n "$VIRTUAL_ENV" ]; then
          uv pip install "numpy==1.26.4" --force-reinstall
        else
          uv pip install "numpy==1.26.4" --force-reinstall --system
        fi
      else
        $python_cmd -m pip install "numpy==1.26.4" --force-reinstall
      fi
      ok "NumPy downgraded to 1.26.4"
    else
      ok "NumPy 1.x already installed ($numpy_version)"
    fi
  fi
}

bundle_models() {
  local app_data_dir="$1"
  local models_dest="$2"
  if [ ! -d "$app_data_dir" ]; then
    warn "No models directory at $app_data_dir, skipping bundle"
    return
  fi
  local has_files
  has_files=$(find "$app_data_dir" -mindepth 1 -maxdepth 1 2>/dev/null | head -1)
  if [ -z "$has_files" ]; then
    warn "Models directory empty at $app_data_dir, skipping bundle"
    return
  fi
  info "Copying models to bundle..."
  rm -rf "$models_dest"
  mkdir -p "$models_dest"
  cp -R "$app_data_dir"/* "$models_dest/"
  local size
  size=$(du -sh "$models_dest" | cut -f1)
  ok "Models copied: $size"
}

patch_tauri_config_for_models() {
  local tauri_conf="$PROJECT_ROOT/frontend/src-tauri/tauri.conf.json"
  cp "$tauri_conf" "${tauri_conf}.backup"
  python3 <<PY
import json
with open("$tauri_conf", "r") as f:
    config = json.load(f)
if "resources" not in config["bundle"]:
    config["bundle"]["resources"] = {}
if isinstance(config["bundle"]["resources"], dict):
    config["bundle"]["resources"]["models"] = "models"
elif isinstance(config["bundle"]["resources"], list):
    config["bundle"]["resources"].append("models")
with open("$tauri_conf", "w") as f:
    json.dump(config, f, indent=2)
print("✅ Tauri config updated to include models")
PY
}

restore_tauri_config() {
  local tauri_conf="$PROJECT_ROOT/frontend/src-tauri/tauri.conf.json"
  if [ -f "${tauri_conf}.backup" ]; then
    mv "${tauri_conf}.backup" "$tauri_conf"
    ok "Restored original Tauri config"
  fi
}

install_frontend_deps() {
  cd "$PROJECT_ROOT/frontend"
  if [ ! -d "node_modules" ]; then
    info "Installing npm dependencies..."
    npm install
  else
    ok "node_modules already exists"
  fi
}

clean_artifacts() {
  header "Cleaning Build Artifacts"
  info "Stopping running processes..."
  pkill -9 -f "evoloop-backend" 2>/dev/null || true
  pkill -9 -f "EvoLoop" 2>/dev/null || true
  sleep 1

  info "Cleaning backend build artifacts..."
  cd "$PROJECT_ROOT/backend"
  rm -rf build dist __pycache__ .pytest_cache

  info "Cleaning frontend build artifacts..."
  cd "$PROJECT_ROOT/frontend"
  rm -rf src-tauri/target dist node_modules/.vite .turbo
  rm -rf src-tauri/models
  mkdir -p src-tauri/models
  touch src-tauri/models/.gitkeep

  cd "$PROJECT_ROOT"
  ok "Clean complete"
}

fix_libvosk() {
  local app_bundle="$1"
  if [ ! -d "$app_bundle" ]; then
    warn "App bundle not found at $app_bundle, skipping libvosk fix"
    return
  fi
  info "Copying libvosk.dylib..."
  mkdir -p "$app_bundle/Contents/Frameworks"
  if [ -f "src-tauri/libs/libvosk.dylib" ]; then
    cp "src-tauri/libs/libvosk.dylib" "$app_bundle/Contents/Frameworks/"
  fi
  install_name_tool -change "libvosk.dylib" "@executable_path/../Frameworks/libvosk.dylib" \
    "$app_bundle/Contents/MacOS/EvoLoop" 2>/dev/null || true
}

sign_bundle() {
  local target="$1"
  codesign --force --deep --sign - "$target" 2>/dev/null || warn "Could not sign $target"
}

create_dmg() {
  local app_bundle="$1"
  local dmg_path="$2"
  info "Creating DMG..."
  mkdir -p "$(dirname "$dmg_path")"
  rm -f "$dmg_path"
  if hdiutil create -volname "EvoLoop" -srcfolder "$app_bundle" -ov -format UDZO "$dmg_path"; then
    ok "DMG created: $(basename "$dmg_path")"
    mkdir -p "$PROJECT_ROOT/deploy/dist"
    mv "$dmg_path" "$PROJECT_ROOT/deploy/dist/"
    ok "DMG moved to deploy/dist/"
  else
    err "DMG creation failed"
  fi
}

show_output() {
  local app_bundle="$1"
  local dmg_glob="$2"
  echo ""
  info "Output locations:"
  if [ -d "$app_bundle" ]; then
    local app_size
    app_size=$(du -sh "$app_bundle" | cut -f1)
    echo "   $(basename "$app_bundle") (${app_size})"
  fi
  if [ -n "$dmg_glob" ]; then
    find "$(dirname "$dmg_glob")" -name "$(basename "$dmg_glob")" -type f 2>/dev/null | while read -r f; do
      local fs
      fs=$(du -h "$f" | cut -f1)
      echo "   $(basename "$f") (${fs})"
    done
  fi
}
