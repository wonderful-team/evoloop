# 语音架构重构方案 — Python 中心化

## 1. 目标

将桌面端语音链路从 Rust 中心化重构为 Python 中心化，音频全程在 Python 进程内闭环，零 Rust 中转。

## 2. 现状与问题

### 2.1 当前架构

```
┌─ Rust (Tauri) ──────────────────────────────────────────────────────┐
│                                                                      │
│  Mic(CPAL) → VAD → Qwen3 ASR / Seeduplex WS(binary protocol)        │
│                  ↓                                                   │
│             voice.route → WS ──→ Python Agent                        │
│                                  ↓                                   │
│             voice.route_result ← WS ── Python Agent                 │
│                  ↓                                                   │
│  EdgeTTS / inject_tts → Seeduplex WS → TTS audio → afplay           │
│                                                                      │
│  + state_machine, event_bus, dictation_paste, screen_recorder       │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心问题

| 问题 | 表现 |
|------|------|
| 音频链路绕路 | Mic PCM → Rust → WS → Python → WS → Rust → Seeduplex WS，来回跨进程 |
| 协议维护成本高 | Rust 手写 Volcengine binary 协议（frame 组包/解析、事件 ID 映射），官方 SDK 是 Python |
| 状态机碎片化 | Rust 有 VoiceStateMachine，Python 有 VoiceSessionState，同步靠 WS 消息 |
| 事件处理重复 | handle_route_result 在 Rust，Agent 在 Python，靠 route_result 传参同步 |
| 功能复制 | TTS、ASR、VAD、状态机在 Rust 和 Python 各有一份实现 |

### 2.3 权限现状

| 权限 | 当前持有者 | 类型 |
|------|-----------|------|
| 麦克风 | Tauri.app (Info.plist) | 弹窗授权 |
| 屏幕录制 | Tauri.app (Info.plist) | 弹窗+系统设置手动勾选 |
| Accessibility (粘贴/焦点) | Tauri.app (entitlements) | 系统设置手动勾选 |

搬动任何功能都需要考虑对应权限的转移。

## 3. 目标架构

### 3.1 设计核心原则

1. **权限不转移：Python 只承担弹窗授权** — 麦克风（Info.plist 弹窗）由 Python pyaudio 持有。Accessibility、屏幕录制等需要系统设置手动勾选的权限，保留在已获授权的 Tauri 进程。
2. **打断响应** — 播放进程必须能被 VAD 瞬间终止。优先使用 `pyaudio` 流式输出（清缓冲区实现毫秒级响应），次选 `subprocess.Popen.kill()` 终止 afplay。

### 3.2 整体视图

```
┌─ Python ───────────────────────────────────────────────────────────┐
│                                                                     │
│  pyaudio Mic → Silero VAD → Volcengine WS (官方 SDK)              │
│                                ↓                                    │
│                          ASR text → Agent → RAG + 路由              │
│                                ↓                                    │
│                    Volcengine WS → TTS PCM                         │
│                                ↓                                    │
│                          afplay / pyaudio 播放                     │
│                                                                     │
│  + 状态机 / 事件调度 / dictation_paste(pyobjc)                     │
└──────────────────────────────────────────────────────────────────────┘
            ▲                     │
            │  控制 WS (JSON)     │ 控制 WS (JSON)
            │                     ▼
┌─ Rust ─────────────────────────────────────────────────────────────┐
│  TauriEventBus (Python→前端)                                       │
│  全局快捷键 / 托盘                                                  │
│  dictation_paste (Accessibility) ← 由 Python 触发                  │
│  screen_recorder (屏幕录制) ← 由 Python 触发                       │
│  Tauri 应用入口 / 窗口管理 / 权限检查                               │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 音频链路对比

| 环节 | 当前 | 目标 |
|------|------|------|
| 采集 | Rust CPAL | Python pyaudio |
| VAD | Rust sherpa-onnx | Python silero-vad |
| ASR | Rust Qwen3 / Rust Seeduplex binary | Python Volcengine WS 官方 SDK |
| TTS | Rust EdgeTTS / Seeduplex inject_tts | Python edge-tts / Volcengine TTS / afplay |
| 播放 | Rust afplay | Python subprocess.afplay / pyaudio |
| 状态机 | Rust + Python 两份 | Python 统一 |
| 协议 | Rust 手写 binary frame | Python websockets 官方 SDK |
| 中转 | Rust WS (双向PCM) | 零中转 |

