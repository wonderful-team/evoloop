#!/bin/bash
# =============================================================================
# EvoLoop 产物上传到服务器脚本
# =============================================================================
# 用法:
#   ./deploy/upload.sh [options]
#
# 示例:
#   ./deploy/upload.sh --all
#   ./deploy/upload.sh --desktop --android --hap
#   ./deploy/upload.sh --all --server root@149.88.92.19:40890 --path /www/wwwroot/member-center/website/bundle/
# =============================================================================

set -e

# 让未匹配到的 glob 直接消失，而不是保留字面量
OLD_NULLGLOB=$(shopt -p nullglob || true)
shopt -s nullglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# member-center 仓库和 evoloop 是平级目录
MEMBER_CENTER_ROOT="$(cd "$PROJECT_ROOT/../member-center" && pwd)"

# 默认服务器配置
DEFAULT_SERVER="root@149.88.92.19"
DEFAULT_PORT="40890"
DEFAULT_REMOTE_PATH="/www/wwwroot/member-center/website/bundle/"
DEFAULT_BACKEND_PATH="/www/wwwroot/evoloop/"
DEFAULT_SSH_KEY="$HOME/.ssh/evoloop_deploy"

SERVER="$DEFAULT_SERVER"
PORT="$DEFAULT_PORT"
REMOTE_PATH="$DEFAULT_REMOTE_PATH"
BACKEND_REMOTE_PATH="$DEFAULT_BACKEND_PATH"
SSH_KEY="$DEFAULT_SSH_KEY"

# 上传开关
UPLOAD_DESKTOP=false
UPLOAD_ANDROID=false
UPLOAD_HAP=false
UPLOAD_IOS=false
UPLOAD_WEB=false
UPLOAD_BACKEND=false

show_usage() {
    cat << EOF
EvoLoop Upload Script

用法: $0 [options]

选项:
  --all                      上传所有产物
  --desktop                  上传 macOS DMG (arm64 + x86_64)
  --android                  上传 Android APK/AAB
  --hap                      上传 HarmonyOS HAP
  --ios                      上传 iOS IPA
  --web                      上传 Web 前端
  --backend                  上传 backend/app/ 到后端服务器 (覆盖 /www/wwwroot/evoloop/app/)
  --server HOST              SSH 服务器 (默认: $DEFAULT_SERVER)
  --port PORT                SSH 端口 (默认: $DEFAULT_PORT)
  --path REMOTE_PATH         远程目录 (默认: $DEFAULT_REMOTE_PATH)
  --backend-path BACKEND_PATH 后端远程目录 (默认: $DEFAULT_BACKEND_PATH)
  --key SSH_KEY              SSH 私钥路径 (默认: $DEFAULT_SSH_KEY)
  --dry-run                  只显示要上传什么，不执行
  --help, -h                 显示帮助
EOF
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --all) UPLOAD_DESKTOP=true; UPLOAD_ANDROID=true; UPLOAD_HAP=true; UPLOAD_IOS=true; UPLOAD_WEB=true; UPLOAD_BACKEND=true; shift ;;
        --desktop) UPLOAD_DESKTOP=true; shift ;;
        --android) UPLOAD_ANDROID=true; shift ;;
        --hap) UPLOAD_HAP=true; shift ;;
        --ios) UPLOAD_IOS=true; shift ;;
        --web) UPLOAD_WEB=true; shift ;;
        --backend) UPLOAD_BACKEND=true; shift ;;
        --server) SERVER="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --path) REMOTE_PATH="$2"; shift 2 ;;
        --backend-path) BACKEND_REMOTE_PATH="$2"; shift 2 ;;
        --key) SSH_KEY="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h) show_usage; exit 0 ;;
        *) echo "❌ 未知参数: $1"; show_usage; exit 1 ;;
    esac
done

if [ "$UPLOAD_DESKTOP" = false ] && [ "$UPLOAD_ANDROID" = false ] && [ "$UPLOAD_HAP" = false ] && [ "$UPLOAD_IOS" = false ] && [ "$UPLOAD_WEB" = false ] && [ "$UPLOAD_BACKEND" = false ]; then
    echo "❌ 请至少选择一个上传目标"
    show_usage
    exit 1
fi

SSH_OPTS="-i $SSH_KEY -p $PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PasswordAuthentication=no"

