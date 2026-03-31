# Phase 3: 语音消息功能 - 完整实现文档

## 功能概述

Phase 3 实现了 EvoLoop 的完整语音交互能力，包括：

| 功能 | 描述 | 状态 |
|:---|:---|:---|
| **Phase 3.1** | 语音录制与消息发送 | ✅ 完成 |
| **Phase 3.2** | 语音转文字 (Whisper STT) | ✅ 完成 |
| **Phase 3.3** | AI 语音回复 (TTS) | ✅ 完成 |

## 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户交互层                                   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ 按住说话按钮  │  │ 语音消息气泡  │  │ AI 语音朗读   │              │
│  │ VoiceRecorder│  │ VoiceMessage │  │   TTSButton  │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
└─────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          前端逻辑层                                   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ useVoiceRecorder (录音) → Blob → 本地存储 → 上传 → 消息发送   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ useTranscription (转写) → /api/audio/transcribe → 填充输入框  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ useTTS (朗读) → /api/audio/tts-stream → Audio 播放           │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           后端 API 层                                 │
├─────────────────────────────────────────────────────────────────────┤
│  POST /api/v1/audio/transcribe  →  Whisper STT  →  返回文字         │
│  POST /api/v1/audio/tts-stream  →  OpenAI TTS   →  返回音频流        │
│  GET  /api/v1/audio/voices      →  返回音色列表                       │
└─────────────────────────────────────────────────────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          外部服务层                                   │
├─────────────────────────────────────────────────────────────────────┤
│  OpenAI Whisper API  (STT: $0.006/min)                              │
│  OpenAI TTS API      (TTS: $0.015/1K chars)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## 用户流程

### 1. 发送语音消息

```
点击 🎤 切换到语音模式
      │
      ▼
按住麦克风按钮 ────────────► 上滑取消
      │                         │
      ▼                         ▼
开始录音 (波形动画) ◄────── 取消发送
      │
      ▼
松开按钮
      │
      ▼
保存本地 + 上传服务器
      │
      ▼
自动转文字 (如开启)
      │
      ▼
发送消息 (带语音附件)
```

### 2. 接收 AI 语音回复

```
AI 消息生成完成
      │
      ▼
检查 autoSpeak 设置
      │
      ├── 开启 ──► 调用 TTS API
      │              │
      │              ▼
      │           流式获取音频
      │              │
      │              ▼
      │           自动播放
      │
      └── 关闭 ──► 显示 🔊 按钮
                     │
                     ▼
                  用户点击后播放
```

## 文件清单

### 后端

| 文件 | 修改类型 | 说明 |
|:---|:---|:---|
| `backend/app/api/routes/audio.py` | 新增 | STT/TTS API 端点 |
| `backend/app/api/main.py` | 修改 | 注册 audio 路由 |
| `backend/app/models/conversation.py` | 修改 | 添加 metadata 字段 |
| `backend/app/api/routes/agent.py` | 修改 | 保存音频 metadata |
| `backend/app/api/routes/conversations.py` | 修改 | 消息序列化包含 metadata |
| `backend/app/domain/project/reference_service.py` | 修改 | 处理 audio 类型 |
| `backend/app/alembic/versions/20250328_add_metadata*.py` | 新增 | 数据库迁移 |

### 前端

#### Hooks
| 文件 | 说明 |
|:---|:---|
| `src/hooks/useVoiceRecorder.ts` | 录音控制 + 波形采集 |
| `src/hooks/useTranscription.ts` | 语音转文字 |
| `src/hooks/useTTS.ts` | TTS 播放控制 + 队列管理 |

#### 组件
| 文件 | 说明 |
|:---|:---|
| `src/components/Chat/VoiceRecorderButton.tsx` | 按住说话按钮 |
| `src/components/Chat/VoiceMessage.tsx` | 语音消息播放器 |
| `src/components/Chat/TTSButton.tsx` | TTS 按钮 + 设置 |
| `src/components/Settings/TTSSettings.tsx` | TTS 设置面板 |

#### 工具
| 文件 | 说明 |
|:---|:---|
| `src/utils/voiceStorage.ts` | Tauri 本地文件存储 |
| `src/utils/permissions.ts` | 麦克风权限管理 |

