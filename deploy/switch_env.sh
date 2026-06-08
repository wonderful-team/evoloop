#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

echo "==========================================================="
echo "  EvoLoop 一键配置切换工具 (Environment Switcher)"
echo "==========================================================="
echo "此工具将基于您的选择自动生成正确的 .env 配置文件"
echo ""

# 1. 选择端侧平台
echo "请选择端侧平台 (Target Platform):"
OPTIONS_PLATFORM=(
  "本地桌面客户端 (Desktop Client) - MacOS/Windows"
  "服务器单用户私有化部署 (Single User Server) - Linux/Windows"
  "云端多租户版 (Cloud Multi-tenant) - CentOS/Linux"
  "移动端 (Mobile Client) - Android/iOS"
  "退出 (Cancel)"
)
select opt in "${OPTIONS_PLATFORM[@]}"; do
  case $REPLY in
    1) TARGET="desktop"; break;;
    2) TARGET="server_single"; break;;
    3) TARGET="server_multi"; break;;
    4) TARGET="mobile"; break;;
    5) exit 0;;
    *) echo "无效的选择，请重试。";;
  esac
done

echo ""

# 1.5 如果是单用户服务器，询问是否开启内嵌模式
SINGLE_SERVER_EMBEDDED="false"
if [ "$TARGET" = "server_single" ]; then
  echo "请选择单用户服务器是否开启内嵌模式 (Embedded Mode):"
  OPTIONS_EMBEDDED=(
    "开启 (True) - 使用 SQLite + 内部队列 (轻量级部署，无外部依赖)"
    "关闭 (False) - 使用 PostgreSQL + Redis (标准生产部署)"
  )
  select opt in "${OPTIONS_EMBEDDED[@]}"; do
    case $REPLY in
      1) SINGLE_SERVER_EMBEDDED="true"; break;;
      2) SINGLE_SERVER_EMBEDDED="false"; break;;
      *) echo "无效的选择，请重试。";;
    esac
  done
  echo ""
fi

echo ""

# 2. 选择运行环境
echo "请选择运行环境 (Environment):"
OPTIONS_ENV=(
  "开发环境 (Local Development)"
  "测试环境 (Test Environment)"
  "生产环境 (Production)"
  "退出 (Cancel)"
)
select opt in "${OPTIONS_ENV[@]}"; do
  case $REPLY in
    1) ENV_TYPE="dev"; ENV_VAL="local"; break;;
    2) ENV_TYPE="test"; ENV_VAL="staging"; break;;
    3) ENV_TYPE="prod"; ENV_VAL="production"; break;;
    4) exit 0;;
    *) echo "无效的选择，请重试。";;
  esac
done

echo ""

# 3. 如果是本地开发，询问云端服务器的连接目标 (EvoCloud)
CLOUD_API_URL="http://127.0.0.1:20160"
CLOUD_WS_URL="ws://127.0.0.1:20160/gateway/ws"
if [ "$ENV_TYPE" = "dev" ]; then
  echo "请选择云端服务器 (EvoCloud) 连接目标:"
  OPTIONS_API=(
    "本地后端 (Local: 127.0.0.1)"
    "测试服务器 (Test: evoloop.develop-assistant.cn)"
    "生产服务器 (Prod: evoloop.cn)"
  )
  select opt in "${OPTIONS_API[@]}"; do
    case $REPLY in
      1) 
        CLOUD_API_URL="http://127.0.0.1:20160"
        CLOUD_WS_URL="ws://127.0.0.1:20160/gateway/ws"
        break;;
      2) 
        CLOUD_API_URL="https://evoloop.develop-assistant.cn"
        CLOUD_WS_URL="wss://evoloop.develop-assistant.cn/gateway/ws"
        break;;
      3) 
        CLOUD_API_URL="https://evoloop.cn"
        CLOUD_WS_URL="wss://evoloop.cn/gateway/ws"
        break;;
      *) echo "无效的选择，请重试。";;
    esac
  done
  echo ""
fi

echo ""
echo "正在生成 $TARGET ($ENV_TYPE) 的配置到 $ENV_FILE ..."

# ---------------------------------------------------------------------------
# 生成 .env 内容
# ---------------------------------------------------------------------------
cat <<EOF > "$ENV_FILE"
# =============================================================================
# EvoLoop 全局环境变量 (自动生成)
# 端侧: $TARGET
# 环境: $ENV_TYPE
# =============================================================================

ENVIRONMENT=$ENV_VAL
VITE_AMAP_KEY=8fee0670ba8e3655efeb623e264fd2c0

EOF

# 根据 Target 配置
if [ "$TARGET" = "desktop" ]; then
    cat <<EOF >> "$ENV_FILE"
# -----------------------------------------------------------------------------
# 桌面端特定配置 (内嵌 SQLite)
# -----------------------------------------------------------------------------
PORT=20160
FRONTEND_PORT=5173
EMBEDDED_MODE=true
MULTI_TENANT_MODE=false
MOBILE_SYNC_ENABLED=false
EVOLOOP_APP_DATA_DIR=~/.evoloop

# 桌面端特有能力：允许 AI 控制本地浏览器与桌面环境
ENABLE_ENVIRONMENT_CONTROLS=true

# 桌面端 API 请求地址 (本地侧边栏后端)
VITE_API_URL=http://127.0.0.1:20160
VITE_EVOCLOUD_MEMBER_BASE_URL=\${EVOCLOUD_API_URL}/member

# 后端 EvoCloud 配置
EVOCLOUD_API_URL=$CLOUD_API_URL
EVOCLOUD_WS_URL=$CLOUD_WS_URL

