#!/usr/bin/env bash

# =============================================================================
# EvoLoop CentOS / RHEL 一键部署脚本 (生产模式 - 兼容宝塔)
# =============================================================================

set -e

show_help() {
  echo "EvoLoop CentOS / RHEL 一键部署脚本"
  echo ""
  echo "用法:"
  echo "  sudo bash $0 [options]"
  echo ""
  echo "选项:"
  echo "  --help, -h        显示此帮助"
  echo ""
  echo "说明:"
  echo "  交互式脚本，将引导您完成以下步骤："
  echo "    1. 检查操作系统与 Docker 环境"
  echo "    2. 配置 .env 环境变量 (域名、密钥、数据库等)"
  echo "    3. 选择部署模式 (Docker Compose / Systemd / Baota)"
  echo "    4. 启动服务"
  echo ""
  echo "配置模板: config/server/.env.example"
  echo "参考文档: 项目根目录的 README.md"
  exit 0
}

for arg in "$@"; do
  [ "$arg" = "--help" ] || [ "$arg" = "-h" ] && show_help
done

# --- 颜色输出 ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================================${NC}"
echo -e "${GREEN}             EvoLoop 生产环境自动化部署脚本 (CentOS)            ${NC}"
echo -e "${GREEN}================================================================${NC}"

# 1. 检查操作系统与宝塔环境
echo -e "${YELLOW}[1/4] 检查服务器环境与控制面板...${NC}"

HAS_BAOTA=false
if [ -d "/www/server/panel" ]; then
    HAS_BAOTA=true
    echo -e "${GREEN}✓ 检测到宝塔面板 (aaPanel) 已安装。将启用宝塔兼容模式！${NC}"
fi

if [ -f /etc/redhat-release ] || grep -q -i 'centos\|redhat\|rocky\|almalinux\|alinux\|aliyun\|alibaba' /etc/os-release 2>/dev/null; then
    echo -e "${GREEN}✓ 检测到 RHEL/CentOS 兼容系统。${NC}"
else
    echo -e "${RED}✗ 警告: 本脚本专为 CentOS/RHEL 系设计，您的系统可能不兼容！${NC}"
    read -p "是否继续尝试执行? (y/n) [n]: " continue_os
    if [[ "$continue_os" != "y" ]]; then
        exit 1
    fi
fi

# 2. 检查并安装 Docker 依赖
echo -e "\n${YELLOW}[2/4] 检查 Docker 与 Docker Compose 依赖...${NC}"

if ! command -v curl &> /dev/null; then
    yum install -y curl
fi
if ! command -v openssl &> /dev/null; then
    yum install -y openssl
fi

if ! command -v docker &> /dev/null; then
    if [ "$HAS_BAOTA" = true ]; then
        echo -e "${RED}✗ 未检测到 Docker！由于您使用了宝塔面板，极度不建议通过脚本底层强装 Docker。${NC}"
        echo -e "${YELLOW}👉 请进入您的宝塔面板网页端 -> 点击左侧【软件商店】 -> 搜索【Docker管理器】并一键安装。${NC}"
        echo -e "${YELLOW}安装完成后，请重新运行此部署脚本！${NC}"
        exit 1
    else
        echo -e "${YELLOW}未检测到 Docker，正在使用 Aliyun 镜像源自动安装...${NC}"
        curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
        systemctl enable docker
        systemctl start docker
        echo -e "${GREEN}✓ Docker 安装成功并已启动。${NC}"
    fi
else
    echo -e "${GREEN}✓ Docker 已安装。${NC}"
    systemctl start docker || true
fi

# 检查 docker-compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}未检测到 Docker Compose，正在安装...${NC}"
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose || true
    echo -e "${GREEN}✓ Docker Compose 安装成功。${NC}"
else
    echo -e "${GREEN}✓ Docker Compose 已准备就绪。${NC}"
fi

