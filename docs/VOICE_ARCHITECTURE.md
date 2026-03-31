# EvoLoop 语音系统架构与 Agent 配合流程

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户层 (User Layer)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐          │
│  │   语音    │     │   文字    │     │   语音    │     │   语音    │          │
│  │  输入    │────▶│  转换    │────▶│  对话    │────▶│  输出    │          │
│  │ (说话)   │     │ (STT)   │     │ (Agent)  │     │ (TTS)   │          │
│  └──────────┘     └──────────┘     └──────────┘     └──────────┘          │
│        │                                               │                    │
│        │         ┌──────────┐                         │                    │
│        └────────▶│  快捷键   │                         │                    │
│                  │(双击Ctrl)│                         │                    │
│                  └──────────┘                         │                    │
│                                                       │                    │
└───────────────────────────────────────────────────────┼────────────────────┘
                                                        │
┌───────────────────────────────────────────────────────┼────────────────────┐
│                      前端层 (Frontend Layer)           │                    │
├───────────────────────────────────────────────────────┼────────────────────┤
│                                                       │                    │
│  ┌─────────────────────────────────────────────────┐  │                    │
│  │               ChatInputArea                      │  │                    │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │  │                    │
│  │  │ 语音按钮  │  │ 录音组件  │  │  文字输入框    │  │  │                    │
│  │  │ (切换)   │  │(按住录音)│  │              │  │  │                    │
│  │  └──────────┘  └──────────┘  └───────────────┘  │  │                    │
│  └─────────────────────────────────────────────────┘  │                    │
│                        │                              │                    │
│  ┌─────────────────────┼─────────────────────────┐   │                    │
│  │                     ▼                         │   │                    │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │   │                    │
│  │  │useVoice  │  │useTrans- │  │   useTTS   │  │   │                    │
│  │  │Recorder │  │ cription │  │            │  │   │                    │
│  │  │(录音)   │──▶│ (STT)   │  │ (语音合成) │◀─┘   │                    │
│  │  └──────────┘  └──────────┘  └────────────┘      │                    │
│  │         │              │              │          │                    │
│  │         ▼              ▼              ▼          │                    │
│  │  ┌──────────────────────────────────────────┐   │                    │
│  │  │          AudioService (SDK)              │   │                    │
│  │  │  /api/v1/audio/transcribe (STT)         │   │                    │
│  │  │  /api/v1/audio/tts-stream (TTS)         │   │                    │
│  │  └──────────────────────────────────────────┘   │                    │
│  └─────────────────────────────────────────────────┘                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      后端层 (Backend Layer)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                     Audio API Routes                              │ │
│  │  ┌──────────────────────────────────────────────────────────┐    │ │
│  │  │  /api/v1/audio/transcribe  ───────┐                      │    │ │
│  │  │  /api/v1/audio/tts-stream ────────┼───▶  Voice Module   │    │ │
│  │  │  /api/v1/audio/voices     ────────┘                      │    │ │
│  │  └──────────────────────────────────────────────────────────┘    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                               │                                         │
│                               ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                       Voice Module                                │ │
│  │  ┌────────────────────────┐    ┌────────────────────────┐        │ │
│  │  │      TTS Factory       │    │      STT Factory       │        │ │
│  │  │  ┌──────────────────┐  │    │  ┌──────────────────┐  │        │ │
│  │  │  │  Edge-TTS        │  │    │  │  FunASR          │  │        │ │
│  │  │  │  (语音合成)      │  │    │  │  (语音识别)      │  │        │ │
│  │  │  │  • 晓晓          │  │    │  │  • 本地模型      │  │        │ │
│  │  │  │  • 云希          │  │    │  │  • 中文优化      │  │        │ │
│  │  │  │  • 21种声音      │  │    │  │  • 离线可用      │  │        │ │
│  │  │  └──────────────────┘  │    │  └──────────────────┘  │        │ │
│  │  │         │              │    │         │              │        │ │
│  │  │         ▼              │    │         ▼              │        │ │
│  │  │  ┌──────────────────┐  │    │  ┌──────────────────┐  │        │ │
│  │  │  │  OpenAI TTS      │  │    │  │  Whisper         │  │        │ │
│  │  │  │  (备选)          │  │    │  │  (云端备选)      │  │        │ │
│  │  │  │  (未配置)        │  │    │  │  (需 API Key)    │  │        │ │
│  │  │  └──────────────────┘  │    │  └──────────────────┘  │        │ │
│  │  └────────────────────────┘    └────────────────────────┘        │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Agent 层 (Agent Layer)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                      Agent Graph                                  │ │
│  │                                                                   │ │
│  │   用户 ──▶ InputNode ──▶ Supervisor ──▶ Worker ──▶ Output       │ │
│  │              (输入)      (路由)       (处理)     (输出)          │ │
│  │                                                                   │ │
│  │   语音消息 ──▶ attachments: [{type: 'audio'}] ──▶ reference      │ │
│  │                 │                                               │ │
│  │                 ▼                                               │ │
│  │   ┌─────────────────────────┐                                   │ │
│  │   │  ReferenceService       │                                   │ │
│  │   │  - 调用 STT 识别语音    │                                   │ │
│  │   │  - 获取文本内容         │                                   │ │
│  │   │  - 添加到上下文         │                                   │ │
│  │   └─────────────────────────┘                                   │ │
│  │                                                                   │ │
│  │   输出响应 ──▶ 如 autoSpeak=true ──▶ TTS 合成语音              │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 核心工作流程