#### 集成修改
| 文件 | 修改 |
|:---|:---|
| `src/components/Chat/ChatInputArea.tsx` | 语音模式切换 + TTS 控制 |
| `src/components/Chat/ChatMessageItem.tsx` | 语音渲染 + TTS 按钮 + 自动朗读 |
| `src/components/Chat/MessageList.tsx` | 使用 SmartChatMessageItem |
| `src/components/Chat/AttachmentPreview.tsx` | 支持 audio 类型 |

## API 接口

### STT (语音识别)

```http
POST /api/v1/audio/transcribe
Content-Type: multipart/form-data

file: <audio_file>
language: zh|en|ja|auto  # 默认 auto
model: whisper-1        # 默认 whisper-1
prompt: <optional>      # 提示词

Response:
{
  "text": "识别出的文字内容",
  "duration": 12.5,
  "language": "zh",
  "confidence": 0.95
}
```

### TTS (语音合成)

```http
POST /api/v1/audio/tts-stream
Content-Type: multipart/form-data

text: 要合成的文本
voice_id: alloy|echo|fable|onyx|nova|shimmer  # 默认 alloy
speed: 0.5-2.0        # 默认 1.0
format: mp3|opus|aac|flac  # 默认 mp3

Response: audio/mpeg 流
```

```http
GET /api/v1/audio/voices

Response:
{
  "voices": [
    {"id": "alloy", "name": "Alloy", "gender": "neutral", "description": "..."},
    ...
  ]
}
```

## 配置

### 环境变量

```bash
# backend/.env
OPENAI_API_KEY=your_openai_api_key
```

### LocalStorage

| Key | 用途 | 默认 |
|:---|:---|:---|
| `evoloop_auto_speak` | 自动朗读开关 | false |
| `evoloop_tts_speed` | TTS 语速 | 1.0 |
| `evoloop_auto_transcribe` | 自动转文字 | true |

### Tauri 权限

`src-tauri/capabilities/default.json`:

```json
{
  "permissions": [
    "core:default",
    "dialog:default",
    "fs:default",
    {
      "identifier": "fs:allow-app-write",
      "allow": [{ "path": "$APPLOCALDATA/**" }]
    },
    {
      "identifier": "fs:allow-app-read",
      "allow": [{ "path": "$APPLOCALDATA/**" }]
    }
  ]
}
```

## 数据库变更

```sql
-- 添加 metadata 列到 message_references 表
ALTER TABLE message_references ADD COLUMN metadata JSON DEFAULT NULL;
```

## 成本分析

### STT (Whisper)
- $0.006 / 分钟
- 1 分钟语音 ≈ $0.006
- 1 小时语音 ≈ $0.36

### TTS (OpenAI)
- $0.015 / 1,000 字符
- 平均 AI 消息 300 字符 ≈ $0.0045
- 1000 条消息 ≈ $4.5

## 使用指南

### 发送语音
1. 点击 🎤 切换到语音模式
2. 按住麦克风录音
3. 松开发送
4. 手指上滑取消

### 设置自动朗读
1. 点击输入框工具栏的 🔊 按钮
2. 或进入 设置 → 语音设置
3. 开启"自动朗读 AI 回复"
4. 选择喜欢的音色和语速

### 手动朗读
- 点击 AI 消息上的 🔊 按钮

## 故障排查

| 问题 | 解决方案 |
|:---|:---|
| 无法录音 | 检查麦克风权限、Tauri fs 权限配置 |
| 转文字失败 | 检查 OpenAI API Key、网络连接 |
| TTS 失败 | 检查 OpenAI API Key、浏览器 Audio API 支持 |
| 语音无法播放 | 检查文件路径、使用 `convertFileSrc` |

## 后续优化

1. **实时转写** - WebSocket 流式返回识别结果
2. **语音打断** - 用户说话时自动停止 AI 朗读
3. **本地缓存** - 缓存已生成的 TTS 音频
4. **情感语音** - 根据内容情感调整语调
5. **多语言 TTS** - 自动检测语言并使用对应音色

## 参考文档

- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text)
- [OpenAI TTS API](https://platform.openai.com/docs/guides/text-to-speech)
- [Tauri FS Plugin](https://v2.tauri.app/plugin/file-system/)
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)