音频跨进程次数：**5 次 → 0 次**

### 3.3 控制链路

Python 和 Rust 之间只传轻量 JSON 控制消息：

```
Python → Rust WS:
  {"type": "paste", "text": "..."}              → dictation_paste()
  {"type": "screencapture"}                     → screen_recorder()
  {"type": "event", "name": "voice:state",
   "payload": {"state": "listening"}}           → Tauri emit → 前端
  {"type": "event", "name": "voice:error",
   "payload": {"message": "..."}}              → Tauri emit → 前端
  {"type": "event", "name": "seeduplex:status",
   "payload": {"connected": true}}             → Tauri emit → 前端

Rust → Python WS:
  {"type": "start_voice", "thread_id": "...",
   "lang": "zh-CN", "mode": "dialogue"}        → Python 启动会话
  {"type": "stop_voice"}                         → Python 停止会话
  {"type": "switch_mode", "mode": "dictation"}  → Python 切换模式
```

**无音频数据经过控制 WS。**

## 4. 文件变更清单

### 4.1 Rust 删除文件（100% 移除）

| 文件 | 行数 | 替代 |
|------|------|------|
| `voice/mic_capture.rs` | ~200 | Python pyaudio |
| `voice/aec_engine.rs` | ~150 | 废弃 |
| `voice/vad_engine.rs` | ~80 | Python silero-vad |
| `voice/offline_asr.rs` | ~70 | 废弃 |
| `voice/asr_engine.rs` | ~20 | 废弃 |
| `voice/seeduplex_client.rs` | ~600 | Python Volcengine SDK |
| `voice/tts_engine.rs` | ~800 | Python edge-tts + afplay |
| `voice/voice_session.rs` | ~1400 | Python 统一管理 |
| `voice/state_machine.rs` | ~80 | 废弃 |
| `voice/audio_utils.rs` | ~30 | Python |
| `voice/wake_word.rs` | ~50 | Python |
| **删除合计** | **~3500** | |

### 4.2 Rust 保留并精简的文件

| 文件 | 当前行数 | 精简后 | 原因 |
|------|---------|--------|------|
| `lib.rs` | ~800 | ~300 | 入口 + VoiceCommand + TauriEventBus |
| `voice/mod.rs` | ~20 | ~10 | 只保留 event + ws_client |
| `voice/event.rs` | ~30 | ~30 | VoiceEventBus trait（Python→前端桥接） |
| `voice/ws_client.rs` | ~200 | ~100 | 控制 WS（JSON 消息中转） |
| `global_shortcut.rs` | ~30 | ~30 | 全局快捷键 |
| `tray.rs` | ~100 | ~50 | 系统托盘 |
| `screen_recorder.rs` | ~150 | ~150 | 屏幕录制（授权不动） |
| `commands/permissions.rs` | ~80 | ~80 | 权限检查 |
| `commands/screenshot.rs` | ~50 | ~50 | 截图命令 |
| `commands/window.rs` | ~50 | ~50 | 窗口管理 |
| **Python 新增** | **~760** | |

### 4.3 Python 新增文件

| 文件 | 行数 | 内容 |
|------|------|------|
| `app/infrastructure/voice/volc_dialog.py` | ~300 | Volcengine 对话管理（StartSession → ASR → ChatRAGText → TTS） |
| `app/core/channel/input/voice_mic.py` | ~100 | pyaudio 麦克风采集 + silero-vad 集成 |
| `app/core/channel/input/voice_player.py` | ~80 | TTS PCM 播放（pyaudio / afplay） |
| `app/infrastructure/voice/control_ws.py` | ~80 | Python←→Rust 控制 WS（JSON 消息） |
| `app/core/channel/input/voice_controller.py` | ~200 | 统一的语音控制器（整合 mic → Volcengine → Agent → TTS 流程） |

### 4.4 Python 修改/保留/删除清单

