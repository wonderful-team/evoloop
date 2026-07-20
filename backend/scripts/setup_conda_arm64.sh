#!/bin/bash
# 使用 Miniconda 安装 ARM64 Python

echo "🍎 安装 Miniconda (ARM64)..."

# 下载 ARM64 版本的 Miniconda
if [ ! -d "$HOME/miniconda3" ]; then
    curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh
    bash Miniconda3-latest-MacOSX-arm64.sh -b -p $HOME/miniconda3
    rm Miniconda3-latest-MacOSX-arm64.sh
fi

# 初始化 conda
source $HOME/miniconda3/bin/activate

# 创建 ARM64 环境
echo "🔧 创建 ARM64 Python 3.11 环境..."
conda create -n evoloop python=3.11 -y
conda activate evoloop

# 验证架构
echo "验证架构:"
python -c "import platform; print(f'Python: {platform.python_version()}')
print(f'Machine: {platform.machine()}')
print(f'Processor: {platform.processor()}')"

# 安装依赖
echo "📦 安装依赖..."
pip install -e /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend

echo "✅ ARM64 环境安装完成！"
echo "启动服务器:"
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
./bin/evo dev