### 流程 1：语音输入 → Agent 处理

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│ 用户    │    │ 前端      │    │ 后端      │    │ Voice    │    │ Agent   │
│ 说话    │───▶│ 录音     │───▶│ STT API  │───▶│ FunASR   │───▶│ 处理    │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └─────────┘
     │                                               │                │
     │ 1. 按住录音按钮                                │                │
     │ 2. 录制音频 (Web Audio API)                   │                │
     │ 3. 松开发送                                    │                │
     │                                               │                │
     │          4. POST /api/v1/audio/transcribe     │                │
     │             (FormData: audio file)            │                │
     │                                               │                │
     │                      5. 调用 FunASR 识别      │                │
     │                         音频 → 文字          │                │
     │                                               │                │
     │                      6. 返回识别文本          │                │
     │                                               │                │
     │          7. 显示识别文本在输入框              │                │
     │                                               │                │
     │          8. 用户确认发送                      │                │
     │             或自动发送                        │                │
     │                                               │                │
     │──────────────────────────────────────────────▶│                │
     │          9. POST /api/v1/chat                 │                │
     │             message + attachments             │                │
     │                                               │                │
     │                                               │       10. Agent 处理
     │                                               │          生成回复
     │                                               │                │
```

### 流程 2：Agent 输出 → 语音播报

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│ 用户    │    │ 前端      │    │ 后端      │    │ Voice    │    │ Agent   │
│ 听到    │◀───│ 播放     │◀───│ TTS API  │◀───│ Edge-TTS │◀───│ 回复    │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └─────────┘
                                      │                              │
                                      │ 1. Agent 生成回复             │
                                      │                              │
                                      │ 2. 检查 autoSpeak 设置        │
                                      │    (localStorage)             │
                                      │                              │
                                      │ 3. 如开启，请求 TTS           │
                                      │                              │
                                      │ 4. POST /api/v1/audio/tts-stream
                                      │    text: 回复内容             │
                                      │    voice_id: 晓晓/云希        │
                                      │                              │
                                      │ 5. Edge-TTS 合成              │
                                      │    文字 → 音频流              │
                                      │                              │
                                      │ 6. 返回 audio/mpeg 流         │
                                      │                              │
                              7. 播放音频 (Audio API)                 │
                                      │                              │
                              8. 用户听到语音回复                     │
```

### 流程 3：快捷键触发语音对话

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│ 用户    │    │ Tauri    │    │ 前端      │    │ 后端      │    │ Agent   │
│ 双击Ctrl│───▶│ 全局    │───▶│ 开始    │───▶│ (等待  │───▶│ 处理    │
│         │    │ 快捷键  │    │ 录音    │    │ 音频)  │    │        │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └─────────┘
     │                                               │
     │ 1. 双击 Ctrl (全局快捷键)                     │
     │    - rdev 监听系统键盘                       │
     │    - 发送事件到前端                          │
     │                                               │
     │ 2. 前端显示录音界面                           │
     │    - 波形可视化                              │
     │    - 提示"正在听..."                         │
     │                                               │
     │ 3. 用户说话...                               │
     │                                               │
     │ 4. 松开 Ctrl 停止录音                        │
     │                                               │
     │ 5. 自动发送给 STT 识别                       │
     │                                               │
     │ 6. 自动发送给 Agent 处理                     │
     │                                               │
     │ 7. Agent 回复 + TTS 播报                     │
