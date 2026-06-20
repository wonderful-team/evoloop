#!/bin/bash

# EvoLoop 图标生成脚本 (兼容版)
# 使用 sips 自动生成多尺寸图标

MASTER_LOGO="${MASTER_LOGO:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../mobile"

if [ -z "$MASTER_LOGO" ] || [ ! -f "$MASTER_LOGO" ]; then
  echo "❌ 用法: MASTER_LOGO=/path/to/logo.png bash $0"
  echo "   需要提供 1024x1024 PNG 源图标文件"
  exit 1
fi

echo "🚀 开始为 EvoLoop 生成图标 (来源: $MASTER_LOGO) ..."

# 1. Android 适配
echo "🤖 处理 Android 图标..."

generate_android() {
    local res=$1
    local size=$2
    local target_dir="$PROJECT_ROOT/android/app/src/main/res/mipmap-$res"
    mkdir -p "$target_dir"
    sips -z "$size" "$size" "$MASTER_LOGO" --out "$target_dir/ic_launcher.png" > /dev/null 2>&1
    sips -z "$size" "$size" "$MASTER_LOGO" --out "$target_dir/ic_launcher_round.png" > /dev/null 2>&1
    echo "   → 适配 $res ($size x $size)"
}

generate_android "mdpi" 48
generate_android "hdpi" 72
generate_android "xhdpi" 96
generate_android "xxhdpi" 144
generate_android "xxxhdpi" 192

# 2. iOS 适配
echo "🍎 处理 iOS 图标..."
IOS_ICON_SET="$PROJECT_ROOT/ios/EvoLoopMobile/Images.xcassets/AppIcon.appiconset"
mkdir -p "$IOS_ICON_SET"

generate_ios() {
    local size=$1
    local filename=$2
    sips -z "$size" "$size" "$MASTER_LOGO" --out "$IOS_ICON_SET/$filename" > /dev/null 2>&1
    echo "   → 适配 iOS $filename ($size x $size)"
}

generate_ios 40 "icon-20@2x.png"
generate_ios 60 "icon-20@3x.png"
generate_ios 58 "icon-29@2x.png"
generate_ios 87 "icon-29@3x.png"
generate_ios 80 "icon-40@2x.png"
generate_ios 120 "icon-40@3x.png"
generate_ios 120 "icon-60@2x.png"
generate_ios 180 "icon-60@3x.png"
generate_ios 1024 "icon-1024.png"

echo "✅ 所有图标生成并适配完毕！"