info()  { echo -e "\033[0;34mℹ\033[0m $1"; }
ok()    { echo -e "\033[0;32m✅\033[0m $1"; }
warn()  { echo -e "\033[1;33m⚠️\033[0m $1"; }
err()   { echo -e "\033[0;31m❌\033[0m $1"; }
step()  { echo -e "\033[1;33m┌─────────────────────────────────────────────────────────────┐\033[0m"
          echo -e "\033[1;33m│ $1\033[0m"
          echo -e "\033[1;33m└─────────────────────────────────────────────────────────────┐\033[0m"; }

# 测试 SSH 连接
test_ssh() {
    if ! ssh $SSH_OPTS "$SERVER" "echo 'SSH OK'" >/dev/null 2>&1; then
        err "无法通过 SSH key 登录 $SERVER:$PORT"
        echo ""
        echo "请检查:"
        echo "  1. 私钥文件是否存在: $SSH_KEY"
        echo "  2. 公钥是否已添加到服务器: ssh-copy-id -i ${SSH_KEY}.pub -p $PORT $SERVER"
        exit 1
    fi
    ok "SSH 连接正常"
}

# 确保远程目录存在
ensure_remote_dir() {
    if [ "$DRY_RUN" = true ]; then
        info "[dry-run] 会创建远程目录: $REMOTE_PATH"
        return
    fi
    ssh $SSH_OPTS "$SERVER" "mkdir -p '$REMOTE_PATH'"
}

# 从 VERSION 或 .env 获取版本
APP_VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || grep ^APP_VERSION= "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 || echo "")

# 上传文件
upload_file() {
    local src="$1"
    local dest_name="$2"

    if [ ! -f "$src" ]; then
        warn "文件不存在，跳过: $src"
        return 1
    fi

    local size
    size=$(du -h "$src" | cut -f1)

    if [ "$DRY_RUN" = true ]; then
        info "[dry-run] 准备上传: $src ($size) -> ${REMOTE_PATH}${dest_name}"
        return 0
    fi

    info "上传: $src ($size) -> ${REMOTE_PATH}${dest_name}"
    rsync -avz --progress -e "ssh $SSH_OPTS" "$src" "${SERVER}:${REMOTE_PATH}${dest_name}"
    ok "上传完成: $dest_name"
}

