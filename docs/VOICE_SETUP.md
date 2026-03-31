# EvoLoop 语音功能配置指南

本文档介绍如何配置和使用 EvoLoop 的语音功能（TTS 和 STT）。

## 功能概览

| 功能 | 提供商 | 特点 | 是否需要配置 |
|------|--------|------|-------------|
| **TTS (语音合成)** | Edge-TTS | 免费，21种声音，中文优秀 | ❌ 零配置 |
| **STT (语音识别)** | FunASR | 本地运行，中文优化，隐私安全 | ⚠️ 需要安装依赖 |
| **STT (备选)** | Whisper | 云端，多语言 | ⚠️ 需要 OpenAI Key |

---

## 一、TTS 配置（Edge-TTS）

### 1.1 特点

- ✅ **完全免费** - 使用微软 Edge 浏览器同款服务
- ✅ **零配置** - 安装即用，无需 API Key
- ✅ **中文优秀** - 晓晓、云希等声音非常自然
- ✅ **多语言** - 支持中/英/日/韩/粤语/台湾话

### 1.2 可用声音

#### 中文（普通话）
| 声音 ID | 名称 | 性别 | 特点 |
|---------|------|------|------|
| `zh-CN-XiaoxiaoNeural` | 晓晓 | 女声 | **推荐**，温柔自然 |
| `zh-CN-XiaoyiNeural` | 小艺 | 女声 | 活泼年轻 |
| `zh-CN-YunxiNeural` | 云希 | 男声 | **推荐**，年轻阳光 |
| `zh-CN-YunjianNeural` | 云健 | 男声 | 新闻播报风格 |
| `zh-CN-YunyangNeural` | 云扬 | 男声 | 沉稳磁性 |

#### 方言
| 声音 ID | 名称 | 语言 |
|---------|------|------|
| `zh-TW-HsiaoChenNeural` | 晓晨 | 台湾普通话 |
| `zh-HK-HiuMaanNeural` | 晓曼 | 香港粤语 |

### 1.3 配置选项

编辑 `backend/.env` 文件：

```env
# TTS 默认声音
TTS_DEFAULT_VOICE=zh-CN-XiaoxiaoNeural

# TTS 默认语速 (0.5 - 2.0)
TTS_DEFAULT_SPEED=1.0
```

### 1.4 使用 API

#### 获取声音列表
```bash
curl http://localhost:8000/api/v1/audio/voices
```

#### 合成语音
```bash
# 流式合成（推荐，直接播放）
curl -X POST http://localhost:8000/api/v1/audio/tts-stream \
  -F "text=你好，我是智能语音助手" \
  -F "voice_id=zh-CN-XiaoxiaoNeural" \
  -F "speed=1.0" \
  --output output.mp3

# 非流式合成（返回 URL）
curl -X POST http://localhost:8000/api/v1/audio/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，我是智能语音助手",
    "voice_id": "zh-CN-YunxiNeural",
    "speed": 1.0
  }'
```

---

## 二、STT 配置（FunASR）

### 2.1 特点

- ✅ **完全离线** - 本地运行，保护隐私
- ✅ **中文优化** - 识别率比 Whisper 高 15-20%
- ✅ **中文标点** - 自动添加标点符号
- ✅ **免费** - 无需 API Key
- ⚠️ **需要安装** - 首次使用需下载模型

### 2.2 安装 FunASR

由于依赖较多，提供几种安装方式：

#### 方式一：使用 Conda（推荐，避免编译问题）

```bash
cd evoloop/backend

# 激活虚拟环境
source .venv/bin/activate

# 使用 conda 安装编译依赖
conda install -c conda-forge numba llvmlite -y

# 安装 FunASR
uv pip install funasr modelscope torch torchaudio
```

#### 方式二：使用 pip 安装（如果遇到编译错误）

```bash
cd evoloop/backend
source .venv/bin/activate

# 先安装 numpy 和 torch
uv pip install numpy torch torchaudio --force-reinstall

# 安装 FunASR（可能耗时较长，需要编译）
uv pip install funasr modelscope
```

#### 方式三：Docker 安装（最稳定）

```bash
# 拉取 FunASR 官方镜像
docker pull registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-cpu-0.4.5

# 运行服务
docker run -p 10095:10095 -it --rm \
  registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-cpu-0.4.5
```

### 2.3 模型配置

编辑 `backend/.env` 文件：

```env
# FunASR 模型选择
# 可选: paraformer-zh | paraformer-zh-plus | paraformer-zh-streaming
FUNASR_MODEL=paraformer-zh

# 设备选择 (cpu | cuda)
FUNASR_DEVICE=cpu
```

**模型说明：**

