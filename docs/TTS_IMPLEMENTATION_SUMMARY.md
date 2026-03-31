# Phase 3.3: TTS (Text-to-Speech) 实现摘要

## 概述
为 EvoLoop 添加 AI 语音回复功能，让 AI 能够"说话"回复用户。

## 后端实现

### API 端点

| 端点 | 方法 | 说明 |
|:---|:---|:---|
| `/api/v1/audio/tts` | POST | 文本转语音，返回音频 URL |
| `/api/v1/audio/tts-stream` | POST | 流式 TTS，直接返回音频流 |
| `/api/v1/audio/tts-file/{filename}` | GET | 获取 TTS 生成的音频文件 |
| `/api/v1/audio/voices` | GET | 获取可用音色列表 |

### 代码文件

**`backend/app/api/routes/audio.py`**

主要功能：
- OpenAI TTS API 集成
- 音频流式返回（ faster playback）
- 音频文件临时存储
- 6 种音色支持：alloy, echo, fable, onyx, nova, shimmer

```python
# 流式 TTS 端点
@router.post("/tts-stream")
async def text_to_speech_stream(...)

# 音色列表
@router.get("/voices")
async def list_voices()
```

## 前端实现

### Hooks

**`frontend/packages/desktop/src/hooks/useTTS.ts`**

主要功能：
- `useTTS()` - TTS 播放控制
- `useAutoSpeak()` - 自动朗读设置
- `useTTSQueue()` - 队列播放（用于长文本分段）

```typescript
const {
  isSpeaking,    // 是否正在播放
  isLoading,     // 是否加载中
  voices,        // 可用音色列表
  currentVoice,  // 当前音色
  speak,         // 播放文本
  stop,          // 停止播放
} = useTTS()

const { autoSpeak, toggleAutoSpeak } = useAutoSpeak()
```

### 组件

**`frontend/packages/desktop/src/components/Chat/TTSButton.tsx`**

1. **TTSButton** - 单条消息的朗读按钮
2. **TTSControls** - TTS 设置下拉菜单（音色选择、语速调节）
3. **AutoSpeakIndicator** - 自动朗读状态指示器

**`frontend/packages/desktop/src/components/Settings/TTSSettings.tsx`**

设置页面中的 TTS 配置面板：
- 自动朗读开关
- 语速调节 (0.5x - 2.0x)
- 音色选择（带预览）

### 集成

**`ChatMessageItem.tsx`**
- 添加 TTS 按钮到 AI 消息的操作栏
- `SmartChatMessageItem` 包装组件支持自动朗读

**`MessageList.tsx`**
- 使用 `SmartChatMessageItem` 替代 `ChatMessageItem`

**`ChatInputArea.tsx`**
- 工具栏添加自动朗读开关和设置按钮

## 用户交互流程

### 手动朗读
```
用户点击 AI 消息上的 🔊 按钮
         ↓
   调用 /api/v1/audio/tts-stream
         ↓
   音频流式返回并播放
```

### 自动朗读
```
AI 消息生成完成 (status === "completed")
         ↓
   检查 autoSpeak 设置
         ↓
   自动调用 speak(message.content)
         ↓
   播放 AI 回复语音
```

### 设置面板
```
设置 → 语音设置
   ├── 自动朗读 AI 回复 [开关]
   ├── 语速调节 [滑块 0.5x - 2.0x]
   └── 音色选择 [单选]
        ├── Alloy (中性)
        ├── Echo (男声)
        ├── Fable (中性)
        ├── Onyx (男声)
        ├── Nova (女声)
        └── Shimmer (女声)
        [每个音色可点击预览]
```

## 配置与存储

### LocalStorage 键

| 键 | 说明 | 默认值 |
|:---|:---|:---|
| `evoloop_auto_speak` | 自动朗读开关 | `false` |
| `evoloop_tts_speed` | 语速设置 | `1.0` |

### 后端环境变量

```bash
OPENAI_API_KEY=your_openai_api_key
```

## 成本估算

使用 OpenAI TTS API：
- $0.015 / 1,000 字符
- 平均一条 AI 消息约 200-500 字符
- 每条消息约 $0.003 - $0.0075
- 1000 条消息约 $3 - $7.5

## 国际化键

```json
{
  "chat.tts": {
    "speak": "朗读",
    "stop": "停止朗读",
    "settings": "语音设置",
    "autoSpeak": "自动朗读",
    "autoSpeakOn": "自动朗读已开启",
    "autoSpeakOff": "自动朗读已关闭",
    "speed": "语速",
    "slow": "慢",
    "normal": "正常",
    "fast": "快",
    "voice": "选择音色",
    "voiceDesc": "选择您喜欢的 AI 语音",
    "preview": "你好，我是语音助手。",
    "playbackError": "播放失败",
    "error": "语音合成失败",
    "gender": {
      "male": "男声",
      "female": "女声",
      "neutral": "中性"
    }
  },
  "settings.tts": {
    "title": "文本转语音",
    "description": "配置 AI 语音输出设置",
    "autoSpeak": "自动朗读 AI 回复",
    "autoSpeakDesc": "AI 消息到达时自动朗读",
    "speechRate": "语速",
    "voice": "语音选择",
    "voiceDesc": "选择您喜欢的 AI 语音",
    "slow": "慢",
    "normal": "正常",
    "fast": "快",
    "note": "TTS 使用 OpenAI API。语音生成费用约为每 1000 字符 $0.015。"
  }
}
```

## 文件清单

### 后端
- `backend/app/api/routes/audio.py` (已更新)
  - 添加 `/tts-stream` 端点
  - 添加 `/tts-file/{filename}` 端点
  - 添加 `/voices` 端点

### 前端
- `frontend/packages/desktop/src/hooks/useTTS.ts` (新增)
- `frontend/packages/desktop/src/components/Chat/TTSButton.tsx` (新增)
- `frontend/packages/desktop/src/components/Settings/TTSSettings.tsx` (新增)
- `frontend/packages/desktop/src/components/Chat/ChatMessageItem.tsx` (更新)
- `frontend/packages/desktop/src/components/Chat/MessageList.tsx` (更新)
- `frontend/packages/desktop/src/components/Chat/ChatInputArea.tsx` (更新)

## 后续优化建议

1. **长文本分段** - 将长消息分段播放，支持中断
2. **语音队列** - 连续播放多条消息
3. **语音打断** - 用户说话时自动停止播放
4. **本地缓存** - 缓存已生成的语音
5. **多语言支持** - 根据内容自动选择语言
6. **情感识别** - 根据内容情感调整语调

## 已知限制

1. **网络依赖** - TTS 需要网络连接
2. **字符限制** - 单次最多 4096 字符
3. **费用** - 使用 OpenAI API 产生费用
4. **浏览器支持** - 需要现代浏览器的 Audio API 支持
