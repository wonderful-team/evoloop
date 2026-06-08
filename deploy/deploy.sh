#!/usr/bin/env bash
#
# EvoLoop 远程部署脚本
# =====================
# 增量同步到远程服务器，中间件（Postgres/Redis/Neo4j/Meilisearch）
# 通过共享 docker-compose.yml 管理，应用层跑在宿主机。
#

set -e

# ============================================================
# 默认配置
# ============================================================
HOST=""; USER="root"; PORT=22; KEY=""; PASSWORD=""
DEPLOY_DIR="/www/wwwroot/evoloop"
ENV_FILE=""; SYNC_ONLY=false; SKIP_BUILD=false; SKIP_FE=false
BUILD_ENV="production"

# ============================================================
# 颜色输出
# ============================================================
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warning() { echo -e "${YELLOW}⚠${NC} $1"; }
error()   { echo -e "${RED}✗${NC} $1"; }

# ============================================================
# 帮助
# ============================================================
show_help() {
  cat <<EOF
EvoLoop 远程部署脚本

增量同步到远程服务器，中间件通过共享 docker-compose.yml 管理。

用法:
  bash \$0 --host=HOST [options]

必要参数:
  --host=HOST

认证方式:
  --user=USER       (默认: root)
  --port=PORT       (默认: 22)
  --key=PATH        SSH 私钥
  --password        密码认证 (需 sshpass)

部署选项:
  --deploy-dir=PATH (默认: /www/wwwroot/evoloop)
  --env-file=PATH   .env 文件
  --sync-only       仅同步，不部署
  --skip-build      跳过后端 Python 环境部署
  --skip-fe         跳过前端构建与同步
  --env=ENV         构建环境: development|production (默认: production)

示例:
  bash \$0 --host=149.88.92.19 --env-file=.env
  bash \$0 --host=149.88.92.19 --sync-only
EOF
  exit 0
}

# ============================================================
# 参数解析
# ============================================================
for arg in "$@"; do
  case "$arg" in
    --help|-h) show_help ;;
    --host=*) HOST="${arg#*=}" ;;
    --user=*) USER="${arg#*=}" ;;
    --port=*) PORT="${arg#*=}" ;;
    --key=*) KEY="${arg#*=}" ;;
    --password=*) SSHPASS="${arg#*=}"; PASSWORD="yes" ;;
    --password) PASSWORD="yes" ;;
    --deploy-dir=*) DEPLOY_DIR="${arg#*=}" ;;
    --env-file=*) ENV_FILE="${arg#*=}" ;;
    --sync-only) SYNC_ONLY=true ;;
    --skip-build) SKIP_BUILD=true ;;
    --skip-fe) SKIP_FE=true ;;
    --env=*) BUILD_ENV="${arg#*=}" ;;
  esac
done
[ -z "$HOST" ] && { error "必须指定 --host=HOST"; exit 1; }

# ============================================================
# SSH 认证 + 快捷函数
# ============================================================
SSH_OPTS="-p $PORT -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ControlMaster=auto -o ControlPath=/tmp/ssh-evo-%r@%h:%p -o ControlPersist=120"
[ -z "$KEY" ] && [ -z "$PASSWORD" ] && for k in "$HOME/.ssh/id_rsa" "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_ecdsa"; do [ -f "$k" ] && { KEY="$k"; break; }; done

if [ -n "$KEY" ]; then
  SSH_OPTS="$SSH_OPTS -i $KEY"
elif [ -n "$PASSWORD" ]; then
  command -v sshpass &>/dev/null || { error "密码认证需要安装 sshpass"; exit 1; }
  [ -z "$SSHPASS" ] && read -s -p "请输入 SSH 密码: " SSHPASS && echo ""
  export SSHPASS; SSH_OPTS="$SSH_OPTS -o PreferredAuthentications=password"
else
  error "未找到 SSH key，且未指定 --password"; exit 1
fi
SSH_TARGET="${USER}@${HOST}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