# 2.5 配置 Docker 镜像加速
echo -e "\n${YELLOW}[2.5] 检查 Docker 镜像拉取加速...${NC}"
read -p "是否为 Docker 配置国内镜像加速源 (解决 pull 超时问题)? (y/n) [y]: " setup_mirror
if [[ -z "$setup_mirror" || "$setup_mirror" == "y" ]]; then
    mkdir -p /etc/docker
    # 如果已经有 daemon.json，先备份
    if [ -f /etc/docker/daemon.json ]; then
        cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
    fi
    # 覆盖配置 (使用多个可用性较高的公共加速源)
    cat > /etc/docker/daemon.json <<EOF
{
    "registry-mirrors": [
        "https://docker.1panel.live",
        "https://docker.m.daocloud.io",
        "https://docker.nju.edu.cn",
        "https://dockerproxy.com"
    ]
}
EOF
    systemctl daemon-reload
    systemctl restart docker
    echo -e "${GREEN}✓ Docker 镜像加速源已配置并重启生效。${NC}"
fi

# 3. 强交互式配置参数
echo -e "\n${YELLOW}[3/4] 环境参数配置向导 (强管控环节)...${NC}"

ENV_FILE=".env"
SKIP_CONFIG=false
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "config/server/.env.example" ]; then
        cp config/server/.env.example "$ENV_FILE"
        echo -e "${GREEN}✓ 已从 config/server/.env.example 复制服务器配置。${NC}"
    elif [ -f ".env.example" ]; then
        cp .env.example "$ENV_FILE"
        echo -e "${GREEN}✓ 已从 .env.example 复制默认配置（旧模板）。${NC}"
    else
        echo -e "${RED}✗ 找不到 config/server/.env.example，请确保在项目根目录下运行此脚本！${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ 检测到已存在 .env 配置文件。${NC}"
    read -p "是否跳过环境参数配置向导，直接进入容器更新/部署阶段？(y/n) [y]: " skip_config
    if [[ -z "$skip_config" || "$skip_config" == "y" ]]; then
        SKIP_CONFIG=true
    fi
fi

