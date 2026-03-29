# Tauri 语音消息功能配置指南

## 功能概述

EvoLoop 语音功能包含三个主要部分：
1. **语音输入** (STT) - 按住说话，自动转文字
2. **语音输出** (TTS) - AI 语音回复，自动朗读
3. **语音消息** - 发送和播放语音消息

## 已实现的组件

### 1. 前端组件 - 语音输入 (STT)

| 文件 | 说明 |
|:---|:---|
| `src/hooks/useVoiceRecorder.ts` | 录音 Hook，支持波形检测 |
| `src/hooks/useTranscription.ts` | 语音转文字 Hook |
| `src/utils/voiceStorage.ts` | Tauri 本地文件存储工具 |
| `src/utils/permissions.ts` | 麦克风权限检查 |
| `src/components/Chat/VoiceRecorderButton.tsx` | 按住说话按钮组件 |
| `src/components/Chat/VoiceMessage.tsx` | 语音消息气泡组件 |
| `src/components/Chat/VoiceMessageWithTranscript.tsx` | 带转文字的语音消息 |

### 2. 前端组件 - 语音输出 (TTS)

| 文件 | 说明 |
|:---|:---|
| `src/hooks/useTTS.ts` | TTS Hook，支持播放控制 |
| `src/components/Chat/TTSButton.tsx` | TTS 按钮和设置组件 |
| `src/components/Settings/TTSSettings.tsx` | TTS 设置面板 |

### 3. 后端修改

| 文件 | 修改内容 |
|:---|:---|
| `app/api/routes/audio.py` | Whisper STT + OpenAI TTS API |
| `app/api/main.py` | 注册 audio 路由 |
| `app/api/routes/agent.py` | 支持 audio 附件保存 metadata |
| `app/api/routes/conversations.py` | 消息序列化包含 metadata |
| `app/models/conversation.py` | MessageReference 添加 metadata 字段 |
| `app/domain/project/reference_service.py` | 添加 audio 类型处理 |

### 4. 集成修改

| 文件 | 修改内容 |
|:---|:---|
| `ChatInputArea.tsx` | 集成语音录制、输入模式切换、自动转文字、TTS 控制 |
| `AttachmentPreview.tsx` | 支持 `audio` 类型附件 |
| `MessageContent.tsx` | 支持 `[Audio: ...]` 渲染播放器 |
| `ChatMessageItem.tsx` | 检测语音附件，添加 TTS 按钮，自动朗读 |
| `MessageList.tsx` | 使用 SmartChatMessageItem |
| `chatStore.ts` | 支持 attachments 持久化 |

### 5. 数据库迁移

| 文件 | 说明 |
|:---|:---|
| `alembic/versions/20250328_add_metadata_to_message_references.py` | 添加 metadata JSON 列 |

## 安装依赖

### 前端依赖

```bash
cd frontend/packages/desktop

# 安装 Tauri 插件
npm install @tauri-apps/plugin-dialog @tauri-apps/plugin-fs
```

### 后端依赖

后端使用 OpenAI API，需要设置环境变量：

```bash
# .env
OPENAI_API_KEY=your_openai_api_key
```

## Tauri 配置

### 1. 添加权限到 `src-tauri/capabilities/default.json`

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

### 2. 注册 Tauri 插件

在 `src-tauri/src/lib.rs` 中添加：

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        // ... 其他插件
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

## 数据库迁移

运行迁移命令：

```bash
cd backend
alembic upgrade head
```

或者手动执行 SQL：

```sql
ALTER TABLE message_references ADD COLUMN metadata JSON DEFAULT NULL;
```

## 功能使用

### 发送语音消息

1. 点击输入框左侧的 🎤 图标切换到语音模式
2. 按住麦克风按钮开始录音
3. 说话（显示波形动画和时长）
4. 松开按钮发送语音
5. 手指上滑可取消发送

### 自动转文字

- 语音录制完成后自动进行语音识别
- 识别结果会显示在语音消息下方
- 可以在语音模式切换按钮旁关闭自动转文字

### 播放语音消息

- 点击语音气泡中的播放按钮
- 波形会显示播放进度
- 再次点击暂停

## 文件存储

语音文件存储位置：
- **macOS**: `~/Library/Application Support/com.evoloop.app/voice/recordings/`
- **Windows**: `%APPDATA%/com.evoloop.app/voice/recordings/`
- **Linux**: `~/.local/share/com.evoloop.app/voice/recordings/`

## API 接口

### 语音转文字

```http
POST /api/v1/audio/transcribe
Content-Type: multipart/form-data

file: <audio_file>
language: zh  # 可选，auto 为自动检测
model: whisper-1  # 可选
```