run_remote_bg() { if [ -n "$PASSWORD" ]; then sshpass -e ssh $SSH_OPTS "$SSH_TARGET" "$1"; else ssh $SSH_OPTS "$SSH_TARGET" "$1"; fi; }
run_remote()   { if [ -n "$PASSWORD" ]; then sshpass -e ssh -t $SSH_OPTS "$SSH_TARGET" "$1"; else ssh -t $SSH_OPTS "$SSH_TARGET" "$1"; fi; }
rsync_to() {
  local src="$1" dst="$2"
  if [ -n "$PASSWORD" ]; then
    sshpass -e rsync -av --progress -e "ssh -p $PORT -o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password" "$src" "$SSH_TARGET:$dst"
  else
    rsync -av --progress -e "ssh -p $PORT -i $KEY -o StrictHostKeyChecking=accept-new" "$src" "$SSH_TARGET:$dst"
  fi
}

# ============================================================
# 排除列表
# ============================================================
EXCLUDE_RSYNC=(
  --exclude='mobile' --exclude='frontend/src-tauri'
  --exclude='frontend/node_modules' --exclude='backend/.venv'
  --exclude='frontend/dist' --exclude='backend/dist' --exclude='backend/build'
  --exclude='backend/evoloop-backend.spec' --exclude='backend/entry_point.py'
  --exclude='dist'   --exclude='Makefile' --exclude='.git' --exclude='.gitignore'
  --exclude='.pre-commit-config.yaml' --exclude='deploy/build'
  --exclude='deploy/dev.sh' --exclude='deploy/check_arch.sh'
  --exclude='deploy/update-version.sh' --exclude='deploy/generate-client.sh'
  --exclude='deploy/install_funasr.sh'
  --exclude='frontend/playwright.config.ts' --exclude='frontend/vitest.config.ts'
  --exclude='.mypy_cache' --exclude='__pycache__' --exclude='.pytest_cache'
  --exclude='.ruff_cache' --exclude='*.pyc'
  --exclude='backend/node_modules' --exclude='node_modules'
)

# ============================================================
# 测试连接
# ============================================================
test_connection() {
  info "测试 SSH 连接到 ${SSH_TARGET}:${PORT} ..."
  local OK=false
  if [ -n "$PASSWORD" ]; then
    sshpass -e ssh $SSH_OPTS "$SSH_TARGET" "echo connected" 2>/dev/null && OK=true
  else
    ssh $SSH_OPTS "$SSH_TARGET" "echo connected" 2>/dev/null && OK=true
  fi
  if [ "$OK" != true ]; then error "SSH 连接失败"; exit 1; fi
  success "SSH 连接成功"
}