# AI 模型配置 (桌面推荐本地模型)
LLM_API_KEY=lm-studio
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=local-model
EMBEDDING_DIMENSIONS=768
EOF

elif [ "$TARGET" = "server_single" ]; then
    cat <<EOF >> "$ENV_FILE"
# -----------------------------------------------------------------------------
# 服务器单用户私有化部署特定配置
# -----------------------------------------------------------------------------
PORT=20160
FRONTEND_PORT=5173
EMBEDDED_MODE=$SINGLE_SERVER_EMBEDDED
MULTI_TENANT_MODE=false
EVOLOOP_APP_DATA_DIR=~/.evoloop
MOBILE_SYNC_ENABLED=false

EOF

    if [ "$SINGLE_SERVER_EMBEDDED" = "false" ]; then
        cat <<EOF >> "$ENV_FILE"
# 请填写真实的数据库和 Redis 地址
POSTGRES_SERVER=postgresql://user:pass@localhost:5432/evoloop
REDIS_URL=redis://localhost:6379/0

EOF
    fi

    cat <<EOF >> "$ENV_FILE"
# AI 模型配置
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
EMBEDDING_DIMENSIONS=768
EOF

    if [ "$ENV_TYPE" = "dev" ]; then
        echo "VITE_API_URL=http://127.0.0.1:20160" >> "$ENV_FILE"
        echo "EVOCLOUD_API_URL=$CLOUD_API_URL" >> "$ENV_FILE"
        echo "EVOCLOUD_WS_URL=$CLOUD_WS_URL" >> "$ENV_FILE"
    elif [ "$ENV_TYPE" = "test" ]; then
        echo "VITE_API_URL=https://evoloop.develop-assistant.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_API_URL=https://evoloop.develop-assistant.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_WS_URL=wss://evoloop.develop-assistant.cn/gateway/ws" >> "$ENV_FILE"
    else
        echo "VITE_API_URL=https://evoloop.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_API_URL=https://evoloop.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_WS_URL=wss://evoloop.cn/gateway/ws" >> "$ENV_FILE"
    fi

elif [ "$TARGET" = "server_multi" ]; then
    cat <<EOF >> "$ENV_FILE"
# -----------------------------------------------------------------------------
# 云端多租户版特定配置
# -----------------------------------------------------------------------------
PORT=20161
FRONTEND_PORT=5174
EMBEDDED_MODE=false
MULTI_TENANT_MODE=true
EVOLOOP_APP_DATA_DIR=/var/evoloop/data

# 云端推荐使用 Docker 沙盒来隔离代码执行环境
EXECUTION_MODE=docker

# 请填写真实的数据库和 Redis 地址 (隔离配置)
POSTGRES_SERVER=postgresql://user:pass@localhost:5432/evoloop_multi
REDIS_URL=redis://localhost:6379/1

# AI 模型配置
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
EMBEDDING_DIMENSIONS=768
EOF

    if [ "$ENV_TYPE" = "dev" ]; then
        echo "VITE_API_URL=http://127.0.0.1:20160" >> "$ENV_FILE"
        echo "EVOCLOUD_API_URL=$CLOUD_API_URL" >> "$ENV_FILE"
        echo "EVOCLOUD_WS_URL=$CLOUD_WS_URL" >> "$ENV_FILE"
    elif [ "$ENV_TYPE" = "test" ]; then
        echo "VITE_API_URL=https://evoloop.develop-assistant.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_API_URL=https://evoloop.develop-assistant.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_WS_URL=wss://evoloop.develop-assistant.cn/gateway/ws" >> "$ENV_FILE"
    else
        echo "VITE_API_URL=https://evoloop.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_API_URL=https://evoloop.cn" >> "$ENV_FILE"
        echo "EVOCLOUD_WS_URL=wss://evoloop.cn/gateway/ws" >> "$ENV_FILE"
    fi

elif [ "$TARGET" = "mobile" ]; then
    cat <<EOF >> "$ENV_FILE"
# -----------------------------------------------------------------------------
# 移动端特定配置
# -----------------------------------------------------------------------------
PORT=20160
FRONTEND_PORT=5173
EOF
    if [ "$ENV_TYPE" = "dev" ]; then
        cat <<EOF >> "$ENV_FILE"
# 移动端本地开发，已根据您的选择指向 API
VITE_EVOCLOUD_API_URL=$CLOUD_API_URL
VITE_EVOLOOP_WS_URL=$CLOUD_WS_URL
EOF
    elif [ "$ENV_TYPE" = "test" ]; then
        cat <<EOF >> "$ENV_FILE"
VITE_EVOCLOUD_API_URL=https://evoloop.develop-assistant.cn
VITE_EVOLOOP_WS_URL=wss://evoloop.develop-assistant.cn/gateway/ws
EOF
    else
        cat <<EOF >> "$ENV_FILE"
VITE_EVOCLOUD_API_URL=https://evoloop.cn
VITE_EVOLOOP_WS_URL=wss://evoloop.cn/gateway/ws
EOF
    fi
fi

# 根据环境设置调试模式
if [ "$ENV_TYPE" = "dev" ]; then
    echo "VITE_STARTUP_DEBUG_MODE=true" >> "$ENV_FILE"
else
    echo "VITE_STARTUP_DEBUG_MODE=false" >> "$ENV_FILE"
fi

echo "==========================================================="
echo "✅ 成功生成 .env 配置文件"
echo "👉 您可以查看 $ENV_FILE 以确认详细内容"
echo "==========================================================="