#### 4.4.1 保留（逻辑不变，28 个）

| 文件 | 理由 |
|------|------|
| `core/channel/input/voice_input.py` | L0 编排逻辑不变 |
| `core/channel/output/voice_channel.py` | Agent→TTS 管道不变，推送目标改进程内 |
| `core/voice/state_machine.py` | 纯逻辑，无外部依赖 |
| `core/routing/local_matcher.py` | L0 匹配算法不变 |
| `core/routing/router.py` | L0 匹配器工厂不变 |
| `core/routing/retriever.py` | L1 检索不变 |
| `core/routing/index.py` | LanceDB 向量索引不变 |
| `core/routing/sync.py` | 索引重建逻辑不变 |
| `core/routing/session_frame.py` | 多轮对话处理不变 |
| `core/routing/schemas.py` | 路由数据模型不变 |
| `core/routing/init_spec.py` | L0 规范生成不变（缓存传输方式改进程内） |
| `core/routing/tasks.py` | 后台重建任务不变 |
| `core/routing/idempotency.py` | 幂等性逻辑不变 |
| `core/engine/worker_registry.py` | Worker 生命周期管理不变 |
| `infrastructure/voice/__init__.py` | 公共 API 接口 |
| `infrastructure/voice/base.py` | STT 基础抽象 |
| `infrastructure/voice/model_manager.py` | 语音模型下载管理 |
| `infrastructure/voice/utils.py` | TTS 文本清理 |
| `infrastructure/voice/tts/base.py` | TTS 基础抽象 |
| `infrastructure/voice/tts/factory.py` | 添加 Volcengine TTS 选项 |
| `infrastructure/voice/stt/factory.py` | 添加 Volcengine STT 选项 |
| `infrastructure/voice/stt/qwen3_asr.py` | 保留为离线后备 |
| `core/channel/registry.py` | 通道注册管理 |
| `core/channel/input/__init__.py` | 输入通道抽象 |
| `core/file/media_reader.py` | 文件转录服务 |
| `core/learning/multimodal_synthesizer.py` | 学习管道顺便用 STT |
| `api/routes/route.py` | HTTP 诊断端点 |
| `api/schemas/audio.py` | 音频响应模式 |

#### 4.4.2 重写（5 个）

| 文件 | 从 → 到 |
|------|---------|
| `api/routes/voice_ws.py` | WS/HTTP 端点 → 进程内管道启动+依赖注入 |
| `core/routing/executor.py` | `manager.push()` 推 WS → 进程内 TTS 引擎调用 |
| `core/routing/connection.py` | WS 连接注册表 → 进程内事件总线/回调注册表 |
| `app/main.py` | WS 全局变量引导（manager/envelope_fn）→ Volcengine 客户端初始化+音频管线启动 |
| `infrastructure/voice/stt/aliyun.py` | 阿里云 STT → Volcengine ASR 提供商（或删除） |

#### 4.4.3 删除（7 个）

| 文件 | 原因 |
|------|------|
| `infrastructure/voice/stt/__init__.py` | 空文件 |
| `infrastructure/voice/tts/__init__.py` | 空文件 |
| `infrastructure/voice/stt/base.py` | 纯 re-export stub，导入方应直接引用 `voice.base` |
| `infrastructure/voice/stt/whisper.py` | 不需要的后备 ASR |
| `infrastructure/voice/tts/edge_provider.py` | 无用 stub（`NotImplementedError`），标注"应该直接从 Rust 调用" |
| `infrastructure/voice/tts/qwen_provider.py` | 无用 stub（`NotImplementedError`），同上 |
| `api/schemas/audio.py` | 如果 HTTP STT 端点移除则删除 |

### 4.3 Python 新增文件

| 文件 | 行数 | 内容 |
|------|------|------|
| `app/infrastructure/voice/volc_dialog.py` | ~300 | Volcengine 对话管理（StartSession → ASR → ChatRAGText → TTS） |
| `app/core/channel/input/voice_mic.py` | ~100 | pyaudio 麦克风采集 + silero-vad 集成 |
| `app/core/channel/input/voice_player.py` | ~80 | TTS PCM 播放（pyaudio / afplay） |
| `app/infrastructure/voice/control_ws.py` | ~80 | Python←→Rust 控制 WS（JSON 消息） |
| `app/core/channel/input/voice_controller.py` | ~200 | 统一的语音控制器（整合 mic → Volcengine → Agent → TTS 流程） |