| 模型 | 大小 | 特点 | 适用场景 |
|------|------|------|----------|
| `paraformer-zh` | ~220MB | 基础模型，通用场景 | **推荐**，日常使用 |
| `paraformer-zh-plus` | ~500MB | 增强模型，带 VAD 和标点 | 高精度需求 |
| `paraformer-zh-streaming` | ~220MB | 流式模型，实时识别 | 实时对话 |


### 2.4 首次使用

首次使用时会**自动下载模型**到 `~/.evoloop/models/`（可通过 `MODELS_DIR` 环境变量配置），下载时间取决于网络：

- paraformer-zh: 约 2-5 分钟
- paraformer-zh-plus: 约 5-10 分钟

下载完成后会缓存，下次使用无需重新下载。

**模型存储路径配置：**
```env
# 在 .env 文件中配置（可选，默认为 ~/.evoloop/models）
MODELS_DIR=~/.evoloop/models
```

### 2.5 打包时预下载模型（可选）

为了减少用户首次使用的等待时间，可以在打包时将模型一并打包：

#### 方式一：使用便捷脚本（推荐）
```bash
# 打包默认模型 (paraformer-zh, ~220MB)
./scripts/build_with_models.sh

# 打包所有模型 (~1.2GB)
./scripts/build_with_models.sh --all

# 打包指定模型
./scripts/build_with_models.sh --models paraformer-zh,paraformer-zh-plus
```

#### 方式二：使用主构建脚本
```bash
# 仅使用已下载的模型（不重新下载）
./scripts/build_all.sh --with-models

# 下载模型并打包
./scripts/build_all.sh --download-models --with-models

# 下载指定模型并打包
./scripts/build_all.sh --download-models paraformer-zh,paraformer-zh-plus --with-models
```

#### 方式三：手动下载后打包
```bash
# 1. 先下载模型
./scripts/download_models.sh --models paraformer-zh,paraformer-zh-plus

# 2. 打包时包含模型
./scripts/build_all.sh --with-models
```

**打包 vs 运行时下载对比：**

| 方式 | DMG 大小 | 首次使用体验 | 适用场景 |
|------|----------|--------------|----------|
| 不打包模型 | ~150MB | 需等待下载 2-5 分钟 | 网络良好的环境 |
| 打包基础模型 | ~370MB | 开箱即用 | 推荐，平衡体验 |
| 打包所有模型 | ~1.4GB | 开箱即用 | 离线环境或完整体验 |

### 2.6 模型打包技术说明

当使用 `--with-models` 打包时：

1. 模型从 `~/.evoloop/models` 复制到 `frontend/src-tauri/models/`
2. Tauri 配置临时修改，将 `models` 目录包含在 bundle 中
3. 打包完成后，模型随 App 一起分发
4. 用户首次启动时，模型自动从 App Bundle 复制到 `~/.evoloop/models/`
5. 复制完成后，即可离线使用 STT 功能

这种设计的好处：
- ✅ 模型只会在首次启动时复制一次
- ✅ 用户可以更新模型而不影响 App Bundle
- ✅ 支持多用户，每个用户有自己的模型副本

### 2.5 使用 API

#### 查看 STT 提供商状态
```bash
curl http://localhost:8000/api/v1/audio/stt/providers
```

#### 语音识别
```bash
# 上传音频文件进行识别
curl -X POST http://localhost:8000/api/v1/audio/transcribe \
  -F "file=@/path/to/audio.wav" \
  -F "language=zh" \
  -F "prompt=专业术语1,专业术语2"

# 返回示例
{
  "text": "你好，这是语音识别测试。",
  "duration": 3.5,
  "language": "zh-CN",
  "confidence": 0.95
}
```

#### 支持的音频格式
- `webm` - Web 录音默认格式
- `wav` - 无损格式，识别效果最好
- `mp3` - 压缩格式
- `m4a` - iPhone 录音格式
- `ogg`, `opus` - 其他格式

---

## 三、STT 备选配置（Whisper）

如果 FunASR 安装失败，可以使用 OpenAI Whisper 作为备选。

### 3.1 配置 OpenAI Key

编辑 `backend/.env`：

```env
OPENAI_API_KEY=sk-your-real-api-key
```

### 3.2 使用

无需额外配置，当 FunASR 不可用时自动回退到 Whisper。

---

## 四、前端使用

### 4.1 使用 SDK

```typescript
import { AudioService } from '@/client'

// 获取声音列表
const { voices } = await AudioService.listVoices()

// 获取 STT 提供商
const { providers } = await AudioService.listSttProviders()

// 语音识别
const result = await AudioService.transcribeAudio({
  formData: {
    file: audioBlob,
    language: 'zh',
    prompt: '专业术语'
  }
})
console.log(result.text) // 识别文本
```

