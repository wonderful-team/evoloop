#!/bin/bash
# ARM64 安装脚本 - 使用国内镜像（在 ARM64 终端中运行）

echo "🍎 ARM64 环境设置（使用国内镜像）"
echo "================================"

# 检查架构
if [ "$(uname -m)" != "arm64" ]; then
    echo "❌ 请在 ARM64 终端中运行"
    exit 1
fi

# 删除旧环境
rm -rf .venv

# 创建虚拟环境
echo "🔧 创建虚拟环境..."
python3.11 -m venv .venv
source .venv/bin/activate

# 升级 pip
echo "📦 升级 pip..."
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# 设置国内镜像
cat > ~/.pip/pip.conf << EOF
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
EOF

# 安装核心依赖
echo "🔧 安装核心依赖..."
pip install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    pydantic-core pydantic fastapi uvicorn \
    sqlmodel alembic aiosqlite pgvector

# 安装项目依赖（跳过 SSL 检查）
echo "📦 安装项目依赖..."
pip install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -e . --no-build-isolation

# 验证
echo "🔍 验证..."
python -c "import pydantic_core; print(f'✅ pydantic-core: {pydantic_core.__version__}')"
file .venv/lib/python*/site-packages/pydantic_core/*.so | head -1

echo ""
echo "✅ 安装完成！启动服务器："
echo "  ./bin/evo dev"