### 4.4 Python 修改文件

| 文件 | 改动 |
|------|------|
| `app/api/routes/voice_ws.py` | voice.route 改为直接调 VoiceController，不再创建 route_task |
| `app/core/channel/output/voice_channel.py` | ChatRAGText 交互代替原有 TTS push，保留 TokenEvent 流式逻辑 |
| `app/api/routes/models.py` | 恢复 kokoro 删除？— 已在之前步骤完成 |

## 5. 前端改动清单

### 5.1 核心变化

前端当前直接调用 Rust Tauri 命令管理语音会话。新架构下，前端改为：
- **语音模式切换** → Python（通过控制 WS 中转）
- **状态监听** → Python → Rust → Tauri event → 前端（链路不变）
- **TTS 配置** → Python（不再调用 Rust `set_tts_engine` 等命令）

### 5.2 需要改动的文件

| 优先级 | 文件 | 改动内容 |
|--------|------|---------|
| **关键** | `hooks/useVoiceEvents.ts` | `start_voice_session` / `stop_voice_session` / `switch_voice_mode` 等 ~15 个 Tauri invoke 改为发 Python 指令；事件监听接口不变（`voice.state` 等仍通过 Tauri event 到达） |
| **关键** | `hooks/useTTS.ts` | `speak()` / `stop()` 从 Rust invoke 改为 Python TTS 调用；voice 定义和选择 UI 保留为 Python TTS 的配置 |
| **重要** | `hooks/useWakeWord.ts` | 唤醒词监听从 Rust 移到 Python |
| **重要** | `hooks/useTauriVoiceShortcut.ts` | 快捷键注册保留 Rust，但 `onPress` 回调改为触发 Python |
| **重要** | `components/Settings/VoiceControlSettings.tsx` | Seeduplex 配置保留；模型下载 / 唤醒词配置指向 Python |
| **重要** | `components/Settings/TTSSettings.tsx` | 去掉 `safeInvoke("set_tts_engine")` 等 Rust 调用，改为配置 Python TTS |
| **中等** | `stores/voiceStore.ts` | 状态模型可能随 Python 事件格式调整 |
| **中等** | `components/Settings/ModelManager.tsx` | 模型下载从 Rust 移到 Python |
| **中等** | `components/Chat/ChatInputArea.tsx` | 语音模式切换的 IPC 链改为指向 Python |
| **中等** | `components/Chat/TTSButton.tsx` | `speak()` 改为 Python 调用 |
| **中等** | `routes/voice-hud.tsx` | HUD 数据源不变（Tauri event），但事件内容可能微调 |
| **可能** | `hooks/useVoiceRecorder.ts` | 浏览器 MediaRecorder 可能被 Python mic 流替代 |
| **可能** | `utils/voiceStorage.ts` | 文件操作用 Rust invoke 指向 Python |

### 5.3 不需要改的文件

`ChatInputArea.tsx`（UI 按钮布局）、`VoiceMessage.tsx`、`VoiceMessageWithTranscript.tsx`、`SourcesFooter.tsx`、`UpgradePrompt.tsx`、路由文件、自动生成的 SDK/类型、locales（微调可能）

## 6. 实现步骤

### Step 1: 控制 WS 双向通信（Rust + Python）

- Rust 启动一个 local TCP WS server（或 client）
- Python 连接后收发 JSON 控制消息
- 验证：Rust 发 `start_voice` → Python 收，Python 发 `event` → Rust 收 → Tauri emit

### Step 2: Python Volcengine 对话客户端

- 基于 `realtime_dialog_client.py` 示例，嵌入 Agent 调用
- 实现：StartSession → Mic PCM → ASR → Event 459 → ChatRAGText → TTS → 播放
- 验证：运行脚本，说话，听到回复

### Step 3: Python Mic + VAD + 播放