```

## 关键组件交互

### 1. ChatInputArea ↔ Voice Module

```typescript
// ChatInputArea.tsx
const ChatInputArea = () => {
  const [isVoiceMode, setIsVoiceMode] = useState(false)
  const { transcribe } = useTranscription()
  
  // 语音模式切换
  const toggleVoiceMode = () => setIsVoiceMode(!isVoiceMode)
  
  // 录音完成回调
  const handleRecordingComplete = async (audioBlob: Blob) => {
    // 1. 调用 STT 识别
    const result = await transcribe(audioBlob, { language: 'zh' })
    
    if (result) {
      // 2. 填入输入框
      setInputText(result.text)
      
      // 3. 可选：自动发送
      if (autoSend) {
        sendMessage(result.text)
      }
    }
  }
}
```

### 2. ChatMessageItem ↔ TTS

```typescript
// ChatMessageItem.tsx
const ChatMessageItem = ({ message }) => {
  const { autoSpeak } = useAutoSpeak()
  const { speak } = useTTS()
  
  // 新消息到达时
  useEffect(() => {
    if (autoSpeak && message.role === 'assistant') {
      // 自动朗读 AI 回复
      speak(message.content)
    }
  }, [message, autoSpeak])
  
  // 手动朗读按钮
  const handleSpeak = () => {
    speak(message.content)
  }
}
```

### 3. Agent Graph ↔ ReferenceService

```python
# reference_service.py
async def process_attachments(attachments):
    references = []
    
    for att in attachments:
        if att.type == "audio":
            # 1. 下载音频文件
            audio_data = await download_audio(att.id)
            
            # 2. 调用 FunASR 识别
            result = await stt_provider.transcribe(STTOptions(
                audio_data=audio_data,
                language=VoiceLocale.ZH_CN
            ))
            
            # 3. 添加识别文本到上下文
            references.append({
                "type": "audio_transcript",
                "text": result.text
            })
    
    return references
```

## 数据流

### 请求/响应数据格式

**STT 请求 (前端 → 后端)**
```typescript
// FormData
{
  file: Blob,           // 音频文件 (webm/wav/mp3)
  language: 'zh',       // 语言
  model: 'auto',        // 模型选择
  prompt: '',           // 热词提示 (可选)
  provider: 'auto'      // 'auto' | 'funasr' | 'whisper'
}
```

**STT 响应 (后端 → 前端)**
```json
{
  "text": "你好，这是测试",
  "duration": 3.5,
  "language": "zh-CN",
  "confidence": 0.95
}
```

**TTS 请求 (前端 → 后端)**
```typescript
// FormData
{
  text: "你好，我是晓晓",
  voice_id: "zh-CN-XiaoxiaoNeural",
  speed: 1.0,
  format: "mp3"
}
```

**TTS 响应 (后端 → 前端)**
```
Content-Type: audio/mpeg
Body: <audio stream>
```

## 配置项

### 用户可配置项

| 配置项 | 存储位置 | 默认值 | 说明 |
|--------|----------|--------|------|
| autoSpeak | localStorage | false | 自动朗读 AI 回复 |
| currentVoice | localStorage | 晓晓 | 默认 TTS 声音 |
| speechSpeed | localStorage | 1.0 | 语速 0.5-2.0 |
| voiceShortcut | localStorage | Ctrl | 语音快捷键 |

### 系统配置项

| 配置项 | 位置 | 默认值 | 说明 |
|--------|------|--------|------|
| FUNASR_MODEL | .env | paraformer-zh | STT 模型 |
| FUNASR_DEVICE | .env | cpu | cpu/cuda |
| TTS_DEFAULT_VOICE | .env | 晓晓 | 默认声音 |

## 错误处理与 Fallback

### STT Fallback 链

```
用户请求
    │
    ▼
FunASR (本地)
    │── 未安装 ──▶ Whisper (云端)
    │                │── 无 API Key ──▶ 错误提示
    │── 识别失败 ──▶ 重试 1 次
    │── 仍失败 ──▶ Whisper (云端)
```

### TTS Fallback 链

```
用户请求
    │
    ▼
Edge-TTS (免费)
    │── 网络错误 ──▶ 重试 1 次
    │── 仍失败 ──▶ 错误提示 (暂不支持其他 TTS)
```

## 性能优化

### 1. 模型预加载

```python
# 应用启动时预加载 FunASR
@app.on_event("startup")
async def preload_models():
    STTFactory.preload_funasr("paraformer-zh")
```

### 2. 音频缓存

```typescript
// 缓存常用 TTS 结果
const ttsCache = new Map()

const speak = async (text: string) => {
  if (ttsCache.has(text)) {
    playAudio(ttsCache.get(text))
  } else {
    const audio = await fetchTTS(text)
    ttsCache.set(text, audio)
    playAudio(audio)
  }
}
```

### 3. 流式处理

- TTS 使用流式返回 (`/tts-stream`)，边下载边播放
- STT 目前整段识别，未来支持 WebSocket 流式

## 总结

整个语音系统的工作流程：

1. **输入**：用户通过按钮或快捷键触发录音
2. **识别**：音频通过 FunASR (本地) 转换为文字
3. **处理**：文字送入 Agent 进行对话处理
4. **输出**：Agent 回复通过 Edge-TTS (免费) 合成语音
5. **播放**：前端播放语音，完成交互闭环

所有环节都支持中文优化，且无需额外 API 费用！
