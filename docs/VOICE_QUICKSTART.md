# EvoLoop 语音功能快速开始

## 🎯 一分钟快速配置

### 1. TTS（语音合成）- 已就绪 ✅

TTS 使用 Edge-TTS，**无需任何配置**，安装即用！

```bash
# 测试 TTS
curl -X POST http://localhost:8000/api/v1/audio/tts-stream \
  -F "text=你好，我是智能语音助手晓晓" \
  -F "voice_id=zh-CN-XiaoxiaoNeural" \
  --output test.mp3 && afplay test.mp3
```

**可用声音：**
- `zh-CN-XiaoxiaoNeural` - 晓晓（女声，推荐）
- `zh-CN-YunxiNeural` - 云希（男声，推荐）

---

### 2. STT（语音识别）- 需安装 ⚙️

STT 使用 FunASR，需要安装依赖。

#### 系统要求
- **macOS**: 支持 Intel 和 Apple Silicon (M1/M2/M3)
- **Linux**: x86_64 架构
- **内存**: 4GB+（推荐 8GB）

#### 步骤 1：安装依赖

**方式 A：使用安装脚本（推荐）**
```bash
cd evoloop/backend
source .venv/bin/activate
./scripts/install_funasr.sh
```

**方式 B：Conda 安装（macOS/Linux 推荐，无编译问题）**
```bash
cd evoloop/backend
source .venv/bin/activate
conda install -c conda-forge numba llvmlite -y
uv pip install funasr modelscope torch torchaudio
```

**macOS 用户注意：**
- Apple Silicon (M1/M2/M3) 芯片完全支持
- 如果遇到编译错误，先安装 llvm：`brew install llvm libomp`
- 详见 [FUNASR_MACOS.md](FUNASR_MACOS.md)

#### 步骤 2：验证安装
```bash
# 检查 STT 状态
curl http://localhost:8000/api/v1/audio/stt/providers

# 预期输出：funasr: available=true
```

#### 步骤 3：测试识别
```bash
# 使用录音文件测试
curl -X POST http://localhost:8000/api/v1/audio/transcribe \
  -F "file=@test.wav" \
  -F "language=zh"
```

---

## 📋 配置选项

编辑 `backend/.env`：

```env
# TTS 配置
TTS_DEFAULT_VOICE=zh-CN-XiaoxiaoNeural
TTS_DEFAULT_SPEED=1.0

# STT 配置
FUNASR_MODEL=paraformer-zh      # paraformer-zh | paraformer-zh-plus
FUNASR_DEVICE=cpu               # cpu | cuda
```

---

## 🔧 故障排除

### FunASR 安装失败？

使用 OpenAI Whisper 作为备选：
```env
OPENAI_API_KEY=sk-your-api-key
```

系统会自动回退到 Whisper。

### 检查服务状态
```bash
# TTS 状态
curl http://localhost:8000/api/v1/audio/voices | jq '.voices | length'
# 预期：21

# STT 状态  
curl http://localhost:8000/api/v1/audio/stt/providers | jq '.providers[0].available'
# 预期：true
```

---

## 🚀 前端使用

```typescript
// 语音识别
const { data } = await AudioService.transcribeAudio({
  formData: {
    file: audioBlob,
    language: 'zh'
  }
})
console.log(data.text) // "你好，这是语音识别结果"

// 语音合成
const response = await fetch('/api/v1/audio/tts-stream', {
  method: 'POST',
  body: formData // text, voice_id, speed
})
const audioBlob = await response.blob()
const audio = new Audio(URL.createObjectURL(audioBlob))
audio.play()
```

---

## 📊 功能对比

| 功能 | Edge-TTS (TTS) | FunASR (STT) | Whisper (STT备选) |
|------|----------------|--------------|-------------------|
| 费用 | 免费 | 免费 | 收费 |
| 网络 | 需联网 | 离线 | 需联网 |
| 中文 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 配置 | 零配置 | 需安装 | 需 API Key |
| 速度 | 快 | 中等 | 依赖网络 |

---

**🎉 完成！** TTS 已就绪，STT 安装 FunASR 后即可使用。