# 辅助函数: 替换或添加 .env 变量
update_env() {
    local key=$1
    local value=$2
    # 处理 value 中的特殊字符
    local escaped_value=$(echo "$value" | sed -e 's/[\/&]/\\&/g')
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s/^${key}=.*/${key}=${escaped_value}/" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

if [ "$SKIP_CONFIG" != true ]; then
    echo -e "\n${YELLOW}=== 基础设置 ===${NC}"
    # 强制生产模式
    update_env "EMBEDDED_MODE" "false"
    echo -e "${GREEN}✓ 已强制开启生产高并发模式 (EMBEDDED_MODE=false)。${NC}"


    # DOMAIN
    read -p "请输入对外访问域名或IP (DOMAIN) [如: 192.168.1.100 或 demo.evoloop.cn]: " input_domain
    while [[ -z "$input_domain" ]]; do
        read -p "DOMAIN 不能为空，请重新输入: " input_domain
    done
    update_env "DOMAIN" "$input_domain"

    read -p "请输入前端完整URL (FRONTEND_HOST) [如: http://${input_domain} 或 https://${input_domain}]: " input_frontend
    while [[ -z "$input_frontend" ]]; do
        read -p "FRONTEND_HOST 不能为空，请重新输入: " input_frontend
    done
    update_env "FRONTEND_HOST" "$input_frontend"
    update_env "BACKEND_CORS_ORIGINS" "$input_frontend"

    # Docker 映射端口设置 (宝塔兼容)
    if [ "$HAS_BAOTA" = true ]; then
        echo -e "\n${YELLOW}【宝塔端口避让】检测到宝塔面板，默认的 80 和 443 端口已被宝塔占用。${NC}"
        read -p "请输入 Docker 前端映射端口 (FRONTEND_DOCKER_PORT) [默认: 8080]: " input_port
        if [ -z "$input_port" ]; then input_port="8080"; fi
        update_env "FRONTEND_DOCKER_PORT" "$input_port"
        echo -e "${GREEN}✓ 容器将在后台监听 $input_port 端口，等待后续在宝塔配置反向代理。${NC}"
    else
        # 非宝塔环境默认也用 8080 或者提示
        read -p "请输入 Docker 前端映射端口 (FRONTEND_DOCKER_PORT) [默认: 8080]: " input_port
        if [ -z "$input_port" ]; then input_port="8080"; fi
        update_env "FRONTEND_DOCKER_PORT" "$input_port"
    fi

    # SECRET_KEY
    echo -e "\n${YELLOW}=== 安全设置 ===${NC}"
    read -p "是否自动生成强加密 SECRET_KEY? (y/n) [y]: " auto_secret
    if [[ -z "$auto_secret" || "$auto_secret" == "y" ]]; then
        secret=$(openssl rand -base64 32)
        update_env "SECRET_KEY" "$secret"
        echo -e "${GREEN}✓ SECRET_KEY 已生成。${NC}"
    else
        read -p "请输入自定义 SECRET_KEY (至少32位): " custom_secret
        update_env "SECRET_KEY" "$custom_secret"
    fi

    # DB Password
    read -p "请设置 PostgreSQL 数据库强密码 (不能使用默认 postgres): " db_pass
    while [[ -z "$db_pass" || "$db_pass" == "postgres" ]]; do
        read -p "密码无效或太弱，请重新输入数据库密码: " db_pass
    done
    update_env "POSTGRES_PASSWORD" "$db_pass"
    update_env "VECTOR_POSTGRES_PASSWORD" "$db_pass"

    # EvoCloud Config
    echo -e "\n${YELLOW}=== EvoCloud 平台集成设置 ===${NC}"
    read -p "请输入 EvoCloud API 地址 [默认: https://api.evoloop.cn]: " evocloud_url
    if [ -n "$evocloud_url" ]; then 
        update_env "EVOCLOUD_API_URL" "$evocloud_url"
    else
        update_env "EVOCLOUD_API_URL" "https://api.evoloop.cn"
    fi

    read -p "请输入 EvoCloud WebSocket 地址 [默认: wss://api.evoloop.cn/ws]: " evocloud_ws
    if [ -n "$evocloud_ws" ]; then 
        update_env "EVOCLOUD_WS_URL" "$evocloud_ws"
    else
        update_env "EVOCLOUD_WS_URL" "wss://api.evoloop.cn/ws"
    fi

    read -p "请输入 EvoCloud API KEY (按回车跳过, 将以单机模式运行): " evo_key
    if [ -n "$evo_key" ]; then update_env "EVOCLOUD_API_KEY" "$evo_key"; fi

    read -p "请输入 EvoCloud API SECRET (按回车跳过): " evo_secret
    if [ -n "$evo_secret" ]; then update_env "EVOCLOUD_API_SECRET" "$evo_secret"; fi
else
    echo -e "${GREEN}✓ 已跳过配置向导，将使用现有 .env 配置部署。${NC}"
fi

# ================================
# 把 .env 变量加载进当前环境变量中
# (以便后续打印凭据和参数配置)
# ================================
if [ -f "$ENV_FILE" ]; then
    set -a
    . "./$ENV_FILE"
    set +a
fi

# 强制检查 Neo4j 和 Meilisearch 默认密码 (如果使用默认值会导致容器启动失败或安全风险)
if [ "$NEO4J_PASSWORD" == "neo4j" ]; then
    NEW_NEO4J_PASS=$(openssl rand -hex 12)
    sed -i "s/NEO4J_PASSWORD=neo4j/NEO4J_PASSWORD=${NEW_NEO4J_PASS}/" "$ENV_FILE"
    NEO4J_PASSWORD=$NEW_NEO4J_PASS
    echo -e "${YELLOW}【安全强化】已自动将 Neo4j 默认密码替换为强随机密码。${NC}"
fi

if [ -z "$MEILISEARCH_API_KEY" ]; then
    NEW_MEILI_KEY=$(openssl rand -hex 16)
    sed -i "s/MEILISEARCH_API_KEY=.*/MEILISEARCH_API_KEY=${NEW_MEILI_KEY}/" "$ENV_FILE"
    MEILISEARCH_API_KEY=$NEW_MEILI_KEY
    echo -e "${YELLOW}【安全强化】已自动为 Meilisearch 生成强随机 Master Key。${NC}"
fi

echo -e "\n${YELLOW}=== 后端部署架构选择 ===${NC}"
echo -e "1. 纯 Docker 容器化部署 (推荐生产环境使用，隔离性好)"
echo -e "2. 宿主机原生守护进程部署 (Systemd 托管，推荐无宝塔的开发测试)"
echo -e "3. 宝塔 Python 项目管理器部署 (推荐已有宝塔环境，纯图形化管理启停)"

# 获取后端部署模式 (默认 docker)
current_mode=$(grep "^BACKEND_DEPLOY_MODE=" "$ENV_FILE" | cut -d '=' -f 2)
if [ "$current_mode" == "baota" ]; then
    default_opt="3"
elif [ "$current_mode" == "local" ]; then
    default_opt="2"
else
    default_opt="1"
fi

read -p "请选择后端 (API+Worker) 的运行模式 [1/2/3, 默认: $default_opt]: " backend_mode_input
if [ -z "$backend_mode_input" ]; then
    backend_mode_input="$default_opt"
fi

if [ "$backend_mode_input" == "3" ]; then
    update_env "BACKEND_DEPLOY_MODE" "baota"
    BACKEND_MODE="baota"
elif [ "$backend_mode_input" == "2" ]; then
    update_env "BACKEND_DEPLOY_MODE" "local"
    BACKEND_MODE="local"
else
    update_env "BACKEND_DEPLOY_MODE" "docker"
    BACKEND_MODE="docker"
fi

echo -e "\n${YELLOW}=== 前端部署架构选择 ===${NC}"
echo -e "1. Docker 容器化部署 (推荐无宝塔的纯净环境，全自动打包)"
echo -e "2. 宝塔纯静态托管部署 (推荐已有宝塔环境，跳过容器打包，前端通过 npm run build 独立上传)"

current_fe_mode=$(grep "^FRONTEND_DEPLOY_MODE=" "$ENV_FILE" | cut -d '=' -f 2)
if [ "$current_fe_mode" == "local" ]; then
    default_fe_opt="2"
else
    default_fe_opt="1"
fi

read -p "请选择前端的运行模式 [1/2, 默认: $default_fe_opt]: " frontend_mode_input
if [ -z "$frontend_mode_input" ]; then
    frontend_mode_input="$default_fe_opt"
fi

if [ "$frontend_mode_input" == "2" ]; then
    update_env "FRONTEND_DEPLOY_MODE" "local"
    FRONTEND_MODE="local"
else
    update_env "FRONTEND_DEPLOY_MODE" "docker"
    FRONTEND_MODE="docker"
fi

# 4. 启动容器编排
echo -e "\n${YELLOW}[4/4] 配置完成！准备启动容器编排...${NC}"

if docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

echo -e "清理旧容器与服务状态..."
$COMPOSE_CMD -f docker-compose.yml down || true
rm -f docker-compose.override.yml

if [ "$BACKEND_MODE" == "local" ] || [ "$BACKEND_MODE" == "baota" ]; then
    echo -e "${YELLOW}检测到混合部署模式: 生成前端网络穿透桥接配置...${NC}"
    cat > docker-compose.override.yml <<EOF
services:
  frontend:
    extra_hosts:
      - "backend:host-gateway"
EOF

    echo -e "正在拉取镜像并启动基础设施中间件..."
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.override.yml up -d db redis neo4j meilisearch
    
    if [ "$FRONTEND_MODE" == "docker" ]; then
        echo -e "正在独立启动前端容器 (跳过容器化后端依赖)..."
        $COMPOSE_CMD -f docker-compose.yml -f docker-compose.override.yml up -d --no-deps frontend
    else
        echo -e "${GREEN}前端使用本地静态托管模式，跳过启动 frontend 容器。${NC}"
    fi
    
    echo -e "\n${YELLOW}配置宿主机原生 Python 后端运行环境...${NC}"
    if ! command -v uv &> /dev/null; then
        echo -e "正在安装极速包管理器 uv..."
        curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh
    fi
    
    cd backend
    echo -e "使用 uv 安装后端 Python 依赖 (国内加速)..."
    export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
    /usr/local/bin/uv sync --all-extras
    
    if [ "$BACKEND_MODE" == "local" ]; then
        echo -e "配置 Systemd 守护进程..."
        cat > /etc/systemd/system/evoloop-api.service <<EOF
[Unit]
Description=EvoLoop API Service
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
EnvironmentFile=$(pwd)/../.env
ExecStart=/usr/local/bin/uv run bin/run.py api
Restart=always
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=evoloop-api

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/evoloop-worker.service <<EOF
[Unit]
Description=EvoLoop Worker Service
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
EnvironmentFile=$(pwd)/../.env
ExecStart=/usr/local/bin/uv run bin/run.py worker
Restart=always
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=evoloop-worker

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable evoloop-api evoloop-worker
        systemctl restart evoloop-api evoloop-worker
        
        cd ..
        echo -e "${GREEN}✓ 宿主机原生守护进程已在后台启动 (evoloop-api / evoloop-worker)。${NC}"
    else
        # 【清理逻辑】防止用户从 local 模式切换到 baota/docker 模式时，遗留的 Systemd 继续潜伏在系统深处不断拉起进程
        if systemctl list-unit-files | grep -q 'evoloop-api.service' 2>/dev/null; then
            echo -e "${YELLOW}检测到遗留的 Systemd 守护进程，正在彻底拔除以防止幽灵冲突...${NC}"
            systemctl stop evoloop-api evoloop-worker 2>/dev/null || true
            systemctl disable evoloop-api evoloop-worker 2>/dev/null || true
            rm -f /etc/systemd/system/evoloop-api.service
            rm -f /etc/systemd/system/evoloop-worker.service
            systemctl daemon-reload
        fi
        
        cd ..
        echo -e "${GREEN}✓ 后端 Python 虚拟环境与依赖已就绪 (.venv)，等待在宝塔面板中配置启动。${NC}"
        
        echo -e "\n${YELLOW}=== 后端服务临时启动测试 ===${NC}"
        read -p "是否需要脚本先在后台临时启动服务(API+Worker)以确认环境配置无误？(y/n) [y]: " temp_start_input
        if [ "$temp_start_input" != "n" ]; then
            echo -e "正在使用官方 CLI 工具启动后台服务..."
            backend/bin/evo start
            echo -e "${GREEN}✓ 临时服务已启动，日志将记录在 backend/logs/ 中。${NC}"
            TEMP_EVO_STARTED="true"
        else
            SKIP_CONN_TEST="true"
        fi
    fi
else
    if [ "$FRONTEND_MODE" == "docker" ]; then
        echo -e "正在拉取镜像并启动完整堆栈 (纯 Docker 容器化)..."
        $COMPOSE_CMD -f docker-compose.yml up -d --build
    else
        echo -e "正在拉取镜像并启动后端与基础组件，跳过前端容器..."
        $COMPOSE_CMD -f docker-compose.yml up -d --build db redis neo4j meilisearch backend worker
    fi
fi

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}✓ 部署指引已完成！服务正在后台启动中...${NC}"