### 4.2 使用 React Hook

```typescript
import { useTranscription } from '@/hooks/useTranscription'

function VoiceRecorder() {
  const { transcribe, isTranscribing, error } = useTranscription()

  const handleRecord = async (audioBlob: Blob) => {
    const result = await transcribe(audioBlob, {
      language: 'zh',
      prompt: '专业术语'
    })
    if (result) {
      console.log('识别结果:', result.text)
    }
  }
}
```

---

## 五、故障排除

### 5.1 Edge-TTS 连接超时

**现象：** `Connection timeout to host speech.platform.bing.com`

**原因：** 网络无法连接微软服务

**解决：**
- 检查网络连接
- 如果使用代理，配置环境变量：`export HTTPS_PROXY=http://proxy:port`
- 或使用 VPN

### 5.2 macOS 安装问题

**现象：** `illegal hardware instruction` 或 numba 编译失败

**原因：** Apple Silicon 架构兼容性问题

**解决：**
```bash
# 1. 确保使用 ARM64 Python
file $(which python)
# 预期：Mach-O 64-bit executable arm64

# 2. 使用 conda 安装（避免编译）
conda install -c conda-forge numba llvmlite

# 3. 或者安装 llvm 后编译
brew install llvm libomp
export LLVM_CONFIG=/opt/homebrew/opt/llvm/bin/llvm-config
uv pip install numba
```

详见 [FUNASR_MACOS.md](FUNASR_MACOS.md)

### 5.3 FunASR 模型下载失败

**现象：** 首次使用时报下载错误

**解决：**
```bash
# 查看模型存储路径
cd ~/.evoloop/models/hub/

# 手动设置模型镜像（国内加速）
export MODELSCOPE_CACHE=~/.evoloop/models
export MODELSCOPE_ENDPOINT=https://www.modelscope.cn

# 或者手动下载模型
python -c "from modelscope import snapshot_download; snapshot_download('damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch', cache_dir='~/.evoloop/models')"
```

### 5.4 FunASR 内存不足

**现象：** 加载模型时 OOM

**解决：**
- 使用更小的模型：`paraformer-zh` 代替 `paraformer-zh-plus`
- 确保内存大于 4GB
- 关闭其他占用内存的应用

### 5.2 FunASR 模型下载失败

**现象：** 首次使用时报下载错误

**解决：**
```bash
# 手动设置模型镜像（国内加速）
export MODELSCOPE_CACHE=~/.evoloop/models
export MODELSCOPE_ENDPOINT=https://www.modelscope.cn

# 或者手动下载模型
python -c "from modelscope import snapshot_download; snapshot_download('damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch', cache_dir='~/.evoloop/models')"
```

### 5.3 FunASR 内存不足

**现象：** 加载模型时 OOM

**解决：**
- 使用更小的模型：`paraformer-zh` 代替 `paraformer-zh-plus`
- 确保内存大于 4GB
- 关闭其他占用内存的应用

### 5.4 检查服务状态

```bash
# 检查 TTS 状态
curl http://localhost:8000/api/v1/audio/voices

# 检查 STT 状态
curl http://localhost:8000/api/v1/audio/stt/providers

# 测试 TTS
curl -X POST http://localhost:8000/api/v1/audio/tts-stream \
  -F "text=测试" -F "voice_id=zh-CN-XiaoxiaoNeural" \
  --output test.mp3 && afplay test.mp3
```

---

## 六、性能优化

### 6.1 TTS 优化
- 使用流式接口 `/tts-stream` 减少等待时间
- 缓存常用音频，避免重复合成

### 6.2 STT 优化
- 使用 `paraformer-zh` 模型，平衡速度和精度
- 使用 GPU 加速（如果可用）
- 预处理音频：降噪、归一化音量

### 6.3 预加载模型

在应用启动时预加载 FunASR 模型：

```python
# backend/app/main.py 启动时
from app.core.voice.stt.factory import STTFactory

@app.on_event("startup")
async def preload_models():
    # 预加载 FunASR
    STTFactory.preload_funasr("paraformer-zh")
```

---

## 七、总结

| 功能 | 推荐配置 | 备注 |
|------|----------|------|
| TTS | Edge-TTS 默认 | 零配置，即装即用 |
| STT | FunASR paraformer-zh | 安装后中文识别最佳 |
| STT 备选 | Whisper | 需要 OpenAI Key |

**快速开始：**
1. TTS 无需配置，立即可用
2. STT 安装 FunASR：`conda install numba && uv pip install funasr`
3. 测试：`curl http://localhost:8000/api/v1/audio/stt/providers`