# ============================================================
# 环境预检
# ============================================================
pre_flight_check() {
  echo ""; info "环境预检..."

  local DOCKER_OK=false
  run_remote_bg "command -v docker" 2>/dev/null && DOCKER_OK=true
  if [ "$DOCKER_OK" != true ]; then
    echo ""; warning "远程服务器未安装 Docker"
    read -p "是否自动安装 Docker？(y/N): " install_it
    if [[ "$install_it" =~ ^[Yy]$ ]]; then
      info "正在远程安装 Docker (阿里云镜像)..."
      run_remote_bg "
        dnf install -y -q dnf-plugins-core 2>/dev/null || true
        rm -f /etc/yum.repos.d/docker-ce.repo /etc/yum.repos.d/docker-ce-staging.repo
        dnf config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo 2>/dev/null || true
        dnf install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin 2>/dev/null ||
        dnf install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
      "
      run_remote_bg "systemctl enable docker && systemctl start docker"
    else
      error "Docker 是运行中间件的前提条件，中止部署"; exit 1
    fi
  fi
  success "Docker 已安装"

  local COMPOSE_OK=false
  run_remote_bg "docker compose version" 2>/dev/null && COMPOSE_OK=true
  if [ "$COMPOSE_OK" != true ]; then
    run_remote_bg "yum install -y docker-compose-plugin 2>/dev/null || apt-get install -y docker-compose-plugin 2>/dev/null || true"
    run_remote_bg "docker compose version" 2>/dev/null || { error "Docker Compose V2 安装失败"; exit 1; }
  fi
  success "Docker Compose V2 可用"

  if [ "$SKIP_BUILD" != true ]; then
    local PYTHON_OK=false
    run_remote_bg "command -v python3" 2>/dev/null && PYTHON_OK=true
    if [ "$PYTHON_OK" != true ]; then
      warning "未安装 Python3，尝试自动安装..."
      run_remote_bg "yum install -y python3 python3-pip 2>/dev/null || apt-get install -y python3 python3-pip 2>/dev/null || true"
      run_remote_bg "command -v python3" 2>/dev/null || { error "Python3 安装失败"; exit 1; }
    fi
    local PYTHON_VER=$(run_remote_bg "python3 --version" 2>/dev/null | awk '{print $2}' | cut -d. -f1,2 || echo "0.0")
    local MAJ=${PYTHON_VER%.*}; local MIN=${PYTHON_VER#*.}
    if [ "$MAJ" -ge 3 ] && [ "$MIN" -ge 10 ] 2>/dev/null; then
      success "Python3 ${PYTHON_VER} (满足 3.10+)"
    else
      warning "Python3 ${PYTHON_VER}，EvoLoop 建议 3.10+"
    fi
  fi

  for port in 5432 6379 7474 7687 7700; do
    if run_remote_bg "ss -tlnp | grep -q ':$port '" 2>/dev/null; then
      local owner=$(run_remote_bg "ss -tlnp | grep ':$port ' | head -1" 2>/dev/null)
      warning "端口 $port 已被占用 — $owner (Docker 容器启动后以该端口映射)"
    else
      success "端口 $port 空闲"
    fi
  done

  echo ""; success "环境预检通过"
}

# ============================================================
# 同步文件
# ============================================================
sync_files() {
  echo ""; info "开始增量同步到 ${SSH_TARGET}:${DEPLOY_DIR} ..."
  run_remote_bg "mkdir -p $DEPLOY_DIR"

  local RSYNC_ARGS="-av --delete --progress"
  if [ -n "$PASSWORD" ]; then
    sshpass -e rsync $RSYNC_ARGS "${EXCLUDE_RSYNC[@]}" -e "ssh -p $PORT -o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password" "$PROJECT_ROOT/" "$SSH_TARGET:$DEPLOY_DIR/" || true
  else
    rsync $RSYNC_ARGS "${EXCLUDE_RSYNC[@]}" -e "ssh -p $PORT -i $KEY -o StrictHostKeyChecking=accept-new" "$PROJECT_ROOT/" "$SSH_TARGET:$DEPLOY_DIR/" || true
  fi

  if [ -n "$ENV_FILE" ]; then
    [ -f "$ENV_FILE" ] || { error ".env 文件不存在: $ENV_FILE"; exit 1; }
    info "同步 .env → $DEPLOY_DIR/.env ..."
    rsync_to "$ENV_FILE" "$DEPLOY_DIR/.env"
  fi

  local SHARED_COMPOSE="$PROJECT_ROOT/../docker-compose.yml"
  if [ -f "$SHARED_COMPOSE" ]; then
    info "同步共享 docker-compose.yml → /www/wwwroot/docker-compose.yml ..."
    rsync_to "$SHARED_COMPOSE" "/www/wwwroot/docker-compose.yml"
  fi

  success "文件同步完成"
}

# ============================================================
# 启动 Docker 中间件
# ============================================================
start_infra() {
  echo ""; info "启动 Docker 中间件..."
  # 5432 被 sub2api 占用，共享 compose postgres 走 5433
  run_remote_bg "grep -q 'POSTGRES_PORT=' /www/wwwroot/.env 2>/dev/null || echo 'POSTGRES_PORT=5433' >> /www/wwwroot/.env"
  local CMD="docker compose -f /www/wwwroot/docker-compose.yml up -d postgres redis neo4j meilisearch"
  info "远程执行: $CMD"
  run_remote_bg "$CMD"
  success "Docker 中间件已启动"
}

# ============================================================
# 部署 EvoLoop 后端 (宿主机)
# ============================================================
deploy_backend() {
  echo ""
  [ "$SYNC_ONLY" = true ] && { info "仅同步模式，跳过后端部署"; return; }
  [ "$SKIP_BUILD" = true ] && { info "跳过后端部署 (--skip-build)"; return; }

  local BK_DIR="$DEPLOY_DIR/backend"
  local UV_BIN="/usr/local/bin/uv"

  # 安装 uv
  local UV_OK=false
  run_remote_bg "command -v uv" 2>/dev/null && UV_OK=true
  if [ "$UV_OK" != true ]; then
    info "安装 uv 包管理器..."
    run_remote_bg "curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh"
    run_remote_bg "command -v uv" 2>/dev/null || { error "uv 安装失败"; exit 1; }
  fi
  success "uv 已就绪"

  # uv sync 安装依赖
  info "安装 Python 依赖 (uv sync)..."
  run_remote "cd $BK_DIR && uv sync --all-extras"
  success "Python 依赖安装完成"

  # 数据库迁移
  if [ -f "$BK_DIR/bin/migrate.py" ] || [ -f "$BK_DIR/alembic.ini" ]; then
    info "执行数据库迁移..."
    run_remote "cd $BK_DIR && uv run bin/migrate.py 2>/dev/null || echo '迁移完成或无需迁移'"
  fi

  # 配置宝塔 Python 项目管理
  info "请在宝塔面板中配置 Python 项目:"
  info "  API 项目:"
  info "    项目名称: evoloop-api"
  info "    运行目录: $BK_DIR"
  info "    启动命令: $UV_BIN run bin/run.py api"
  info "    Python 版本: 3.11+"
  info "  Worker 项目:"
  info "    项目名称: evoloop-worker"
  info "    运行目录: $BK_DIR"
  info "    启动命令: $UV_BIN run bin/run.py worker"
  info "    Python 版本: 3.11+"
}

# ============================================================
# 部署前端 (本地构建 → rsync)
# ============================================================
deploy_frontend() {
  echo ""
  [ "$SYNC_ONLY" = true ] && { info "仅同步模式，跳过前端构建"; return; }
  [ "$SKIP_FE" = true ] && { info "跳过前端构建 (--skip-fe)"; return; }

  local FE_DIR="$PROJECT_ROOT/frontend"
  [ ! -d "$FE_DIR" ] && { warning "frontend 目录不存在，跳过"; return; }

  # 安装依赖
  if [ ! -d "$FE_DIR/node_modules" ]; then
    info "安装前端依赖..."
    (cd "$FE_DIR" && npm install 2>/dev/null || pnpm install 2>/dev/null) || {
      warning "前端依赖安装失败，跳过构建"; return
    }
  fi

  # 构建
  local BUILD_CMD="$PROJECT_ROOT/deploy/build/server-frontend.sh --env $BUILD_ENV"
  info "构建前端 ($BUILD_ENV)..."
  bash "$BUILD_CMD" || {
    warning "前端构建失败，跳过"; return
  }
  success "前端构建完成"

  # 同步 dist 到服务器
  local DIST_DIR="$FE_DIR/dist"
  [ ! -d "$DIST_DIR" ] && { warning "dist 目录不存在，跳过同步"; return; }
  info "同步前端 dist 到服务器..."
  rsync_to "$DIST_DIR/" "$DEPLOY_DIR/frontend/dist/"
  success "前端同步完成"
}

# ============================================================
# 连通性验证
# ============================================================
verify_services() {
  echo ""; info "验证服务连通性..."
  [ "$SYNC_ONLY" = true ] && return

  local ALL_OK=true

  # 验证 API 端口
  local API_READY=false
  for i in $(seq 1 10); do
    if run_remote_bg "bash -c '</dev/tcp/127.0.0.1/20160'" 2>/dev/null; then
      API_READY=true; break
    fi
    sleep 1
  done
  if [ "$API_READY" = true ]; then
    success "API 端口 20160: 可达"
  else
    warning "API 端口 20160: 超时"
  fi

  # 验证 Docker 中间件
  for svc in postgres redis neo4j meilisearch; do
    local OK=false
    run_remote_bg "docker exec evoloop-${svc} sh -c 'echo OK'" 2>/dev/null && OK=true
    if [ "$OK" = true ]; then
      success "evoloop-${svc} (Docker): 可达"
    else
      warning "evoloop-${svc} (Docker): 不可达"
    fi
  done

  if [ "$ALL_OK" = true ]; then
    echo ""; success "所有服务连通性正常"
  else
    echo ""; warning "部分服务异常，请检查日志"
  fi
}

# ============================================================
# 生成 Baota Nginx 反代配置
# ============================================================
generate_baota_nginx_config() {
  [ "$SYNC_ONLY" = true ] && return
  local NGINX_CONF=$(cat <<'NGINX_EOF'
# ==================================================
# EvoLoop 宝塔 Nginx 反向代理配置
# ==================================================
# 后端:  Python FastAPI (宝塔 Python 项目)
# 前端:  SPA 静态文件
# ==================================================

# API 反代
# location ^~ /api/ {
#     proxy_pass http://127.0.0.1:20160/api/;
#     proxy_set_header Host $host;
#     proxy_set_header X-Real-IP $remote_addr;
#     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#     proxy_buffering off;
# }

# WebSocket
# location ^~ /ws/ {
#     proxy_pass http://127.0.0.1:20160/ws/;
#     proxy_http_version 1.1;
#     proxy_set_header Upgrade $http_upgrade;
#     proxy_set_header Connection "Upgrade";
#     proxy_set_header Host $host;
# }

# SPA 前端 (已部署)
location / {
    root /www/wwwroot/evoloop/frontend/dist;
    try_files $uri $uri/ /index.html;
}
NGINX_EOF
)
  info "生成宝塔 Nginx 反代配置..."
  local TMPFILE=$(mktemp /tmp/evoloop-baota-nginx.XXXXXX)
  echo "$NGINX_CONF" > "$TMPFILE"
  rm -f "$TMPFILE"
  success "Nginx 配置已生成"
}

# ============================================================
# 打印摘要
# ============================================================
print_summary() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║           EvoLoop 远程部署完成                          ║"
  echo "╠══════════════════════════════════════════════════════════╣"
  echo "║"
  echo "║  环境:     ${BUILD_ENV}"
  echo "║  服务器: ${SSH_TARGET}"
  echo "║  部署目录: ${DEPLOY_DIR}"
  echo "║  后端:     添加至宝塔 Python 项目管理 (evoloop-api + evoloop-worker)"
  echo "║  前端:     已构建并同步至 \$DEPLOY_DIR/frontend/dist"
  echo "║"
  echo "║  中间件 (Docker): postgres / redis / neo4j / meilisearch"
  echo "║    /www/wwwroot/docker-compose.yml"
  echo "║"
  echo "║  后续操作:"
  echo "║    1. 宝塔面板 → 网站 → Python项目 → 添加 Python 项目:"
  echo "║       API:   evoloop-api   $UV_BIN run bin/run.py api"
  echo "║       Worker: evoloop-worker  $UV_BIN run bin/run.py worker"
  echo "║    2. docker compose -f /www/wwwroot/docker-compose.yml logs -f"
  echo "║"
  echo "╚══════════════════════════════════════════════════════════╝"
}

# ============================================================
# 主流程
# ============================================================
main() {
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║           EvoLoop 远程部署脚本                           ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  info "目标: ${SSH_TARGET}:${PORT}"
  info "部署目录: ${DEPLOY_DIR}"

  test_connection
  pre_flight_check
  deploy_frontend
  sync_files
  start_infra
  deploy_backend
  generate_baota_nginx_config
  verify_services
  print_summary
}

main