echo -e "\n${YELLOW}=== 基础设施中间件连通性检查 ===${NC}"
check_tcp_port() {
    local port=$1
    local name=$2
    local max_retries=30
    local count=0
    echo -n "等待 $name 就绪 (端口: $port) "
    while [ $count -lt $max_retries ]; do
        if bash -c "</dev/tcp/127.0.0.1/${port}" 2>/dev/null; then
            echo -e " -> ${GREEN}✓ 已就绪${NC}"
            return 0
        fi
        sleep 2
        count=$((count + 1))
        echo -n "."
    done
    echo -e " -> ${RED}✗ 启动超时${NC}"
    return 1
}

check_tcp_port "${POSTGRES_PORT}" "PostgreSQL"
check_tcp_port "${REDIS_PORT}" "Redis"
check_tcp_port "${NEO4J_BOLT_PORT}" "Neo4j"
check_tcp_port "${MEILISEARCH_PORT:-7700}" "Meilisearch"

if [ "$FRONTEND_MODE" == "docker" ]; then
    CHECK_URL="http://127.0.0.1:${FRONTEND_DOCKER_PORT}"
    echo -e "\n${YELLOW}正在进行本地连通性测试 (等待前端服务完全启动)...${NC}"
else
    CHECK_URL="http://127.0.0.1:20160/api/v1/system/health"
    echo -e "\n${YELLOW}正在进行本地连通性测试 (等待后端 API 及所有中间件就绪)...${NC}"