- `pyaudio` 麦克风采集 + `silero-vad` VAD 打断检测
- `afplay` / `pyaudio` 播放 TTS PCM
- 验证：Mic 采集→PCM→播放（无须 Volcengine，先验证音频环）

### Step 4: 集成 VoiceController

- 整合 Step 2 + Step 3 → 完整链路
- 控制 WS 接收 Rust 的 start/stop/switch_mode
- 状态变化通过控制 WS → Rust → Tauri → 前端

### Step 5: 补 dictation_paste + screencapture

- Python 通过控制 WS `{"type": "paste", "text": "..."}` 触发 Rust 执行
- Python 通过控制 WS `{"type": "screencapture"}` 触发 Rust 执行

### Step 6: 清理 Rust 旧代码

- 删除 voice_session.rs、seeduplex_client.rs、tts_engine.rs 等
- 精简 lib.rs、mod.rs、ws_client.rs

## 6. 风险与缓解

### 6.1 麦克风权限：Python 进程可能拿不到授权
**风险**：macOS 对麦克风采集有沙盒权限控制。Python 脚本通过 pyaudio 调用 CoreAudio 时，macOS 可能弹窗显示的是 "Terminal.app" 而非本应用，或在 Tauri sidecar 场景下因无独立 Bundle ID 导致无声。

**缓解**：
- Tauri 的 `Info.plist` 保留 `NSMicrophoneUsageDescription` 声明
- Python 配置 `PLISTBUDDY` 或通过 `pyobjc` 设置进程级别的 Bundle ID
- 如果生产环境 sidecar 场景下失败，为 Python 进程创建独立的 `.app` wrapper 以持有授权

### 6.2 VAD 打断（Barge-in）响应速度
**风险**：用户随时可能打断 AI 说话。如果 Python 用 `subprocess.afplay` 播放 TTS，检测到 VAD 打断时需要能瞬间终止播放。`afplay` 不支持即时停止（kill 有延迟）。

**缓解**：
- 使用 `subprocess.Popen` 启动 afplay，VAD 打断时立即 `process.kill()` + `process.wait()`
- 更优方案：Python 使用 `pyaudio` 或 `sounddevice` 流式播放音频块，打断时直接清空输出缓冲区，实现毫秒级响应
- 两种方案可根据实际体验选择

### 6.3 粘贴逻辑与 Apple Event 权限
**风险**：方案提到 dictation_paste 可通过 pyobjc 在 Python 侧实现。但 macOS 上模拟全局粘贴需要 Accessibility 权限。若以 Python 进程持有，用户需在系统设置中单独为 Python 勾选授权，这在打包发布后极难配置。

**缓解**：
- **dictation_paste 保留在 Rust 侧**。Python 收到听写文本后，通过控制 WS 发送 `{"type": "paste", "text": "..."}` 给 Rust，由已获授权的 Tauri 进程执行模拟按键和粘贴。保证 100% 成功率。

### 6.4 其他风险

| 风险 | 缓解 |
|------|------|
| Python pyaudio 延迟不稳定（蓝牙耳机） | 提供 fallback 到 afplay 播放 WAV 文件 |
| silero-vad Python 包模型下载慢 | 复用已有模型文件 `~/.evoloop/models/silero_vad.onnx` |
| 控制 WS 断连导致状态不同步 | Rust 端定时心跳 + 重连机制 |
| macOS Python 没装在系统 PATH | 使用绝对路径 `/usr/bin/afplay` |

## 8. 对话模式语音链路（当前实现）

### 8.1 当前架构总览

