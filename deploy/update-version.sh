#!/bin/bash
# =============================================================================
# EvoLoop 版本号更新脚本
# =============================================================================
# 用法:
#   ./update-version.sh <version> [build_number]
# 示例:
#   ./update-version.sh 1.2.3          # 更新版本号为 1.2.3
#   ./update-version.sh 1.2.3 45       # 更新版本号为 1.2.3，构建号 45
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 参数检查
if [ $# -lt 1 ]; then
    echo "❌ 错误: 请提供版本号"
    echo "用法: $0 <version> [build_number]"
    echo "示例: $0 1.2.3"
    exit 1
fi

NEW_VERSION="$1"
BUILD_NUMBER="${2:-1}"
BUILD_TIME=$(date +%Y%m%d%H%M%S)
GIT_COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

# 验证版本号格式 (语义化版本: x.x.x)
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ 错误: 版本号格式不正确，应为 x.x.x (如: 1.2.3)"
    exit 1
fi

echo "🚀 更新 EvoLoop 版本号..."
echo "   版本: $NEW_VERSION"
echo "   构建号: $BUILD_NUMBER"
echo "   构建时间: $BUILD_TIME"
echo "   Git Commit: $GIT_COMMIT"

# =============================================================================
# 1. 更新 .env.prod.desktop (桌面端版本信息)
# =============================================================================
ENV_PROD_DESKTOP="$PROJECT_ROOT/.env.prod.desktop"

if [ -f "$ENV_PROD_DESKTOP" ]; then
    for key in APP_VERSION BUILD_NUMBER BUILD_TIME GIT_COMMIT; do
        val=""
        case "$key" in
            APP_VERSION) val="$NEW_VERSION" ;;
            BUILD_NUMBER) val="$BUILD_NUMBER" ;;
            BUILD_TIME) val="$BUILD_TIME" ;;
            GIT_COMMIT) val="$GIT_COMMIT" ;;
        esac
        if grep -q "^$key=" "$ENV_PROD_DESKTOP"; then
            sed -i.bak "s/^$key=.*/$key=$val/" "$ENV_PROD_DESKTOP"
        fi
    done
    rm -f "$ENV_PROD_DESKTOP.bak"
    echo "✅ 已更新: $ENV_PROD_DESKTOP"
else
    echo "⚠️  .env.prod.desktop 不存在，跳过版本更新"
fi

# =============================================================================
# 2. 更新 Cargo.toml (Rust 后端版本)
# =============================================================================
CARGO_FILE="$PROJECT_ROOT/frontend/src-tauri/Cargo.toml"
if [ -f "$CARGO_FILE" ]; then
    # 使用 sed 更新 version 字段
    sed -i.bak "s/^version = \"[^\"]*\"/version = \"$NEW_VERSION\"/" "$CARGO_FILE"
    rm -f "$CARGO_FILE.bak"
    echo "✅ 已更新: $CARGO_FILE"
fi

# =============================================================================
# 3. 更新 package.json (前端版本)
# =============================================================================
PACKAGE_FILE="$PROJECT_ROOT/frontend/package.json"
if [ -f "$PACKAGE_FILE" ]; then
    # 使用 Node.js 或 sed 更新版本
    if command -v node &> /dev/null; then
        node -e "
            const fs = require('fs');
            const pkg = JSON.parse(fs.readFileSync('$PACKAGE_FILE', 'utf8'));
            pkg.version = '$NEW_VERSION';
            fs.writeFileSync('$PACKAGE_FILE', JSON.stringify(pkg, null, 2) + '\n');
        "
    else
        sed -i.bak "s/\"version\": \"[^\"]*\"/\"version\": \"$NEW_VERSION\"/" "$PACKAGE_FILE"
        rm -f "$PACKAGE_FILE.bak"
    fi
    echo "✅ 已更新: $PACKAGE_FILE"
fi

# =============================================================================
# 4. 更新 tauri.conf.json
# =============================================================================
TAURI_CONF="$PROJECT_ROOT/frontend/src-tauri/tauri.conf.json"
if [ -f "$TAURI_CONF" ]; then
    if command -v node &> /dev/null; then
        node -e "
            const fs = require('fs');
            const conf = JSON.parse(fs.readFileSync('$TAURI_CONF', 'utf8'));
            conf.version = '$NEW_VERSION';
            fs.writeFileSync('$TAURI_CONF', JSON.stringify(conf, null, 2) + '\n');
        "
    fi
    echo "✅ 已更新: $TAURI_CONF"
fi

# =============================================================================
# 5. 生成版本信息文件 (供前端使用)
# =============================================================================
VERSION_INFO_FILE="$PROJECT_ROOT/frontend/src/version.json"
mkdir -p "$(dirname "$VERSION_INFO_FILE")"

cat > "$VERSION_INFO_FILE" << EOF
{
  "version": "$NEW_VERSION",
  "buildNumber": $BUILD_NUMBER,
  "buildTime": "$BUILD_TIME",
  "gitCommit": "$GIT_COMMIT",
  "stage": "${RELEASE_STAGE:-alpha}",
  "fullVersion": "$NEW_VERSION+$BUILD_NUMBER (${GIT_COMMIT:0:7})"
}
EOF

echo "✅ 已生成: $VERSION_INFO_FILE"

# =============================================================================
# 6. 生成 Rust 版本常量文件
# =============================================================================
RUST_VERSION_FILE="$PROJECT_ROOT/frontend/src-tauri/src/version.rs"
mkdir -p "$(dirname "$RUST_VERSION_FILE")"

cat > "$RUST_VERSION_FILE" << EOF
// 此文件由 deploy/update-version.sh 自动生成，请勿手动修改
// 生成时间: $(date)

pub const VERSION: &str = "$NEW_VERSION";
pub const BUILD_NUMBER: &str = "$BUILD_NUMBER";
pub const BUILD_TIME: &str = "$BUILD_TIME";
pub const GIT_COMMIT: &str = "$GIT_COMMIT";
pub const FULL_VERSION: &str = "$NEW_VERSION+$BUILD_NUMBER (${GIT_COMMIT:0:7})";

/// 获取完整的版本信息
pub fn get_version_info() -> VersionInfo {
    VersionInfo {
        version: VERSION.to_string(),
        build_number: BUILD_NUMBER.to_string(),
        build_time: BUILD_TIME.to_string(),
        git_commit: GIT_COMMIT.to_string(),
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct VersionInfo {
    pub version: String,
    pub build_number: String,
    pub build_time: String,
    pub git_commit: String,
}
EOF

echo "✅ 已生成: $RUST_VERSION_FILE"

echo ""
echo "🎉 版本号更新完成!"
echo "   当前版本: $NEW_VERSION (Build $BUILD_NUMBER)"
echo ""
echo "💡 提示:"
echo "   - 前端版本信息: frontend/src/version.json"
echo "   - Rust版本常量: frontend/src-tauri/src/version.rs"
echo "   - 环境变量配置: .env"
