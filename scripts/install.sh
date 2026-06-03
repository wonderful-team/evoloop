#!/usr/bin/env bash
#
# EvoLoop 一键安装脚本
# =====================
# 支持：Linux / macOS
# 用法：
#   bash scripts/install.sh [options]
#   远程：curl -fsSL https://get.evoloop.ai | bash
#

set -e

DEPLOY_DIR=""

show_help() {
  echo "EvoLoop 一键安装脚本"
  echo ""
  echo "用法:"
  echo "  bash $0 [options]"
  echo ""
  echo "选项:"
  echo "  --help, -h            显示此帮助"
  echo "  --version VERSION     指定版本 (默认: latest)"
  echo "  --dir PATH            安装目录 (默认: \$HOME/evoloop)"
  echo "  --deploy-dir=PATH     部署目标目录 (默认: 当前目录)"
  echo "                        指定后仅复制服务器所需文件到目标目录，"
  echo "                        排除 mobile/、frontend/src-tauri/ 等"
  echo "  --compose-url URL     Docker Compose 文件地址"
  echo ""
  echo "环境变量:"
  echo "  EVOLOOP_VERSION      版本号"
  echo "  INSTALL_DIR          安装目录"
  echo ""
  echo "示例:"
  echo "  bash $0"
  echo "  bash $0 --version v0.2.0"
  echo "  bash $0 --dir /opt/evoloop"
  echo "  bash $0 --deploy-dir=/opt/evoloop"
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) show_help; exit 0 ;;
    --deploy-dir=*) DEPLOY_DIR="${arg#*=}" ;;
  esac
done

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 版本信息
EVOLOOP_VERSION="${EVOLOOP_VERSION:-latest}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/evoloop}"
COMPOSE_URL="https://raw.githubusercontent.com/evoloop-ai/evoloop/${EVOLOOP_VERSION}/docker-compose.yml"
ENV_URL="https://raw.githubusercontent.com/evoloop-ai/evoloop/${EVOLOOP_VERSION}/.env.example"

# 打印函数
info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

# 检测操作系统
detect_os() {
    local OS=$(uname -s)
    case "$OS" in
        Linux*)
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                echo "linux:$ID"
            else
                echo "linux:unknown"
            fi
            ;;
        Darwin*)
            echo "macos:$(sw_vers -productVersion)"
            ;;
        *)
            echo "unsupported"
            ;;
    esac
}

# 检测依赖
 detect_dependencies() {
    info "检测系统依赖..."

    local MISSING_DEPS=()

    # 检测 Docker
    if ! command -v docker &> /dev/null; then
        MISSING_DEPS+=("docker")
    else
        local DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
        success "Docker 已安装: $DOCKER_VERSION"
    fi

    # 检测 Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        MISSING_DEPS+=("docker-compose")
    else
        if docker compose version &> /dev/null; then
            success "Docker Compose (插件) 已安装"
        else
            local COMPOSE_VERSION=$(docker-compose --version | awk '{print $3}' | tr -d ',')
            success "Docker Compose 已安装: $COMPOSE_VERSION"
        fi
    fi

    # 检测 Git
    if ! command -v git &> /dev/null; then
        MISSING_DEPS+=("git")
    else
        success "Git 已安装"
    fi

    # 检测内存（推荐至少 4GB）
    local TOTAL_MEM=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo "0")
    if [ "$TOTAL_MEM" -gt 0 ] && [ "$TOTAL_MEM" -lt 4096 ]; then
        warning "内存不足 4GB (当前: ${TOTAL_MEM}MB)，可能影响性能"
    fi

    # 检测磁盘空间（推荐至少 10GB）
    local FREE_SPACE=$(df -BG "$HOME" 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G' || echo "0")
    if [ "$FREE_SPACE" -lt 10 ]; then
        warning "磁盘空间不足 10GB (剩余: ${FREE_SPACE}GB)"
    fi

    if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
        error "缺少以下依赖: ${MISSING_DEPS[*]}"
        echo ""
        echo "请安装缺失的依赖后重试："
        echo "  - Docker: https://docs.docker.com/get-docker/"
        echo "  - Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi

    success "所有依赖检测通过"
}

# 安装缺失依赖（仅支持部分系统）
install_dependencies() {
    local OS=$(detect_os)

    info "尝试自动安装依赖..."

    case "$OS" in
        linux:ubuntu|linux:debian)
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y docker.io docker-compose-plugin git
                sudo systemctl enable docker
                sudo systemctl start docker
                sudo usermod -aG docker "$USER"
                warning "已将当前用户加入 docker 组，请重新登录后重试"
                exit 0
            fi
            ;;
        linux:centos|linux:rhel|linux:fedora)
            if command -v yum &> /dev/null; then
                sudo yum install -y docker docker-compose git
                sudo systemctl enable docker
                sudo systemctl start docker
                sudo usermod -aG docker "$USER"
                warning "已将当前用户加入 docker 组，请重新登录后重试"
                exit 0
            fi
            ;;
        macos:*)
            if command -v brew &> /dev/null; then
                brew install --cask docker
                brew install git
                warning "请启动 Docker Desktop 后重试"
                exit 0
            fi
            ;;
    esac

    error "无法自动安装依赖，请手动安装"
    exit 1
}

