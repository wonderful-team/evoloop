# Tauri 语音消息功能 - 实现摘要

## 完成的功能

### Phase 3.2: Whisper STT (Speech-to-Text) 集成 ✅

#### 后端实现

1. **音频转录 API** (`backend/app/api/routes/audio.py`)
   - `POST /api/v1/audio/transcribe` - 使用 OpenAI Whisper 进行语音识别
   - 支持多种音频格式 (webm, mp3, wav)
   - 返回识别的文字、语言、时长和置信度

2. **数据库模型更新** (`backend/app/models/conversation.py`)
   - `MessageReference.metadata` JSON 字段 - 存储语音时长、波形数据、转写文本

3. **消息引用处理** (`backend/app/api/routes/agent.py`)
   - 保存语音附件时自动提取并保存 metadata

4. **数据库迁移** (`backend/app/alembic/versions/20250328_add_metadata_to_message_references.py`)
   - 添加 metadata JSON 列到 message_references 表

#### 前端实现

1. **录音 Hook** (`frontend/packages/desktop/src/hooks/useVoiceRecorder.ts`)
   - 使用 Web Audio API 录制语音
   - 实时音量检测和波形数据采集
   - 支持取消录音

2. **语音录制按钮** (`frontend/packages/desktop/src/components/Chat/VoiceRecorderButton.tsx`)
   - 按住说话 UI
   - 上滑取消发送
   - 实时波形动画显示
   - 录音时长显示

3. **语音消息组件** (`frontend/packages/desktop/src/components/Chat/VoiceMessage.tsx`)
   - 波形进度显示
   - 播放/暂停控制
   - 转写文本显示

4. **输入框集成** (`frontend/packages/desktop/src/components/Chat/ChatInputArea.tsx`)
   - 文字/语音输入模式切换
   - 自动转文字开关
   - 语音上传后自动调用转录 API
   - 转写结果自动填入输入框

5. **附件预览** (`frontend/packages/desktop/src/components/Chat/AttachmentPreview.tsx`)
   - 支持 audio 类型附件显示

6. **消息显示** (`frontend/packages/desktop/src/components/Chat/ChatMessageItem.tsx`)
   - 检测语音消息附件并渲染 VoiceMessage 组件

7. **工具函数**
   - `voiceStorage.ts` - 本地文件存储、时长格式化
   - `permissions.ts` - 麦克风权限检查

## 工作流程

### 发送语音消息

```
┌─────────────────────────────────────────────────────────────────┐
│  用户操作                                                        │
│  1. 点击 🎤 切换到语音模式                                        │
│  2. 按住麦克风按钮开始录音                                        │
│  3. 说话（显示波形和时长）                                        │
│  4. 松开按钮发送 / 上滑取消                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  前端处理                                                        │
│  1. Web Audio API 录制音频 → Blob                                 │
│  2. 保存到 Tauri 本地存储                                         │
│  3. 上传音频文件到后端                                            │
│  4. 调用 /api/v1/audio/transcribe 转文字（如开启自动转写）        │
│  5. 发送消息（包含音频附件和 metadata）                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  后端处理                                                        │
│  1. 保存音频文件                                                 │
│  2. 保存 MessageReference (type=audio, metadata={duration, ...}) │
│  3. Whisper STT → 返回转写文本                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 配置要求

### 后端环境变量

```bash
# .env
OPENAI_API_KEY=your_openai_api_key
```

### Tauri 权限配置

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

### 数据库迁移

```bash
cd backend
alembic upgrade head
```

## 国际化键

```json
{
  "chat.voice.switchToVoice": "切换到语音输入",
  "chat.voice.switchToText": "切换到文字输入", 
  "chat.voice.permissionDenied": "麦克风权限被拒绝",
  "chat.voice.recordingFailed": "录音启动失败",
  "chat.voice.recordingError": "录音出错",
  "chat.voice.cancelled": "已取消",
  "chat.voice.tooShort": "录音时间太短",
  "chat.voice.releaseToCancel": "松开取消发送",
  "chat.voice.slideUpToCancel": "手指上滑取消",
  "chat.voice.transcribing": "转文字中...",
  "chat.voice.autoTranscribeOn": "自动转文字",
  "chat.voice.autoTranscribeOff": "不转文字"
}
```

## 成本估算

使用 OpenAI Whisper API:
- $0.006 / 分钟
- 1 小时语音 ≈ $0.36
- 1000 小时语音 ≈ $360

## 后续功能

### Phase 3.3: TTS (AI 语音回复)

后端已实现基础接口，前端需要添加:
- AI 消息自动播放设置
- TTS 音色选择
- 播放队列管理
- 音频流式播放

## 已知问题与限制

1. **录音格式**: 浏览器录制为 WebM/Opus 格式
2. **浏览器兼容**: 需要支持 MediaRecorder API 的现代浏览器
3. **网络依赖**: Whisper 转写需要网络连接
4. **文件大小**: 1 分钟语音约 100-200KB

## 文件清单

### 后端
- `backend/app/api/routes/audio.py` (新增)
- `backend/app/api/main.py` (更新)
- `backend/app/models/conversation.py` (更新)
- `backend/app/api/routes/agent.py` (更新)
- `backend/app/api/routes/conversations.py` (更新)
- `backend/app/alembic/versions/20250328_add_metadata_to_message_references.py` (新增)

### 前端
- `frontend/packages/desktop/src/hooks/useVoiceRecorder.ts` (新增)
- `frontend/packages/desktop/src/utils/voiceStorage.ts` (新增)
- `frontend/packages/desktop/src/utils/permissions.ts` (新增)
- `frontend/packages/desktop/src/components/Chat/VoiceRecorderButton.tsx` (新增)
- `frontend/packages/desktop/src/components/Chat/VoiceMessage.tsx` (新增)
- `frontend/packages/desktop/src/components/Chat/ChatInputArea.tsx` (更新)
- `frontend/packages/desktop/src/components/Chat/AttachmentPreview.tsx` (更新)
- `frontend/packages/desktop/src/components/Chat/ChatMessageItem.tsx` (更新)
