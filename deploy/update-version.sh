#!/bin/bash
# =============================================================================
# EvoLoop 全局版本号管理脚本
# =============================================================================
# 单一来源: evoloop/VERSION
# 用法:
#   ./update-version.sh [build_number]
#
# 示例:
#   ./update-version.sh          # 读取 VERSION 文件，build_number 默认 1
#   ./update-version.sh 45       # 读取 VERSION 文件，build_number 45
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="$PROJECT_ROOT/VERSION"

# 参数检查
if [ $# -ge 1 ]; then
    BUILD_NUMBER="$1"
else
    BUILD_NUMBER="1"
fi

# 读取 VERSION
if [ ! -f "$VERSION_FILE" ]; then
    echo "❌ 错误: VERSION 文件不存在: $VERSION_FILE"
    echo "请创建 VERSION 文件，例如: echo '1.0.0' > VERSION"
    exit 1
fi

NEW_VERSION="$(cat "$VERSION_FILE" | tr -d '[:space:]')"

# 验证版本号格式 (语义化版本: x.x.x)
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ 错误: VERSION 文件内容格式不正确，应为 x.x.x (如: 1.0.0)"
    echo "当前内容: '$NEW_VERSION'"
    exit 1
fi

BUILD_TIME=$(date +%Y%m%d%H%M%S)
GIT_COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

# iOS 用版本号 (去掉 patch 后可用于 MARKETING_VERSION，但这里保持完整)
# pbxproj 里 MARKETING_VERSION 可以是 x.x 或 x.x.x，这里统一用完整版本
IOS_MARKETING_VERSION="$NEW_VERSION"

# Android versionCode: 把 1.2.3 转成 10203 (major*10000 + minor*100 + patch)
IFS='.' read -r major minor patch <<< "$NEW_VERSION"
ANDROID_VERSION_CODE=$((major * 10000 + minor * 100 + patch))

# HarmonyOS versionCode: 把 1.2.3 转成 1000000*major + 1000*minor + patch
# 例如 1.0.0 -> 1000000, 1.2.3 -> 1002003
HARMONY_VERSION_CODE=$((major * 1000000 + minor * 1000 + patch))

echo "🚀 更新 EvoLoop 全局版本号..."
echo "   版本: $NEW_VERSION"
echo "   构建号: $BUILD_NUMBER"
echo "   构建时间: $BUILD_TIME"
echo "   Git Commit: $GIT_COMMIT"
echo "   Android versionCode: $ANDROID_VERSION_CODE"
echo "   HarmonyOS versionCode: $HARMONY_VERSION_CODE"
echo ""

update_env_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo "⚠️  跳过: $file 不存在"
        return
    fi

    for key in APP_VERSION BUILD_NUMBER BUILD_TIME GIT_COMMIT; do
        val=""
        case "$key" in
            APP_VERSION) val="$NEW_VERSION" ;;
            BUILD_NUMBER) val="$BUILD_NUMBER" ;;
            BUILD_TIME) val="$BUILD_TIME" ;;
            GIT_COMMIT) val="$GIT_COMMIT" ;;
        esac
        if grep -q "^$key=" "$file"; then
            sed -i.bak "s/^$key=.*/$key=$val/" "$file"
        else
            echo "$key=$val" >> "$file"
        fi
    done
    rm -f "$file.bak"
    echo "✅ 已更新: $file"
}

# 1. 更新 .env 相关文件
for env_file in "$PROJECT_ROOT/.env.prod.desktop" "$PROJECT_ROOT/.env.example"; do
    update_env_file "$env_file"
done

# 2. 更新 frontend/package.json
FRONTEND_PKG="$PROJECT_ROOT/frontend/package.json"
if [ -f "$FRONTEND_PKG" ]; then
    node -e "
        const fs = require('fs');
        const pkg = JSON.parse(fs.readFileSync('$FRONTEND_PKG', 'utf8'));
        pkg.version = '$NEW_VERSION';
        fs.writeFileSync('$FRONTEND_PKG', JSON.stringify(pkg, null, 2) + '\n');
    "
    echo "✅ 已更新: $FRONTEND_PKG"
fi

# 3. 更新 mobile/package.json
MOBILE_PKG="$PROJECT_ROOT/mobile/package.json"
if [ -f "$MOBILE_PKG" ]; then
    node -e "
        const fs = require('fs');
        const pkg = JSON.parse(fs.readFileSync('$MOBILE_PKG', 'utf8'));
        pkg.version = '$NEW_VERSION';
        fs.writeFileSync('$MOBILE_PKG', JSON.stringify(pkg, null, 2) + '\n');
    "
    echo "✅ 已更新: $MOBILE_PKG"
fi

