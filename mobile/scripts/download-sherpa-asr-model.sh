#!/bin/bash
# 下载 Sherpa-ONNX 中文流式 ASR 模型并放入项目资源目录
# 使用方法: bash scripts/download-sherpa-asr-model.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
MODEL_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2"
MODEL_NAME="sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23"
TEMP_DIR=$(mktemp -d)

echo "🚀 下载 Sherpa-ONNX 中文流式 ASR 模型..."
echo "   URL: $MODEL_URL"

curl -L --progress-bar -o "$TEMP_DIR/model.tar.bz2" "$MODEL_URL"

echo "📦 解压模型..."
tar -xjf "$TEMP_DIR/model.tar.bz2" -C "$TEMP_DIR"

echo "📂 模型内容:"
ls -lh "$TEMP_DIR/$MODEL_NAME"

echo ""
echo "📲 复制到 Android assets..."
mkdir -p "$PROJECT_ROOT/android/app/src/main/assets/sherpa-asr"
cp -R "$TEMP_DIR/$MODEL_NAME" "$PROJECT_ROOT/android/app/src/main/assets/sherpa-asr/"
echo "   → android/app/src/main/assets/sherpa-asr/$MODEL_NAME"

echo ""
echo "🍎 复制到 iOS resources..."
mkdir -p "$PROJECT_ROOT/ios/EvoLoopMobile/Resources/sherpa-asr"
cp -R "$TEMP_DIR/$MODEL_NAME" "$PROJECT_ROOT/ios/EvoLoopMobile/Resources/sherpa-asr/"
echo "   → ios/EvoLoopMobile/Resources/sherpa-asr/$MODEL_NAME"

echo ""
echo "🧹 清理临时文件..."
rm -rf "$TEMP_DIR"

echo ""
echo "✅ 完成！模型已放入项目。"
echo "   总大小约 25MB (int8 量化)"
