# Apple Silicon (M1/M2/M3/M4) 安装指南

本文档专门针对 Apple Silicon Mac 用户的安装和打包注意事项。

## 🔍 环境检测

首先确认你的 Python 环境：

```bash
# 检查 Python 架构
python3 -c "import platform; print(f'Python: {platform.python_version()}'); print(f'Machine: {platform.machine()}')"
```

**期望输出：**
```
Python: 3.11.x
Machine: arm64  ✅ 正确（原生 Apple Silicon）
```

**如果显示：**
```
Machine: x86_64  ⚠️  Rosetta 模式（可能有兼容性问题）
```

## 🚀 快速开始

### 1. 模型下载（打包用）

**无需安装 FunASR 依赖，仅下载模型：**

```bash
# 下载默认模型
./scripts/download_models.sh --skip-funasr-check

# 下载所有模型
./scripts/download_models.sh --all --skip-funasr-check

# 下载指定模型
./scripts/download_models.sh --models paraformer-zh,paraformer-zh-plus --skip-funasr-check
```

### 2. 完整打包（包含模型）

```bash
# 自动下载并打包模型
./scripts/build_with_models.sh

# 或者分开执行
./scripts/download_models.sh --skip-funasr-check
./scripts/build_all.sh --with-models
```

## 🔧 开发环境（可选）

如果你需要在本地开发环境运行 FunASR（不是打包，而是实际使用 STT 功能）：

### 方案一：使用 Conda（推荐）

```bash
# 安装 conda（如果还没有）
brew install miniconda

# 创建环境
conda create -n evoloop python=3.11 -y
conda activate evoloop

# 安装 Apple Silicon 优化的依赖
conda install -c conda-forge numba llvmlite -y

# 安装其他依赖
cd backend
uv pip install torch torchaudio funasr modelscope
```

### 方案二：使用 Rosetta Python

```bash
# 安装 x86_64 版本的 Homebrew
arch -x86_64 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 使用 Rosetta Python
arch -x86_64 /usr/local/bin/brew install python@3.11
arch -x86_64 /usr/local/opt/python@3.11/bin/python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install funasr modelscope torch torchaudio
```

### 方案三：使用 Docker

```bash
# 使用 FunASR 官方镜像
docker pull registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-cpu-0.4.5

# 运行服务
docker run -p 10095:10095 -it --rm \
  registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-cpu-0.4.5
```

## ⚠️ 常见问题

### 1. llvmlite 编译失败

**错误信息：**
```
Failed to build `llvmlite==0.46.0`
TypeError: spawn() got an unexpected keyword argument 'dry_run'
```

**原因：**
- Apple Silicon 上没有预编译的 llvmlite wheel
- 从源码编译需要 LLVM 开发库

**解决方案：**
- **打包场景**：使用 `--skip-funasr-check` 跳过 FunASR 安装，只下载模型
- **开发场景**：使用 Conda 安装（见上文方案一）

### 2. "illegal hardware instruction"

**原因：**
- 使用了为 x86_64 编译的 Python 包

**解决方案：**
```bash
# 确保使用 ARM64 Python
file $(which python3)
# 应该显示: Mach-O 64-bit executable arm64

# 如果不是，重新安装 Python
brew reinstall python@3.11
```

### 3. 模型下载后的路径

```
~/.evoloop/models/
└── hub/
    └── damo/
        └── speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch/
            ├── model.pt
            ├── configuration.json
            └── ...
```

## 📦 打包模型 vs 运行时下载

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| **打包模型** | 将模型包含在 DMG 中 | **推荐**，用户开箱即用，无需关心 FunASR |
| **运行时下载** | 首次使用时自动下载 | 减小安装包体积，适合网络良好的环境 |

### 为什么打包时不需要 FunASR？

- 模型下载只需要 `modelscope` 库（轻量级，纯 Python）
- FunASR 只在**运行时使用模型**才需要
- 打包时只需将模型文件放入 resources，运行时由 backend 加载
- 最终用户的机器上，FunASR 会在安装依赖时安装（有 wheel 或用户自行解决）

## ✅ 验证安装

```bash
# 检查模型是否下载成功
ls -la ~/.evoloop/models/hub/damo/

# 检查是否可以导入 modelscope
python3 -c "from modelscope import snapshot_download; print('✅ OK')"

# 如果已安装 FunASR，验证模型加载
python3 -c "
from funasr import AutoModel
model = AutoModel(model='damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch')
print('✅ FunASR model loaded')
"
```

## 🆘 获取帮助

如果仍有问题：

1. 检查文档：[VOICE_SETUP.md](VOICE_SETUP.md)
2. 查看 FunASR 官方文档：https://github.com/alibaba-damo-academy/FunASR
3. Apple Silicon 特定问题：https://github.com/numba/llvmlite/issues
