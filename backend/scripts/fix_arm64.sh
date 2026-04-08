#!/bin/bash
# 修复 ARM64 架构问题

echo "🔧 ARM64 架构修复脚本"
echo "======================"

# 检查是否在 Rosetta 下运行
if [ "$(uname -m)" = "x86_64" ]; then
    echo "⚠️  当前终端在 Rosetta (x86_64) 模式下运行"
    echo ""
    echo "方案 1: 在原生 ARM64 终端中运行此脚本"
    echo "方案 2: 使用以下命令创建 ARM64 虚拟环境:"
    echo ""
    echo "  arch -arm64 /usr/local/bin/python3.11 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  arch -arm64 pip install -r requirements.txt"
    echo ""
    echo "方案 3: 使用 conda 安装（推荐）"
    echo ""
fi

# 尝试使用 arch -arm64 强制 ARM64
echo "🔧 尝试使用 ARM64 架构..."
rm -rf .venv

# 使用系统 Python 的 ARM64 架构
arch -arm64 python3.11 -m venv .venv
source .venv/bin/activate

# 升级 pip
echo "📦 升级 pip..."
arch -arm64 pip install --upgrade pip

# 安装核心依赖（强制从源码编译以确保 ARM64）
echo "🔧 安装 pydantic-core（从源码编译 ARM64 版本）..."
arch -arm64 pip install pydantic-core --no-binary pydantic-core --no-cache-dir

echo "🔧 安装其他依赖..."
arch -arm64 pip install pydantic fastapi uvicorn --no-cache-dir

echo ""
echo "✅ 安装完成！验证架构..."
file .venv/lib/python3.11/site-packages/pydantic_core/*.so

echo ""
echo "🧪 测试导入..."
python -c "import pydantic_core; import fastapi; print('✅ 成功！')"
