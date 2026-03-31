# FunASR macOS 快速安装

针对 macOS 用户的简化安装指南。

## 1. 检测你的 Mac

```bash
# 查看芯片类型
uname -m
# arm64 = Apple Silicon (M1/M2/M3)
# x86_64 = Intel
```

## 2. 一键安装

```bash
cd evoloop/backend
source .venv/bin/activate

# 运行安装脚本
./scripts/install_funasr.sh
```

## 3. 如果脚本失败

### Apple Silicon (M1/M2/M3) 手动安装

```bash
# 1. 激活环境
source .venv/bin/activate

# 2. 安装 conda 的 numba（避免编译）
conda install -c conda-forge numba llvmlite -y

# 3. 安装 PyTorch（Apple Silicon 版本）
uv pip install torch torchaudio

# 4. 安装 FunASR
uv pip install funasr modelscope

# 5. 验证
python -c "from funasr import AutoModel; print('✅ OK')"
```

### Intel Mac 手动安装

```bash
source .venv/bin/activate
uv pip install torch torchaudio funasr modelscope
```

## 4. 验证安装

```bash
# 检查状态
curl http://localhost:8000/api/v1/audio/stt/providers

# 预期输出包含："name": "funasr", "available": true
```

## 5. 常见问题

### Q: 遇到 `illegal hardware instruction`
**A:** Python 架构不对，重新安装 ARM64 Python：
```bash
brew install python@3.11
```

### Q: numba 编译卡住
**A:** 使用 conda 版本：
```bash
conda install numba
```

### Q: 内存不足（MemoryError）
**A:** 使用小模型，编辑 `.env`：
```env
FUNASR_MODEL=paraformer-zh  # 不是 zh-plus
```

## 6. 测试

```bash
# 测试识别
curl -X POST http://localhost:8000/api/v1/audio/transcribe \
  -F "file@test.wav" \
  -F "language=zh"
```

## 完整文档

- [FUNASR_MACOS.md](FUNASR_MACOS.md) - 详细 macOS 指南
- [VOICE_SETUP.md](VOICE_SETUP.md) - 完整配置文档
