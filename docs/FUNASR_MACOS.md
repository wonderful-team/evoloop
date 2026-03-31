# FunASR macOS 安装指南

FunASR 完全支持 macOS，包括 Intel 和 Apple Silicon (M1/M2/M3) 芯片。

## 系统要求

| 配置 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 系统版本 | macOS 11 (Big Sur) | macOS 13+ (Ventura) |
| 内存 | 4GB | 8GB+ |
| 芯片 | Intel / Apple Silicon | Apple Silicon M1/M2/M3 |
| 存储 | 2GB 可用空间 | 5GB+（用于模型缓存） |

## 安装步骤

### 步骤 1：确保使用正确的 Python

```bash
# 检查 Python 版本（需要 3.9+）
python3 --version

# 如果使用 Homebrew Python，确保路径正确
which python3
# 预期输出：/opt/homebrew/bin/python3 (Apple Silicon) 或 /usr/local/bin/python3 (Intel)
```

### 步骤 2：激活虚拟环境

```bash
cd evoloop/backend
source .venv/bin/activate

# 确认在虚拟环境中
which python
# 预期输出：.../evoloop/backend/.venv/bin/python
```

### 步骤 3：安装依赖

#### 对于 Apple Silicon (M1/M2/M3) 芯片：

```bash
# 1. 安装 PyTorch（支持 Apple Silicon 加速）
uv pip install torch torchaudio

# 2. 安装 numba（可能需要单独处理）
# 方式 A：使用 conda（推荐）
conda install -c conda-forge numba llvmlite

# 方式 B：使用 pip（如果 conda 不可用）
# 先安装 llvm
brew install llvm
export LLVM_CONFIG="/opt/homebrew/opt/llvm/bin/llvm-config"
uv pip install numba

# 3. 安装 FunASR
uv pip install funasr modelscope
```

#### 对于 Intel 芯片：

```bash
# 1. 安装 PyTorch
uv pip install torch torchaudio

# 2. 安装 FunASR（Intel 通常没有编译问题）
uv pip install funasr modelscope
```

### 步骤 4：验证安装

```bash
python -c "
import funasr
from funasr import AutoModel
print('✅ FunASR 安装成功！')
print(f'版本: {funasr.__version__}')
"
```

### 步骤 5：测试模型加载

```bash
python -c "
from funasr import AutoModel
print('正在加载模型（首次下载约 220MB）...')
model = AutoModel(
    model='damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch',
    device='cpu'  # macOS 暂时使用 CPU，MPS 支持正在完善
)
print('✅ 模型加载成功！')
"
```

## 性能预期

### Apple Silicon (M1/M2/M3)

| 模型 | 推理速度 | 内存占用 |
|------|---------|---------|
| paraformer-zh (220MB) | 0.3x 实时 | ~800MB |
| paraformer-zh-plus (500MB) | 0.5x 实时 | ~1.5GB |

**说明：**
- 10 秒音频约需 3-5 秒处理
- Apple Silicon 的 Neural Engine 目前 FunASR 尚未充分利用
- 使用 CPU 推理，但性能已经很好

### Intel Mac

| 模型 | 推理速度 | 内存占用 |
|------|---------|---------|
| paraformer-zh (220MB) | 0.5x 实时 | ~800MB |

**说明：**
- 10 秒音频约需 5-8 秒处理
- 建议关闭其他占用 CPU 的应用

## 常见问题

### 问题 1：`illegal hardware instruction` 错误

**原因：** 可能是 numba 或 PyTorch 架构不匹配

**解决：**
```bash
# 重新安装 PyTorch（确保是 ARM64 版本）
uv pip uninstall torch torchaudio
uv pip install torch torchaudio

# 验证架构
python -c "import torch; print(torch.__version__); print('MPS available:', torch.backends.mps.is_available())"
```

### 问题 2：`RuntimeError: Failed to initailize Numba` 

**解决：**
```bash
# 安装 llvm
brew install llvm libomp

# 设置环境变量
export PATH="/opt/homebrew/opt/llvm/bin:$PATH"
export LDFLAGS="-L/opt/homebrew/opt/llvm/lib"
export CPPFLAGS="-I/opt/homebrew/opt/llvm/include"

# 重新安装 numba
uv pip install --force-reinstall numba
```

### 问题 3：模型下载缓慢或失败

**解决：**
```bash
# 使用国内镜像
export MODELSCOPE_CACHE=~/.cache/modelscope
export MODELSCOPE_ENDPOINT=https://www.modelscope.cn

# 手动下载模型
python -c "
from modelscope import snapshot_download
snapshot_download('damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch')
"
```

### 问题 4：`MemoryError` 或系统变慢

**原因：** 内存不足

**解决：**
```bash
# 使用更小的模型
# 编辑 backend/.env
FUNASR_MODEL=paraformer-zh  # 不要使用 zh-plus

# 关闭其他应用释放内存
# 或者重启电脑后重试
```

## 优化建议

### 1. 使用 conda 管理依赖（推荐）

```bash
# 安装 miniconda
brew install miniconda

# 创建环境
conda create -n evoloop python=3.11
conda activate evoloop

# 安装依赖
conda install -c conda-forge numba llvmlite
pip install torch torchaudio funasr modelscope
```

### 2. 预加载模型

在应用启动时预加载模型，避免第一次请求时加载：

```python
# backend/app/main.py 中的 startup 事件
@app.on_event("startup")
async def preload_funasr():
    from app.core.voice.stt.factory import STTFactory
    try:
        STTFactory.preload_funasr("paraformer-zh")
        logger.info("✅ FunASR 模型预加载完成")
    except Exception as e:
        logger.warning(f"⚠️ FunASR 预加载失败: {e}")
```

### 3. 监控资源使用

```bash
# 在另一个终端监控资源
# 内存和 CPU
htop

# 或者使用活动监视器
open -a "Activity Monitor"
```

## 验证安装完整性

运行以下脚本检查安装：

```bash
# 保存为 check_funasr.sh
cd evoloop/backend
source .venv/bin/activate

echo "🔍 检查 FunASR 安装..."

python -c "
import sys

checks = [
    ('PyTorch', 'torch'),
    ('TorchAudio', 'torchaudio'),
    ('FunASR', 'funasr'),
    ('ModelScope', 'modelscope'),
]

all_ok = True
for name, module in checks:
    try:
        __import__(module)
        print(f'✅ {name}')
    except ImportError:
        print(f'❌ {name} - 未安装')
        all_ok = False

if all_ok:
    print('\n🎉 所有依赖已安装！')
    print('\n测试模型加载:')
    try:
        from funasr import AutoModel
        print('正在加载模型...')
        model = AutoModel(
            model='damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch',
            device='cpu'
        )
        print('✅ 模型加载成功！')
    except Exception as e:
        print(f'❌ 模型加载失败: {e}')
else:
    print('\n⚠️ 请安装缺失的依赖')
    sys.exit(1)
"
```

## 总结

| 芯片 | 支持状态 | 性能 | 注意事项 |
|------|---------|------|---------|
| Apple Silicon (M1/M2/M3) | ✅ 完全支持 | 优秀 | 可能需要手动安装 numba |
| Intel | ✅ 完全支持 | 良好 | 无特殊问题 |

**推荐配置：**
- macOS 13+ (Ventura)
- 8GB+ 内存
- 使用 conda 管理依赖

**安装时间：**
- 首次安装：5-15 分钟（取决于网络）
- 模型下载：2-5 分钟（220MB）
