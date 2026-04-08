#!/bin/bash
# 修复 SSL 问题并运行服务器（在 ARM64 终端中使用）

echo "🔧 修复 SSL 证书问题..."

# 检查是否在 ARM64 终端中
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "❌ 当前终端是 $ARCH 架构"
    echo "请在原生 ARM64 终端中运行此脚本"
    echo "（右键终端.app → 获取信息 → 取消勾选'使用 Rosetta 打开'）"
    exit 1
fi

echo "✅ 检测到 ARM64 架构"

# 如果虚拟环境不存在，创建它
if [ ! -d ".venv" ]; then
    echo "🔧 创建 ARM64 虚拟环境..."
    python3.11 -m venv .venv
fi

source .venv/bin/activate

# 修复 SSL
echo "🔧 安装/更新 SSL 证书..."
pip install --upgrade certifi --trusted-host pypi.org --trusted-host files.pythonhosted.org

# 设置环境变量使用系统 SSL
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
export REQUESTS_CA_BUNDLE=$SSL_CERT_FILE

# 安装依赖（使用 trusted-host）
echo "📦 安装依赖..."
pip install \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    pydantic-core pydantic fastapi uvicorn

# 验证
echo "🔍 验证架构..."
python -c "import platform; print(f'Python: {platform.machine()}')"
file .venv/lib/python*/site-packages/pydantic_core/*.so

# 测试导入
echo "🧪 测试导入..."
python -c "import pydantic_core; import fastapi; print('✅ 导入成功')"

# 启动服务器
echo "🚀 启动服务器..."
./bin/evo dev
