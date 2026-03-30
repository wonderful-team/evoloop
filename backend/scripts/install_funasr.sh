#!/bin/bash
# FunASR 安装脚本
# 用法: ./scripts/install_funasr.sh

set -e

echo "🎙️  FunASR 安装脚本"
echo "===================="

# 检测操作系统
OS="$(uname -s)"
ARCH="$(uname -m)"

echo "🔍 检测系统: $OS $ARCH"

if [ "$OS" = "Darwin" ]; then
    echo "✅ 检测到 macOS"
    if [ "$ARCH" = "arm64" ]; then
        echo "   芯片: Apple Silicon (M1/M2/M3)"
        echo "   提示: 确保使用 ARM64 版本的 Python"
    else
        echo "   芯片: Intel"
    fi
else
    echo "✅ 检测到 Linux"
fi

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo ""
    echo "⚠️  未检测到虚拟环境，请先激活："
    echo "   source .venv/bin/activate"
    exit 1
fi

echo "✅ 虚拟环境: $VIRTUAL_ENV"

# macOS 特定提示
if [ "$OS" = "Darwin" ]; then
    echo ""
    echo "📋 macOS 安装提示:"
    echo "   1. 如果遇到 numba 编译错误，建议先安装 llvm:"
    echo "      brew install llvm libomp"
    echo "   2. 或者使用 conda 避免编译:"
    echo "      conda install -c conda-forge numba llvmlite"
    echo ""
fi

# 检测是否有 conda
if command -v conda &> /dev/null; then
    echo "✅ 检测到 Conda，使用 Conda 安装依赖..."
    conda install -c conda-forge numba llvmlite -y
else
    echo "⚠️  未检测到 Conda"
    
    # macOS 尝试安装 llvm
    if [ "$OS" = "Darwin" ] && command -v brew &> /dev/null; then
        echo "📦 尝试安装 llvm..."
        brew install llvm libomp 2>/dev/null || echo "   llvm 可能已安装"
        
        # 设置环境变量
        if [ "$ARCH" = "arm64" ]; then
            export PATH="/opt/homebrew/opt/llvm/bin:$PATH"
            export LLVM_CONFIG="/opt/homebrew/opt/llvm/bin/llvm-config"
        else
            export PATH="/usr/local/opt/llvm/bin:$PATH"
            export LLVM_CONFIG="/usr/local/opt/llvm/bin/llvm-config"
        fi
    fi
fi

# 安装 PyTorch
echo ""
echo "📦 安装 PyTorch..."
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    echo "   安装 Apple Silicon 优化版本..."
fi
uv pip install torch torchaudio --upgrade

# 安装 FunASR
echo ""
echo "📦 安装 FunASR..."
if [ "$OS" = "Darwin" ]; then
    echo "   macOS 安装可能需要几分钟（编译 numba）..."
fi

uv pip install funasr modelscope || {
    echo ""
    echo "❌ 安装失败，尝试使用 --no-build-isolation..."
    uv pip install funasr modelscope --no-build-isolation
}

# 验证安装
echo ""
echo "🔍 验证安装..."
python -c "
try:
    import funasr
    from funasr import AutoModel
    print('✅ FunASR 安装成功!')
    print(f'   版本: {funasr.__version__}')
except ImportError as e:
    print(f'❌ 安装失败: {e}')
    exit(1)
"

# 预下载模型（可选）
echo ""
read -p "是否预下载 FunASR 模型？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "📥 预下载模型 paraformer-zh..."
    echo "   模型大小: ~220MB，下载时间取决于网络..."
    python -c "
from funasr import AutoModel
model = AutoModel(
    model='damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch',
    model_revision='v2.0.4',
    device='cpu'
)
print('✅ 模型下载完成')
"
fi

echo ""
echo "🎉 FunASR 安装完成!"
echo ""

# macOS 特定提示
if [ "$OS" = "Darwin" ]; then
    echo "📋 macOS 使用提示:"
    echo "   • 如果将来遇到 numba 错误，可能需要重新安装："
    echo "     brew reinstall llvm && export LLVM_CONFIG=/opt/homebrew/opt/llvm/bin/llvm-config"
    echo ""
fi

echo "测试命令:"
echo "  curl http://localhost:8000/api/v1/audio/stt/providers"
echo ""
echo "详细文档:"
echo "  docs/VOICE_SETUP.md"
echo "  docs/FUNASR_MACOS.md"