# 设置环境
setup_environment() {
    info "设置 EvoLoop 环境..."

    # 创建安装目录
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"

    # 如果指定了 --deploy-dir，从本地仓库 rsync 仅服务器所需文件
    if [ -n "$DEPLOY_DIR" ]; then
        info "从 $PROJECT_ROOT 同步服务器所需文件到 $DEPLOY_DIR..."
        EXCLUDE_RSYNC=(
            --exclude='mobile'
            --exclude='frontend/src-tauri'
            --exclude='node_modules'
            --exclude='.venv'
            --exclude='backend/.venv'
            --exclude='backend/dist'
            --exclude='backend/build'
            --exclude='backend/evoloop-backend.spec'
            --exclude='backend/entry_point.py'
            --exclude='dist'
            --exclude='Makefile'
            --exclude='.git'
            --exclude='.pre-commit-config.yaml'
            --exclude='scripts/build'
            --exclude='scripts/dev.sh'
            --exclude='scripts/check_arch.sh'
            --exclude='scripts/update-version.sh'
            --exclude='scripts/generate-client.sh'
            --exclude='scripts/install_funasr.sh'
            --exclude='config/desktop'
            --exclude='config/mobile'
            --exclude='frontend/playwright.config.ts'
            --exclude='frontend/vitest.config.ts'
        )
        PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/..")
        mkdir -p "$DEPLOY_DIR"
        rsync -av --delete "${EXCLUDE_RSYNC[@]}" "$PROJECT_ROOT/" "$DEPLOY_DIR/"
        cd "$DEPLOY_DIR"
        INSTALL_DIR="$DEPLOY_DIR"
        success "已复制服务器所需文件到 $DEPLOY_DIR"
    fi

    # 下载 docker-compose.yml
    if [ -f "docker-compose.yml" ]; then
        warning "docker-compose.yml 已存在，跳过下载"
    else
        info "下载 docker-compose.yml..."
        if command -v curl &> /dev/null; then
            curl -fsSL "$COMPOSE_URL" -o docker-compose.yml
        else
            wget -q "$COMPOSE_URL" -O docker-compose.yml
        fi
        success "docker-compose.yml 下载完成"
    fi

    # 下载 .env 模板
    if [ -f ".env" ]; then
        warning ".env 已存在，跳过创建"
    else
        info "创建 .env 配置文件..."
        if command -v curl &> /dev/null; then
            curl -fsSL "$ENV_URL" -o .env
        else
            wget -q "$ENV_URL" -O .env
        fi

        # 生成随机密钥
        local SECRET_KEY=$(openssl rand -base64 32 2>/dev/null || head -c 32 /dev/urandom | base64)
        sed -i.bak "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env 2>/dev/null || true
        rm -f .env.bak

        success ".env 配置文件创建完成"
        warning "请编辑 .env 文件配置必要的环境变量"
    fi

    # 创建数据目录
    mkdir -p data/postgres data/redis data/neo4j
    mkdir -p ~/.evoloop/database ~/.evoloop/skills ~/.evoloop/screenshots

    success "环境设置完成"
}

# 启动服务
start_services() {
    info "启动 EvoLoop 服务..."

    cd "$INSTALL_DIR"

    # 拉取最新镜像
    info "拉取 Docker 镜像..."
    docker-compose pull 2>/dev/null || docker compose pull

    # 启动服务
    info "启动服务..."
    docker-compose up -d 2>/dev/null || docker compose up -d

    success "服务启动命令已执行"
}

# 健康检查
health_check() {
    info "等待服务启动..."

    local MAX_RETRIES=30
    local RETRY=0

    echo -n "检查服务健康状态"
    while [ $RETRY -lt $MAX_RETRIES ]; do
        if curl -fs http://localhost:20160/api/v1/health &> /dev/null; then
            echo ""
            success "后端服务运行正常"
            return 0
        fi
        echo -n "."
        sleep 2
        RETRY=$((RETRY + 1))
    done

    echo ""
    warning "服务启动超时，请检查日志：docker-compose logs"
    return 1
}

# 打印成功信息
print_success() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           EvoLoop 安装完成！                             ║"
    echo "╠══════════════════════════════════════════════════════════╣"
    echo "║                                                          ║"
    echo "║  访问地址：                                              ║"
    echo "║    - 前端：http://localhost:20160                         ║"
    echo "║    - 后端 API：http://localhost:20160                     ║"
    echo "║    - API 文档：http://localhost:20160/docs                ║"
    echo "║                                                          ║"
    echo "║  常用命令：                                              ║"
    echo "║    cd $INSTALL_DIR                                       ║"
    echo "║    docker-compose up -d      # 启动服务                  ║"
    echo "║    docker-compose down       # 停止服务                  ║"
    echo "║    docker-compose logs -f    # 查看日志                  ║"
    echo "║                                                          ║"
    echo "║  配置文件：                                              ║"
    echo "║    $INSTALL_DIR/.env                                    ║"
    echo "║                                                          ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
}

# 主函数
main() {
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           EvoLoop 一键安装脚本                           ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    # 检测操作系统
    local OS=$(detect_os)
    if [ "$OS" = "unsupported" ]; then
        error "不支持的操作系统"
        exit 1
    fi
    info "检测到操作系统: $OS"

    # 检测依赖
    if ! detect_dependencies; then
        read -p "是否尝试自动安装依赖? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install_dependencies
        else
            exit 1
        fi
    fi

    # 设置环境
    setup_environment

    # 启动服务
    start_services

    # 健康检查
    health_check

    # 打印成功信息
    print_success
}

# 处理命令行参数
case "${1:-}" in
    --help|-h)
        echo "EvoLoop 一键安装脚本"
        echo ""
        echo "用法:"
        echo "  curl -fsSL https://get.evoloop.ai | bash"
        echo "  wget -qO- https://get.evoloop.ai | bash"
        echo ""
        echo "环境变量:"
        echo "  EVOLOOP_VERSION    指定版本 (默认: latest)"
        echo "  INSTALL_DIR        安装目录 (默认: $HOME/evoloop)"
        echo ""
        exit 0
        ;;
    *)
        main
        ;;
esac