响应：
```json
{
  "text": "识别出的文字",
  "duration": 12.5,
  "language": "zh",
  "confidence": 0.95
}
```

### 获取可用音色列表

```http
GET /api/v1/audio/voices
```

## 权限说明

应用需要以下权限：
1. **麦克风访问** - 用于录制语音
2. **本地文件系统** - 用于存储语音文件

首次使用时会自动请求权限，或在系统设置中手动开启。

## 国际化键

添加以下翻译键到项目中：

### 语音输入 (STT)

```json
{
  "chat": {
    "voice": {
      "switchToVoice": "切换到语音输入",
      "switchToText": "切换到文字输入",
      "permissionDenied": "麦克风权限被拒绝",
      "recordingFailed": "录音启动失败",
      "recordingError": "录音出错",
      "cancelled": "已取消",
      "tooShort": "录音时间太短",
      "sent": "[语音消息]",
      "sentSuccess": "语音已发送",
      "uploadFailed": "语音上传失败",
      "noProject": "请先选择项目",
      "message": "语音消息",
      "releaseToCancel": "松开取消发送",
      "slideUpToCancel": "手指上滑取消",
      "transcribe": "转文字",
      "transcribing": "转文字中...",
      "transcribed": "已转文字",
      "expand": "展开",
      "retranscribe": "重新转文字",
      "autoTranscribeOn": "自动转文字",
      "autoTranscribeOff": "不转文字"
    }
  }
}
```

### 语音输出 (TTS)

```json
{
  "chat": {
    "tts": {
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
    }
  },
  "settings": {
    "tts": {
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
}
```

## 注意事项

1. **录音格式**: 浏览器录制为 WebM/Opus 格式，兼容性较好
2. **文件大小**: 1 分钟语音约 100-200KB
3. **存储清理**: 本地语音文件默认保留 7 天
4. **转文字限制**: 使用 OpenAI Whisper API，需要网络连接
5. **浏览器兼容**: 需要支持 MediaRecorder API 的现代浏览器

## 故障排查

### 无法录音

1. 检查系统麦克风权限是否开启
2. 检查是否有其他应用占用麦克风
3. 查看控制台是否有错误信息

### 语音无法播放

1. 检查文件 URL 是否正确（使用 `convertFileSrc`）
2. 检查音频格式是否被浏览器支持
3. 检查网络连接（如果是远程文件）

### 转文字失败

1. 检查 OpenAI API Key 是否配置正确
2. 检查网络连接
3. 查看后端日志获取详细错误

### 文件保存失败

1. 检查 Tauri fs 权限配置
2. 检查磁盘空间
3. 检查文件路径权限

## 成本估算

### STT (语音识别)
使用 OpenAI Whisper API：
- $0.006 / 分钟
- 1 小时语音 ≈ $0.36
- 1000 小时语音 ≈ $360

### TTS (语音合成)
使用 OpenAI TTS API：
- $0.015 / 1,000 字符
- 平均一条 AI 消息约 200-500 字符
- 每条消息约 $0.003 - $0.0075
- 1000 条消息约 $3 - $7.5

## 使用指南

### 发送语音消息

1. 点击输入框左侧的 🎤 图标切换到语音模式
2. 按住麦克风按钮开始录音
3. 说话（显示波形动画和时长）
4. 松开按钮发送语音
5. 手指上滑可取消发送

### 自动转文字

- 语音录制完成后自动进行语音识别（如果开启）
- 识别结果会显示在语音消息下方
- 可以点击自动转文字按钮切换开关

### 播放语音消息

- 点击语音气泡中的播放按钮
- 波形会显示播放进度
- 再次点击暂停

### 让 AI 语音回复

1. 点击工具栏的 🔊 按钮开启自动朗读
2. AI 回复消息时会自动朗读
3. 点击 AI 消息上的 🔊 按钮可手动朗读
4. 在设置中选择喜欢的音色和语速

## 故障排查

### 无法录音

1. 检查系统麦克风权限是否开启
2. 检查是否有其他应用占用麦克风
3. 查看控制台是否有错误信息

### 语音无法播放

1. 检查文件 URL 是否正确（使用 `convertFileSrc`）
2. 检查音频格式是否被浏览器支持
3. 检查网络连接（如果是远程文件）

### 转文字失败

1. 检查 OpenAI API Key 是否配置正确
2. 检查网络连接
3. 查看后端日志获取详细错误

### TTS 失败

1. 检查 OpenAI API Key 是否配置正确
2. 检查网络连接
3. 检查浏览器是否支持 Audio API

### 文件保存失败

1. 检查 Tauri fs 权限配置
2. 检查磁盘空间
3. 检查文件路径权限
