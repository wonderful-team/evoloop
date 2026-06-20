#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# Cross-platform sed in-place
sed_i() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

echo "==========================================================="
echo "  EvoLoop 环境配置切换"
echo "==========================================================="
echo ""
echo "可用场景:"
echo ""
echo " 1) 本地开发 (Desktop / Web)"
echo "    来源: .env.local"
echo ""
echo " 2) 桌面端生产部署 (macOS DMG)"
echo "    来源: .env.prod.desktop"
echo ""
echo " 3) 单用户 Web 生产部署"
echo "    来源: .env.prod.web.single"
echo ""
echo " 4) 多用户 Web 生产部署"
echo "    来源: .env.prod.web.multi"
echo ""

read -rp "请选择 [1-4]: " choice

case "$choice" in
  1) SRC=".env.local" ;;
  2) SRC=".env.prod.desktop" ;;
  3) SRC=".env.prod.web.single" ;;
  4) SRC=".env.prod.web.multi" ;;
  *) echo "无效选择"; exit 1 ;;
esac

cp "$PROJECT_ROOT/$SRC" "$ENV_FILE"
echo "已复制 $SRC → .env"

# ── 本地开发: 选择 EvoCloud 连接目标 ──
if [ "$SRC" = ".env.local" ]; then
  echo ""
  echo "请选择 EvoCloud 云端连接目标 (用于手机配对 / 多端同步):"
  echo " 1) 生产服务器 (evoloop.cn)                    ← 默认"
  echo " 2) 测试服务器 (evoloop.develop-assistant.cn)"
  echo " 3) 本地后端 (127.0.0.1:20160)"
  read -rp "请选择 [1]: " cloud_choice
  cloud_choice=${cloud_choice:-1}

  case "$cloud_choice" in
    2)
      sed_i "s|EVOCLOUD_API_URL=https://evoloop.cn|EVOCLOUD_API_URL=https://evoloop.develop-assistant.cn|" "$ENV_FILE"
      sed_i "s|EVOCLOUD_WS_URL=wss://evoloop.cn/gateway/ws|EVOCLOUD_WS_URL=wss://evoloop.develop-assistant.cn/gateway/ws|" "$ENV_FILE"
      ;;
    3)
      sed_i "s|EVOCLOUD_API_URL=https://evoloop.cn|EVOCLOUD_API_URL=http://127.0.0.1:20160|" "$ENV_FILE"
      sed_i "s|EVOCLOUD_WS_URL=wss://evoloop.cn/gateway/ws|EVOCLOUD_WS_URL=ws://127.0.0.1:20160/gateway/ws|" "$ENV_FILE"
      ;;
  esac
fi

# ── 生产 Web: 配置域名 ──
if [[ "$SRC" == .env.prod.web.* ]]; then
  echo ""
  read -rp "请输入部署域名 (留空保持 your-domain.com): " domain
  if [ -n "$domain" ]; then
    sed_i "s|VITE_API_URL=https://your-domain.com|VITE_API_URL=https://$domain|" "$ENV_FILE"
    sed_i "s|DOMAIN=your-domain.com|DOMAIN=$domain|" "$ENV_FILE"
  fi
fi

echo ""
echo "==========================================================="
echo "  ✅ 已生成 .env（来源: $SRC）"
echo "==========================================================="