# 4. 更新 frontend/src-tauri/Cargo.toml
CARGO_FILE="$PROJECT_ROOT/frontend/src-tauri/Cargo.toml"
if [ -f "$CARGO_FILE" ]; then
    sed -i.bak "s/^version = \"[^\"]*\"/version = \"$NEW_VERSION\"/" "$CARGO_FILE"
    rm -f "$CARGO_FILE.bak"
    echo "✅ 已更新: $CARGO_FILE"
fi

# 5. 更新 frontend/src-tauri/tauri.conf.json
TAURI_CONF="$PROJECT_ROOT/frontend/src-tauri/tauri.conf.json"
if [ -f "$TAURI_CONF" ]; then
    node -e "
        const fs = require('fs');
        const conf = JSON.parse(fs.readFileSync('$TAURI_CONF', 'utf8'));
        conf.version = '$NEW_VERSION';
        fs.writeFileSync('$TAURI_CONF', JSON.stringify(conf, null, 2) + '\n');
    "
    echo "✅ 已更新: $TAURI_CONF"
fi

# 6. 更新 Android build.gradle
ANDROID_BUILD_GRADLE="$PROJECT_ROOT/mobile/android/app/build.gradle"
if [ -f "$ANDROID_BUILD_GRADLE" ]; then
    sed -i.bak "s/versionCode [0-9]*/versionCode $ANDROID_VERSION_CODE/" "$ANDROID_BUILD_GRADLE"
    sed -i.bak "s/versionName \"[^\"]*\"/versionName \"$NEW_VERSION\"/" "$ANDROID_BUILD_GRADLE"
    rm -f "$ANDROID_BUILD_GRADLE.bak"
    echo "✅ 已更新: $ANDROID_BUILD_GRADLE (versionCode=$ANDROID_VERSION_CODE, versionName=$NEW_VERSION)"
fi

# 7. 更新 iOS project.pbxproj
IOS_PBXPROJ="$PROJECT_ROOT/mobile/ios/EvoLoopMobile.xcodeproj/project.pbxproj"
if [ -f "$IOS_PBXPROJ" ]; then
    sed -i.bak "s/MARKETING_VERSION = [^;]*;/MARKETING_VERSION = $IOS_MARKETING_VERSION;/g" "$IOS_PBXPROJ"
    rm -f "$IOS_PBXPROJ.bak"
    echo "✅ 已更新: $IOS_PBXPROJ (MARKETING_VERSION=$IOS_MARKETING_VERSION)"
fi

# 8. 更新 HarmonyOS app.json5
HARMONY_APP_JSON="$PROJECT_ROOT/mobile/harmony/AppScope/app.json5"
if [ -f "$HARMONY_APP_JSON" ]; then
    node -e "
        const fs = require('fs');
        const content = fs.readFileSync('$HARMONY_APP_JSON', 'utf8');
        // 去掉 trailing comma 避免 JSON5 解析问题
        const cleaned = content.replace(/,([\s]*[}\]])/g, '\$1');
        const conf = JSON.parse(cleaned);
        conf.app.versionCode = $HARMONY_VERSION_CODE;
        conf.app.versionName = '$NEW_VERSION';
        fs.writeFileSync('$HARMONY_APP_JSON', JSON.stringify(conf, null, 2) + '\n');
    "
    echo "✅ 已更新: $HARMONY_APP_JSON (versionCode=$HARMONY_VERSION_CODE, versionName=$NEW_VERSION)"
fi

# 9. 生成版本信息文件 (供前端使用)
VERSION_INFO_FILE="$PROJECT_ROOT/frontend/src/version.json"
mkdir -p "$(dirname "$VERSION_INFO_FILE")"
cat > "$VERSION_INFO_FILE" << EOF
{
  "version": "$NEW_VERSION",
  "buildNumber": $BUILD_NUMBER,
  "buildTime": "$BUILD_TIME",
  "gitCommit": "$GIT_COMMIT",
  "stage": "${RELEASE_STAGE:-production}",
  "fullVersion": "$NEW_VERSION+$BUILD_NUMBER (${GIT_COMMIT:0:7})"
}
EOF
echo "✅ 已生成: $VERSION_INFO_FILE"

# 10. Rust 版本常量
# =============================================================================
# Rust 版本号现在从 Cargo.toml 读取（通过 env!("CARGO_PKG_VERSION")），
# 不需要再生成 version.rs。
# 构建时传入环境变量即可：
#   BUILD_NUMBER / BUILD_TIME / GIT_COMMIT / RELEASE_STAGE
echo "✅ Rust 版本从 Cargo.toml 读取: $NEW_VERSION"

echo ""
echo "🎉 版本号统一更新完成!"
echo "   当前版本: $NEW_VERSION (Build $BUILD_NUMBER)"
echo ""
echo "💡 提示:"
echo "   - 全局版本源: $VERSION_FILE"
echo "   - 前端版本信息: frontend/src/version.json"
echo "   - Rust 版本从 Cargo.toml 读取: frontend/src-tauri/Cargo.toml"
