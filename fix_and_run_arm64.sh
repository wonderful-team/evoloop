#!/bin/bash
set -e

echo "🚀 EvoLoop ARM64 环境配置 (使用 pyproject.toml)"
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend

# 设置国内镜像（解决 SSL 和速度问题）
export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
# 备选阿里云：export UV_DEFAULT_INDEX="https://mirrors.aliyun.com/pypi/simple"

# 强制 ARM64 架构
export ARCHFLAGS="-arch arm64"
export UV_PYTHON_PREFERENCE=only-managed

# 清理旧环境
echo "🧹 清理旧环境..."
rm -rf .venv uv.lock

# 创建新环境（uv 会自动解析 pyproject.toml）
echo "📦 创建 ARM64 虚拟环境..."
uv venv

# 使用 sync 从 pyproject.toml 安装（一次性装完所有依赖）
echo "⬇️ 从 pyproject.toml 安装依赖（国内镜像）..."
uv sync --no-dev

# 如果需要开发依赖（测试等），用：
# uv sync

echo "✅ 依赖安装完成！"
echo "🎯 启动开发服务器..."
./bin/evo dev