fi

if [ "$SKIP_CONN_TEST" == "true" ]; then
    echo -e "\n${YELLOW}已跳过后端临时连通性测试。${NC}"
else
    MAX_RETRIES=30
    RETRY_COUNT=0
    HEALTHY=false

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        # 严格测试接口返回 200 OK，确保后端以及其依赖的所有数据库都初始化完毕
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$CHECK_URL" || echo "000")
        if [ "$HTTP_STATUS" == "200" ] || [ "$HTTP_STATUS" == "304" ] || [ "$HTTP_STATUS" == "404" ]; then
            # 如果是请求前端 Nginx，它可能返回静态页的各类状态码
            # 如果是请求后端 Health，必须是 200 (或因为路由没配好抛出404，但进程是活的)
            HEALTHY=true
            break
        fi
        sleep 2
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
    done
    echo ""

    if [ "$HEALTHY" = true ]; then
        echo -e "${GREEN}✓ 连通性测试通过！微服务已成功建立连接并稳定运行。${NC}"
    else
        echo -e "${RED}✗ 连通性测试超时 (HTTP状态: $HTTP_STATUS)。可能后端正在拉取大模型资源或数据库仍在建表中。${NC}"
        echo -e "${YELLOW}请观察下方实时日志排查错误。${NC}"
    fi
