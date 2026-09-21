#!/bin/bash
set -euo pipefail

# Prepare core bundled models (action_classifier, domain_classifier, KWS)
# and place them into frontend/src-tauri/models/ so they are shipped inside
# the Tauri app bundle (Resources/models/).
#
# This script should be called before Tauri build when --with-models is enabled.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUNDLE_MODELS_DIR="$PROJECT_ROOT/frontend/src-tauri/models"

KWS_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01.tar.bz2"
KWS_DIR_NAME="sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"

mkdir -p "$BUNDLE_MODELS_DIR"
# Remove any leftover optional model directories so they are not accidentally bundled.
# Core model dirs (action_classifier, domain_classifier, kws) are preserved to avoid re-downloads.
for entry in "$BUNDLE_MODELS_DIR"/*; do
  [ -e "$entry" ] || continue
  basename=$(basename "$entry")
  if [ "$basename" != "action_classifier" ] && [ "$basename" != "domain_classifier" ] && [ "$basename" != "kws" ]; then
    rm -rf "$entry"
  fi
done

copy_classifier_runtime() {
  local name=$1
  local src="$PROJECT_ROOT/backend/models/$name"
  local dst="$BUNDLE_MODELS_DIR/$name"

  if [ ! -f "$src/classifier.onnx" ]; then
    echo "❌ Missing classifier model: $src/classifier.onnx" >&2
    exit 1
  fi

  mkdir -p "$dst"
  cp -f "$src/classifier.onnx" "$dst/"
  # Some ONNX exports keep weights in a separate .data file (optional)
  if [ -f "$src/classifier.onnx.data" ]; then
    cp -f "$src/classifier.onnx.data" "$dst/"
  fi
  cp -f "$src/tokenizer.json" "$src/labels.json" "$dst/"
  echo "✅ $name bundled (~$(du -sh "$dst" | cut -f1))"
}

# ---------------------------------------------------------------------------
# Classifiers (only the runtime files, not the full training checkpoints)
# ---------------------------------------------------------------------------
copy_classifier_runtime action_classifier
copy_classifier_runtime domain_classifier

# ---------------------------------------------------------------------------
# KWS (Keyword Spotting) model for wake word
# ---------------------------------------------------------------------------
KWS_DST="$BUNDLE_MODELS_DIR/kws"
if [ -f "$KWS_DST/tokens.txt" ]; then
  echo "✅ KWS model already bundled (~$(du -sh "$KWS_DST" | cut -f1))"
  exit 0
fi

LOCAL_KWS="$HOME/.evoloop/models/kws"
if [ -f "$LOCAL_KWS/tokens.txt" ]; then
  echo "📂 Using cached KWS model from $LOCAL_KWS"
  mkdir -p "$KWS_DST"
  cp -R "$LOCAL_KWS/." "$KWS_DST/"
  echo "✅ KWS model bundled (~$(du -sh "$KWS_DST" | cut -f1))"
  exit 0
fi

echo "⬇️ Downloading KWS model..."
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

if command -v curl >/dev/null 2>&1; then
  curl -L --fail --show-error -o "$TMP_DIR/kws.tar.bz2" "$KWS_URL"
elif command -v wget >/dev/null 2>&1; then
  wget -O "$TMP_DIR/kws.tar.bz2" "$KWS_URL"
else
  echo "❌ curl or wget is required to download the KWS model" >&2
  exit 1
fi

tar -xjf "$TMP_DIR/kws.tar.bz2" -C "$TMP_DIR"

if [ ! -d "$TMP_DIR/$KWS_DIR_NAME" ]; then
  echo "❌ KWS archive did not contain expected directory: $KWS_DIR_NAME" >&2
  exit 1
fi

mkdir -p "$KWS_DST"
# Move all model files into the flat kws/ directory expected by wake_word.rs
mv "$TMP_DIR/$KWS_DIR_NAME"/* "$KWS_DST/"

echo "✅ KWS model bundled (~$(du -sh "$KWS_DST" | cut -f1))"