# 上传桌面端 DMG
upload_desktop() {
    step "上传桌面端 macOS DMG"
    local files=(
        "$PROJECT_ROOT/deploy/dist/EvoLoop_"*"_aarch64.dmg"
        "$PROJECT_ROOT/deploy/dist/EvoLoop_"*"_x86_64.dmg"
        "$MEMBER_CENTER_ROOT/website/bundle/EvoLoop_"*"_aarch64.dmg"
        "$MEMBER_CENTER_ROOT/website/bundle/EvoLoop_"*"_x86_64.dmg"
    )
    if [ ${#files[@]} -eq 0 ]; then
        warn "未找到 DMG 产物，请先运行 ./deploy/build.sh macos-arm64 / macos-x86_64"
        return
    fi
    local found=false
    for f in "${files[@]}"; do
        found=true
        upload_file "$f" "$(basename "$f")"
    done
}

# 上传 Android
upload_android() {
    step "上传 Android APK/AAB"

    APP_VERSION=$(grep ^APP_VERSION= "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 || echo "")
    if [ -z "$APP_VERSION" ] && command -v node >/dev/null 2>&1; then
        APP_VERSION=$(node -e "console.log(require('$PROJECT_ROOT/mobile/package.json').version || '')" 2>/dev/null || echo "")
    fi

    local files=(
        "$PROJECT_ROOT/deploy/dist/"*.apk
        "$PROJECT_ROOT/deploy/dist/"*.aab
        "$PROJECT_ROOT/mobile/android/app/build/outputs/apk/release/"*.apk
        "$PROJECT_ROOT/mobile/android/app/build/outputs/bundle/release/"*.aab
    )
    if [ ${#files[@]} -eq 0 ]; then
        warn "未找到 APK/AAB 产物，请先运行 ./deploy/build.sh android"
        return
    fi
    for f in "${files[@]}"; do
        local dest_name
        dest_name=$(basename "$f")
        # 如果是 app-release.apk / app-release.aab，按版本重命名
        if [[ "$dest_name" == "app-release.apk" ]] && [ -n "$APP_VERSION" ]; then
            dest_name="Evoloop_mobile_${APP_VERSION}.apk"
        elif [[ "$dest_name" == "app-release.aab" ]] && [ -n "$APP_VERSION" ]; then
            dest_name="Evoloop_mobile_${APP_VERSION}.aab"
        fi
        upload_file "$f" "$dest_name"
    done
}

# 上传 HAP
upload_hap() {
    step "上传 HarmonyOS HAP"
    local files=(
        "$PROJECT_ROOT/mobile/ios/build/outputs/default/"*"-signed.hap"
        "$PROJECT_ROOT/deploy/dist/EvoLoop_"*".hap"
        "$MEMBER_CENTER_ROOT/website/bundle/EvoLoop_"*".hap"
    )
    if [ ${#files[@]} -eq 0 ]; then
        warn "未找到 HAP 产物，请先运行 run-harmony --build-mode Release"
        return
    fi
    for f in "${files[@]}"; do
        upload_file "$f" "$(basename "$f")"
    done
}

# 上传 iOS
upload_ios() {
    step "上传 iOS IPA"
    local files=(
        "$PROJECT_ROOT/deploy/dist/"*.ipa
        "$PROJECT_ROOT/mobile/ios/build/"*.ipa
    )
    if [ ${#files[@]} -eq 0 ]; then
        warn "未找到 IPA 产物，请先运行 ./deploy/build.sh ios"
        return
    fi
    for f in "${files[@]}"; do
        upload_file "$f" "$(basename "$f")"
    done
}

# 上传 Web
upload_web() {
    step "上传 Web 前端"
    local src="$PROJECT_ROOT/frontend/dist"
    if [ ! -d "$src" ]; then
        warn "未找到前端构建产物，请先运行 ./deploy/build.sh web"
        return
    fi
    local size
    size=$(du -sh "$src" | cut -f1)
    if [ "$DRY_RUN" = true ]; then
        info "[dry-run] 准备上传: $src ($size) -> ${REMOTE_PATH}dist/"
        return
    fi
    info "上传 Web 前端: $src ($size) -> ${REMOTE_PATH}dist/"
    rsync -avz --delete --progress -e "ssh $SSH_OPTS" "$src/" "${SERVER}:${REMOTE_PATH}dist/"
    ok "Web 前端上传完成"
}

# 上传后端代码
upload_backend() {
    step "上传后端代码 backend/app/"
    local src="$PROJECT_ROOT/backend/app"
    if [ ! -d "$src" ]; then
        warn "未找到 backend/app 目录"
        return
    fi
    local size
    size=$(du -sh "$src" | cut -f1)
    if [ "$DRY_RUN" = true ]; then
        info "[dry-run] 准备上传: $src ($size) -> ${BACKEND_REMOTE_PATH}app/"
        return
    fi
    info "上传后端代码: $src ($size) -> ${BACKEND_REMOTE_PATH}app/"
    ssh $SSH_OPTS "$SERVER" "mkdir -p '$BACKEND_REMOTE_PATH'"
    rsync -avz --delete --progress \
        -e "ssh $SSH_OPTS" \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.DS_Store' \
        "$src/" "${SERVER}:${BACKEND_REMOTE_PATH}app/"
    ok "后端代码上传完成"
}

# 主流程
step "EvoLoop 产物上传"
echo "  服务器: $SERVER:$PORT"
echo "  产物目录: $REMOTE_PATH"
echo "  后端目录: $BACKEND_REMOTE_PATH"
echo "  SSH Key: $SSH_KEY"
echo ""

test_ssh
ensure_remote_dir

if [ "$UPLOAD_DESKTOP" = true ]; then upload_desktop; fi
if [ "$UPLOAD_ANDROID" = true ]; then upload_android; fi
if [ "$UPLOAD_HAP" = true ]; then upload_hap; fi
if [ "$UPLOAD_IOS" = true ]; then upload_ios; fi
if [ "$UPLOAD_WEB" = true ]; then upload_web; fi
if [ "$UPLOAD_BACKEND" = true ]; then upload_backend; fi

echo ""
ok "上传流程结束"

# 恢复 nullglob 设置
$OLD_NULLGLOB || true