```
┌─ Rust (Tauri) ─────────────────────────────────────────┐
│  Mic (CPAL) → PCM ──WS binary──→ Python                │
│                                                         │
│  WS client: 接收 voice.audio_frame → tts_buffer        │
│              800ms debounce → 写 WAV → afplay 播放      │
│                                                         │
│  接收 dictation.paste → dictation_paste()               │
│  接收 voice.barge_in → 清 buffer + 杀 afplay             │
└─────────────────────────────────────────────────────────┘
           ▲  WS binary (TTS PCM)    │  WS JSON (控制)
           │                         │
┌──────────┴─────────────────────────┴────────────────────┐
│ Python (FastAPI + asyncio)                              │
│                                                         │
│  voice_ws.py: WebSocket 入口                             │
│    voice.start  → 创建 VolcDialogClient                  │
│    voice.stop   → 关闭 VolcDialogClient                  │
│                                                         │
│  dialogue_receive_loop: Volcengine 事件循环               │
│    Event 451 (ASR partial) → voice.partial → Rust HUD   │
│    Event 450 (barge-in)    → voice.barge_in → Rust      │
│    Event 459 (ASR done)    → run_agent_pipeline         │
│    Event 359 (TTS ended)   → state → LISTENING          │
│    Event 350 (injected TTS)→ voice.barge_in → Rust      │
│    SERVER_ACK(bytes)       → websocket.send_bytes → Rust │
│                                                         │
│  executor.py: 模块级全局变量                              │
│    active_volc_clients: dict[thread_id] → VolcDialogClient│
│    push_tts_text(thread_id, text)                        │
│      → active_volc_clients[thread_id].send_chat_tts_text()│
│                                                         │
│  volc_dialog.py: Volcengine 协议客户端                    │
│    connect() → StartSession                              │
│    send_audio(pcm) → TaskRequest (Event 200)             │
│    send_chat_tts_text() → ChatTTSText (Event 500)        │
│    receive_response() → 解析 Volcengine 响应              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 8.2 三种语音反馈

#### 8.2.1 确认语 — L0 匹配后即时反馈

```
来源: voice_input.py (_handle_builtin / _dispatch_macro)
时机: L0 命中后立即 (< 100ms)
内容: 简短固定话术 (2-10字)
例子: "好的"、"搞定了"、"已取消"

路径:
  voice_input.receive(text)
    → get_local_matcher().match(text) → L0 命中
      ├─ builtin → _handle_builtin()
      │   → _push_local_result("routed") → manager.push → UI
      │   → _maybe_push_tts(text) → push_tts_text → ChatTTSText → Volcengine
      │
      └─ macro → _dispatch_macro()
          → run_deterministic()
          → _push_macro_result("done", summary) → manager.push → UI
          → _maybe_push_tts(summary) → push_tts_text → ChatTTSText → Volcengine
```

#### 8.2.2 安抚话术 — Supervisor 首次回应

```
来源: VoiceChannel → MessageBlock(role=ai)
时机: Agent 启动后 ~1-2s
内容: Supervisor LLM 生成的首次回应
例子: "你好！我是你的通用 AI 助手..."

路径:
  Agent Supervisor 生成第一条回复
    → UniversalBridge → VoiceChannel.send(MessageBlock)
      ├─ streamed 去重
      ├─ _routed_texts 去重
      └─ push_voice_result("routed", summary)
           ├─ manager.push(VOICE_ROUTE_RESULT) → Rust → UI
           └─ push_tts_text(thread_id, summary) → ChatTTSText → Volcengine
```

#### 8.2.3 最终回复 — Agent 完成

```
来源: VoiceChannel → SessionCompletedEvent
时机: Agent 执行完成后 ~3-5s
内容: tts_summary（Agent 完整回复，为 TTS 优化）
例子: "项目代码质量评分 B+，主要问题在..."

路径:
  Agent 完成 → SessionCompletedEvent
    → VoiceChannel.send(payload)
      ├─ 取 tts_summary（无则 data.summary 首句）
      ├─ streamed_text 去重
      └─ push_voice_result("done", final_text)
           ├─ manager.push(VOICE_ROUTE_RESULT) → Rust → UI
           └─ push_tts_text(thread_id, final_text) → ChatTTSText → Volcengine
```

### 8.3 三条路径汇合

三条路径最终都走到 `push_tts_text`：

```
① 确认语 ────→ _maybe_push_tts
② 安抚话术 ──→ push_voice_result("routed")
③ 最终回复 ──→ push_voice_result("done")
                    │
              push_tts_text(thread_id, text)
                    │
              active_volc_clients[thread_id]
                    │
              volc_client.send_chat_tts_text()
                    │
              dialogue_receive_loop ← SERVER_ACK(bytes)
                    │
              websocket.send_bytes → Rust afplay