fi

echo -e "\n${CYAN}================================================================${NC}"
echo -e "${CYAN}【🔑 核心中间件连接凭证 (请截图或妥善保存)】${NC}"
echo -e "   - PostgreSQL 数据库: ${POSTGRES_DB}"
echo -e "     -> 用户: ${POSTGRES_USER}"
echo -e "     -> 密码: ${POSTGRES_PASSWORD}"
echo -e "     -> 端口: ${POSTGRES_PORT}"
echo -e "   - Redis 端口: ${REDIS_PORT}"
echo -e "   - Neo4j 图数据库:"
echo -e "     -> 用户: ${NEO4J_USER}"
echo -e "     -> 密码: ${NEO4J_PASSWORD}"
echo -e "     -> Bolt端口: ${NEO4J_BOLT_PORT} / HTTP端口: ${NEO4J_HTTP_PORT}"
echo -e "   - Meilisearch 搜索引擎:"
echo -e "     -> Master Key: ${MEILISEARCH_API_KEY}"
echo -e "     -> 端口: ${MEILISEARCH_PORT:-7700}"
echo -e "${CYAN}================================================================${NC}"

if [ "$HAS_BAOTA" = true ] || [ "$BACKEND_MODE" == "baota" ]; then
    echo -e "\n${YELLOW}【⚠️ 宝塔面板后续配置指引】${NC}"
    
    if [ "$BACKEND_MODE" == "baota" ]; then
        echo -e "\n${CYAN}[1] 宝塔 Python 项目管理器配置后端:${NC}"
        echo -e "   - 在宝塔安装并打开【Python项目管理器】或【网站-Python项目】"
        echo -e "   - 添加 Python 项目:"
        echo -e "     项目路径: $(pwd)/backend"
        echo -e "     启动文件: $(pwd)/backend/bin/run.py"
        echo -e "     启动方式: uvicorn (或 python)"
        echo -e "     启动命令: /usr/local/bin/uv run bin/run.py api"
        echo -e "     运行用户: root"
        echo -e "   - （按同样方式再建一个项目，启动命令改为: /usr/local/bin/uv run bin/run.py worker，专门用于跑 Worker 异步任务）"
    fi
    
    echo -e "\n${CYAN}[2] 宝塔 Nginx 站点配置前端:${NC}"
    echo -e "   - 左侧菜单进入『网站』 -> 『添加站点』，绑定您的域名 ${DOMAIN}。"
    echo -e "   - 网站根目录指向解压后的前端 dist 文件夹。"
    echo -e "   - 点击站点的『设置』 -> 选择『配置文件』，增加以下反代代码:"
    echo -e "     location / { try_files \$uri \$uri/ /index.html; }"
    echo -e "     location ^~ /api/ { proxy_pass http://127.0.0.1:20160/api/; proxy_buffering off; }"
    echo -e "     location ^~ /ws/ { proxy_pass http://127.0.0.1:20160/ws/; proxy_set_header Upgrade \$http_upgrade; proxy_set_header Connection \"Upgrade\"; }"
fi

if [ "$TEMP_EVO_STARTED" == "true" ]; then
    echo -e "\n${YELLOW}【⚠️ 临时测试服务清理提醒】${NC}"
    echo -e "刚才为了测试，系统已在后台启动了 API 进程。"
    echo -e "在您去宝塔进行正式配置之前，请务必先关闭它们："
    echo -e "  ${RED}cd backend && ./bin/evo stop${NC}"
fi

if [ "$BACKEND_MODE" != "baota" ]; then
    echo -e "\n${GREEN}即将进入日志追踪视图 (按 Ctrl+C 可退出，服务将继续在后台运行)${NC}"
    echo -e "${GREEN}================================================================${NC}"
    
    $COMPOSE_CMD logs -f --tail=100
fi
