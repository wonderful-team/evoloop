#!/bin/bash
# ARM64 完整修复脚本 - 使用 uv 避免依赖解析问题

set -e

echo "🍎 ARM64 环境修复脚本"
echo "======================"

# 检查架构
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "❌ 当前终端是 $ARCH 架构，请在 ARM64 终端中运行"
    exit 1
fi

echo "✅ 检测到 ARM64 架构"

# 清理旧环境
echo "🧹 清理旧环境..."
rm -rf .venv

# 检查 uv
if ! command -v uv &> /dev/null; then
    echo "📦 安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 创建虚拟环境
echo "🔧 创建虚拟环境..."
uv venv --python python3.11
source .venv/bin/activate

# 安装核心依赖（分批避免解析问题）
echo "📦 安装核心依赖..."

# 第 1 批：基础运行时
uv pip install \
    pydantic-core \
    pydantic \
    typing-extensions \
    annotated-types

# 第 2 批：Web 框架
uv pip install \
    fastapi \
    uvicorn \
    starlette \
    anyio

# 第 3 批：数据库
uv pip install \
    aiosqlite \
    sqlalchemy \
    alembic \
    sqlmodel

# 第 4 批：其他必要依赖
uv pip install \
    pgvector \
    tenacity \
    jinja2 \
    pyyaml

# 验证架构
echo "🔍 验证架构..."
python -c "import platform; print(f'Python: {platform.machine()}')"
SO_FILE=$(find .venv -name "_pydantic_core*.so" | head -1)
if [ -n "$SO_FILE" ]; then
    file "$SO_FILE"
fi

# 测试导入
echo "🧪 测试导入..."
python -c "
import pydantic_core
import pydantic
import fastapi
import uvicorn
print(f'✅ pydantic-core: {pydantic_core.__version__}')
print(f'✅ pydantic: {pydantic.__version__}')
print(f'✅ fastapi: {fastapi.__version__}')
print('✅ 所有核心依赖导入成功！')
"

echo ""
echo "✅ 安装完成！"
echo ""
echo "🚀 启动服务器："
echo "  ./bin/evo dev"
echo ""

# 询问是否启动
read -p "是否立即启动服务器？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ./bin/evo dev
fi