```

### 8.4 关键时序问题

#### 8.4.1 自动回复盖过安抚话术

```
Event 459 (ASR 完成)
  │
  ├─ 0ms: Volcengine 自动 LLM + TTS 开始
  ├─ ~200ms: 自动 TTS 音频 → SERVER_ACK → Rust afplay（用户已听到错误回复）
  │
  ├─ ~1-2s: Supervisor 生成第一条回复 (MessageBlock)
  │         → push_tts_text → ChatTTSText
  │         → Event 350 → voice.barge_in → 杀 afplay
  │         → 新 TTS 开始（用户听到安抚话术，但已听过错误开头）
  │
  └─ ~3-5s: Agent 完成 → push_voice_result("done")
            → ChatTTSText → 最终回复
```

**问题**：用户每次都会先听到 ~1s 的 Volcengine 自动回复，才被安抚话术覆盖。

#### 8.4.2 测试验证后的最终时序方案

经 `test_discard_auto.py` 测试验证，以下方案有效：

```
Event 459
  ├─ discard_tts = True       ← 丢弃所有自动 TTS 音频 ✅
  ├─ ChatTTSText(占位话术)     ← start=True, end=False，用户听到占位
  ├─ ChatTTSText(关闭占位)     ← start=False, end=True，关闭占位流
  │
  ├─ Agent 完成 → push_tts_text
  │   → ChatTTSText(Agent回复) ← start=True, end=True
  │
  ├─ Event 350(type="chat_tts_text")  ← 测试确认触发 ✅
  │   → voice.barge_in → Rust 清旧音频 + 杀 afplay
  │   → discard_tts = False   ← 开始转发新 TTS
  │
  └─ SERVER_ACK(新 TTS) × N → websocket.send_bytes → Rust afplay
      Event 359 → state → LISTENING
```

**测试结果**：

| 指标 | 结果 |
|------|------|
| Event 459 后丢弃的自动 TTS | 0b（完全阻止 ✅）|
| Agent 回复后的新 TTS | 400KB ✅ |
| Event 350(type="chat_tts_text") 触发 | ✅ |
| Event 359（TTS 正常结束） | 2 次 ✅ |

**关键发现**：
1. 占位 ChatTTSText 成功阻止了 Volcengine 自动回复的音频播放
2. Agent 回复的 `ChatTTSText(start=True, end=True)` **会产生 Event 350(type="chat_tts_text")**
3. Event 350(type="chat_tts_text") 可以作为切换音频的精确信号

#### 8.4.3 实现要点

```python
# 1. Event 459 后立即设置 discard 标志并发送占位
if event == 459:
    discard_tts = True
    volc_client.send_chat_tts_text(start=True, end=False, content="让我查一下。")
    volc_client.send_chat_tts_text(start=False, end=True, content="")
    asyncio.create_task(run_agent_pipeline(websocket, thread_id, asr_text))

# 2. Agent 完成 → push_tts_text → ChatTTSText(start=True, end=True)
#    在 executor.py 中完成，无需改动

# 3. 收到 Event 350(type="chat_tts_text") → 清旧音频 + 接受新 TTS
if event == 350 and isinstance(payload, dict):
    if payload.get("tts_type") in ("chat_tts_text", "external_rag"):
        voice.barge_in → Rust
        discard_tts = False

# 4. SERVER_ACK 处理：根据 discard_tts 决定是否转发
if mtype == "SERVER_ACK" and isinstance(payload, bytes):
    if discard_tts:
        continue  # 丢弃自动 TTS
    await websocket.send_bytes(payload)  # 转发新 TTS
```

### 8.5 其余已知问题

| # | 问题 | 影响 | 优先级 |
|---|------|------|--------|
| 1 | `active_volc_clients` 模块级 dict 无锁 | 并发 race | 中 |
| 2 | `push_voice_result` 对话模式下 manager.push 多余 | 无用 WS 流量 | 低 |
| 3 | 切换 mode 关旧 client 重建导致 PCM 丢包几百 ms | 首字听不到 | 中 |
| 4 | ChatRAGText 未实现（Event 502） | 无法注入 Agent 上下文 | 未来 |
