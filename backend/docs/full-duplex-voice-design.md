# 全双工近实时语音对话设计方案

## 1. 背景与问题 — ✅ 已完成

当前语音链路是"薄客户端 + 文本中继"模式：Tauri Rust 原生层完成 ASR/TTS/VAD，Python 后端（与 Tauri 打包为同一桌面应用，以本地子进程/服务运行）只处理文本 `voice.route` 和 `voice.route_result`。

> 部署说明：Python 后端不是独立部署服务器，而是与 Tauri 打包成整体桌面应用。WebSocket 走 `127.0.0.1` 环回，属于同一机器内进程间通信（IPC），不存在公网延迟和多实例部署问题。

本设计参考 `evoloop-voice-buddy/` 的 VLA（车机式分层语音助理）架构：

- **Layer 0**：**确定性匹配**——L0 模板 + 确定性 Macro，不进 LLM，不查向量，< 50ms；
- **Layer 1**：**快速执行**——确定性 Macro 直执行，非确定性由 LLM 路由后走 Agent 图；
- **Layer 2**：**Agent 兜底**——处理复杂多步任务；
- **听写模式**：客户端本地 LLM 对 ASR 文本做润色、纠错，再粘贴到当前输入焦点；
- **对话模式**：连续语音对话，支持打断、委派、异步结果回推。

该模式能满足基础语音指令，但存在以下限制：

- **非真全双工**：用户必须等机器说完才能发新指令，打断依赖客户端自己停止 TTS，无法利用后端语义做中断。
- **延迟天花板明显**：客户端先录完一整句，再 ASR，再发文本，后端路由执行后返回完整文本，客户端再 TTS 播放，链路完全串行。
- **后端无法感知语音状态**：不知道用户什么时候开始说、什么时候停、是否在机器说话时插话。
- **无流式输出**：LLM 生成完整回复后才返回，TTS 等完整文本才开始合成，无法边生成边播报。
- **现有代码中的隐患（均已修复）**：
  - `VoiceConnectionManager` 是进程内内存结构，无断线重连、多实例不共享（单桌面应用可接受）。
  - `voice.cancel` 曾只是打日志，现已加入 `register_voice_task` 真实取消。
  - ~~`execute_many` 用 `asyncio.create_task` 后无注册~~ — **已删除**，Agent 任务由 `VoiceTaskRegistry` 管理。
  - 同一线程加锁：`asyncio.Lock` 保证同一 thread 同一时刻只有一个"听→处理→说"循环。
  - `/api/v1/audio/transcribe-stream` 返回 501。
  - 无鉴权，仅依赖环回限制。

## 2. 设计目标 — ✅ 已完成

### 2.1 核心体验目标

1. **有情感式的对话交流**——Agent 不只是执行指令，而是像人一样自然地说话。语气、节奏、内容由 LLM 控制，不预设、不套路。语音通道禁止生硬的模板回复，Agent 知道自己在和一个人说话。

2. **全双工语音交流**——TTS 播放时麦克风同时录制（AEC 消除回音），用户随时可以插话。Rust VAD 检测到用户说话 → 停 TTS → 发 barge-in → Python 取消当前 Agent → 进入下一轮。用户不需要等机器说完。

3. **能即时响应的交流**——用户说话后 500ms-2s 内要让用户知道 Agent 收到了。L0 匹配的指令（音量、截图等）< 50ms 播确认语。L0 未命中的交给 Agent：Supervisor 判断能否直接回答，若能则回复结果并立即 TTS 播报；若需要长时间执行则告知用户并派 Worker——确认语由 LLM 根据上下文生成（如"这个问题我需要查一下资料"），不是预设模板。用户听到的是 Agent 在对用户说话。

4. **能判断什么时候该向用户说明或汇报**——Agent 自主决定要不要汇报、什么时候汇报、汇报多少。不需要汇报的不打扰。需要长时间执行时先告知再动手。完成后 1 句话通知结果。复杂结果引导去电脑上查看。这由 Supervisor 提示词的语音行为规则约束，但判断由 LLM 根据上下文自主决定。

5. **能边听边播的交流**——Rust 原生层实现 AEC 消除回音，麦克风持续录制。Agent 播放 TTS 的同时，用户可以随时开口说话，VAD 识别到后立即打断。全双工在 Rust 原生层完成，不依赖 Python 后端响应速度。

### 2.2 架构目标

- Tauri Rust 原生层负责实时语音全链路：麦克风采集、AEC、VAD、ASR、TTS 播放。
- Python 后端负责认知与执行：只接收文本，做路由、执行、状态管理，结果通过 Channel 抽象层回推。
- 语音不是独立的路由管道，而是 Agent 的一个输入/输出通道。语音和文字共享同一份对话历史、同一套 Agent 图、同一个上下文。
- 播什么、什么时候播，完全由 Agent 决定。VoiceChannel 只是传声筒，不预设回复内容。
- 服务端维护语音会话状态机（由 Tauri 信令驱动）。
- 修复现有连接管理、取消、并发等问题。

## 3. 两种工作模式 — ✅ 已完成

参考 `evoloop-voice-buddy/` 的交互设计，语音助理支持两种工作模式。两种模式共享同一套文本控制信令通道，但状态机和后端交互方式不同。

### 3.1 对话模式（Dialogue Mode）

- **触发方式**：长按 F12（或等价触发）进入连续对话。
- **核心链路**：ASR → L0 匹配 → Agent 图（Supervisor 直接回答或派 Worker）。
- **全双工要求**：
  - Tauri 持续录制麦克风（AEC 消除扬声器回声）；
  - Python LLM token 流式输出，Tauri 边收边 TTS；
  - 用户可以在 TTS 播放过程中直接插话；
  - Tauri VAD 检测到用户说话 → 停止 TTS → 发 `voice.barge_in` → Python 取消 LLM 生成和执行；
  - 打断后立即切换到新一轮 ASR → 路由 → 执行。
- **本地 Layer 0 优先**：后端 `LocalMatcher` 先匹配 L0 模板和确定性 Macro，命中即本地执行，不走 Agent 图；未命中才进入 Agent。
- **异步回推**：Macro / Agent 执行结果通过 `voice.token` 流式 + `voice.route_result` 终态回推到客户端，客户端边收边 TTS 播报。

### 3.2 听写模式（Dictation Mode）

- **触发方式**：短按 F12 进入听写模式。
- **核心目标**：把用户语音快速转成文字，并经过本地 LLM 润色、纠错后，粘贴到当前输入焦点（类似 macOS 听写，但带 LLM 后处理）。
- **处理链路**：

  ```text
  用户说话 → Tauri Rust 层流式 ASR（Sherpa-ONNX） → 原始文本
                ↓
         本地 LLM（Qwen3-4B via LM Studio，流式输出）
                ↓
         润色 + 纠错后的文本
                ↓
         模拟 Cmd+V 粘贴到当前焦点
  ```

- **本地 LLM 润色/纠错**：
  - Tauri Rust 层直接调 LM Studio（`127.0.0.1:1234`，`stream=true`），流式接收润色后的 token；
  - 对 ASR 识别错误、口语化重复、语气词进行纠错和润色；
  - 保持用户原意，不擅自扩展内容；
  - 支持中英文混合输入；
  - LLM 输出也用流式，Tauri 边收边显示在输入框（可选）。
- **与后端的关系**：
  - 听写模式**默认不走 Python 后端**，Tauri Rust 层直接调 LM Studio 完成润色；
  - 若用户开启"云听写"或需要后端更大模型润色，可通过 WebSocket 发送 `voice.dictation` 信令，后端返回润色文本；
  - 后端提供可选的 `POST /api/v1/voice/dictation` 端点（或 `voice.dictation` WebSocket 信令）做云端 LLM 润色降级。
- **状态机**：听写模式没有 `speaking` 阶段，只有 `listening → processing → idle`，TTS 可选（仅在有错误需要提示时播放）。

## 4. 非目标 — ✅ 已完成

- 不在后端实现语音采集和播放硬件控制（仍由 Tauri Rust 原生层负责麦克风/扬声器）。
- 不替代移动端现有 `MobileChannel` 文本通道；本设计先聚焦桌面端语音流。
- 不替换现有文本路由逻辑，只扩展流式输出和状态机。
- 不引入端到端语音大模型（如 GPT-4o Realtime）；仍使用流式 ASR + 文本路由 + 流式 LLM + 流式 TTS 四段式架构。
- 不解决多实例部署问题；本设计面向 Tauri + Python 单桌面应用，进程内状态即可满足。如需多设备同步，另行设计。
- 不引入复杂鉴权；WebSocket 仅绑定 `127.0.0.1`，属于同机可信子进程通信。
- **不删除文件级音频处理能力**：聊天消息上传的音频、录屏技能合成时的音轨，仍由 Python 后端 `POST /api/v1/audio/transcribe` 处理。本设计仅把实时语音流的 ASR/TTS 移到 Tauri Rust 原生层。

## 5. 总体架构 — ✅ 已完成

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Tauri 桌面应用（Rust + React）                              │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Tauri React UI 层（packages/desktop/，仅负责界面渲染）                   │  │
│  │  ├─ 设置界面：语音设置、模式选择、VAD/AEC 参数                            │  │
│  │  ├─ 聊天界面：流式 token 显示、打断 UI 反馈                               │  │
│  │  └─ 状态指示：listening / processing / speaking                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ▲ Tauri IPC / Events                     │
│                                    │                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Tauri Rust 原生层（src-tauri/，负责所有音频和语音处理）                   │  │
│  │                                                                       │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────────┐        │  │
│  │  │  麦克风  │→│   AEC   │→│  VAD    │→│ 缓存音频到断句      │        │  │
│  │  │ (持续)  │  │ (回声消除)│  │(800ms)  │  │  → Qwen3-ASR 离线  │        │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └────────┬─────────┘        │  │
│  │                                                   │                   │  │
│  │            ┌──────────────────────────────────────┤                   │  │
│  │            │ VAD 断句 → voice.route                │                   │  │
│  │            │ barge_in → voice.barge_in             │                   │  │
│  │            └──────────────────────────────────────┤                   │  │
│  │                                                   ▼                   │  │
│  │  ┌─────────────────────────────────────────────────────────────┐     │  │
│  │  │            Rust WebSocket 客户端（→ Python 127.0.0.1）         │     │  │
│  │  │  voice.route / voice.barge_in / voice.dictation.finalize     │     │  │
│  │  │  ◄ voice.token / voice.tts_boundary / voice.route_result    │     │  │
│  │  │  ◄ system.init / system.config_changed                      │     │  │
│  │  └─────────────────────────────────────────────────────────────┘     │  │
│  │                                                   │                   │  │
│  │            ┌──────────────────────────────────────┤                   │  │
│  │            │ voice.token / voice.tts_boundary       │                   │  │
│  │            └──────────────────────────────────────┤                   │  │
│  │                                                   ▼                   │  │
│  │  ┌─────────────────────────────────────────────────────────────┐     │  │
│  │  │            TtsEngine (Rust) + afplay                          │     │  │
│  │  │  Edge-TTS / Qwen-TTS                                           │     │  │
│  │  └─────────────────────────────────────────────────────────────┘     │  │
│  │                                                   │                   │  │
│  │                                                   ▼                   │  │
│  │                                  ┌──────────────────────────────┐    │  │
│  │                                  │   扬声器 ◄── 同时麦克风仍在录  │    │  │
│  │                                  └──────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              │ 文本控制信令（voice.*）+ token 流
                              ▼
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Python 后端（本地子进程）                             │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         语音状态机                                   │  │
│   │  idle / listening / processing / speaking / interrupted             │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                       │
│              ┌─────────────────────┴─────────────────────┐                 │
 │              ▼                                           ▼                 │
 │   ┌──────────────────────────────────────────────────────────────────┐      │
 │   │  voice.route 路由                                                │      │
 │   │  (L0 → Agent 快速路径，跳过 LLM 路由)                              │      │
│                                              └──────────┬──────────┘      │
│                                                         │                 │
│                                                         ▼                 │
│                                          ┌──────────────────────────┐      │
│                                          │ 流式 LLM 输出             │      │
│                                          │ (deepseek-chat via       │      │
│                                          │  EvoLoop Gateway)        │      │
│                                          │ → voice.token 推送        │      │
│                                          │ → 句子边界 voice.tts_boundary│   │
│                                          └──────────┬──────────┘      │
│                                                     │                 │
│                                                     ▼                 │
│                                          ┌──────────────────────────┐      │
│                                          │ Macro / Agent           │      │
│                                          │ 执行（异步，结果流式回推）  │      │
│                                          └──────────────────────────┘      │
│                                                                             │
│   文件级音频处理（保留）：                                                   │
│   ┌─────────────────┐        ┌─────────────────┐        ┌─────────────┐    │
│   │ 聊天音频消息     │   →    │ 录屏音轨         │   →    │ audio/transcribe│ │
│   └─────────────────┘        └─────────────────┘        └─────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 架构说明

**两级 LLM 策略**（由 `LIGHTNING_MODE` 系统配置控制）：

| 模式 | Supervisor 模型 | Worker/Finish 模型 | 首 token 延迟 |
|------|---------------|-------------------|-------------|
| `none`（默认） | 云端 deepseek-chat | 云端 deepseek-chat | ~2s |
| `lm-studio`（闪电） | 本地 Qwen3-4B | 云端 deepseek-chat | ~500ms |

语音链路的完整流程：

```
voice.route → L0 检查
  → 未命中 → dispatch_agent_run(metadata={"source": "voice"})
    → Supervisor
      ├── LIGHTNING_MODE=none → supervisor.prompt.j2 + 云端 LLM
      └── LIGHTNING_MODE=lm-studio → supervisor_lightning.prompt.j2 + 本地 LLM
      │
      ├── 直接回答 → 自发布 SessionCompletedEvent
      │   → VoiceChannel → TTS（1-2 句）
      │
      └── route_to(worker) → Worker（云端 LLM）
          → Finish（云端 LLM）→ SessionCompletedEvent
          → VoiceChannel → TTS（tts_summary）
```

闪电模式下 Supervisor 用本地模型快速响应，复杂任务路由到 Worker 时仍由云端模型保证质量。详见 `docs/two-tier-llm-strategy.md`。

- **Tauri Rust 原生层负责所有音频和语音处理**：麦克风持续采集、AEC 回声消除、VAD 快速端点检测、流式 ASR、流式 TTS 播放、听写 LLM 调用。这些功能在 Rust 层实现，通过 FFI 调用 Sherpa-ONNX 等原生库，不在 React/JS 层运行。
- **Tauri React UI 层仅负责界面渲染**：设置界面、聊天界面、状态指示。通过 Tauri IPC/Events 与 Rust 层通信。
- **Python 后端负责认知与执行**：接收 ASR 文本，做路由、流式 LLM 输出、执行、状态管理，token 流式回推。
- **全双工实现关键**：
  - Tauri Rust 层播放 TTS 时麦克风仍在录制（AEC 消除回声）；
  - Python LLM token 流式输出，Tauri Rust 层收到句子边界就开始下一句 TTS；
  - 用户说话时 Tauri Rust 层 VAD 检测 → 立即停止 TTS → 通知 Python 取消生成。
- **Python 后端仍保留文件级音频处理**：聊天消息上传的音频文件、录屏技能合成时的音轨，通过 `POST /api/v1/audio/transcribe` 转写，不走实时语音通道。
- Tauri Rust 层与 Python 之间的 WebSocket 只传输**文本控制信令和 token 流**，正常路径下语音不出 Tauri。

## 6. 模型与技术选型 — 🟡 部分实现

### 6.1 ASR（Tauri Rust 原生层，离线整段识别）

> ⚠️ **设计变更**：原设计使用流式 Paraformer，现改为 Qwen3-ASR 离线整段识别（VAD 断句后识别整段音频）。流式 Paraformer 已移除。

| 模型 | 说明 | 延迟 |
|------|------|------|
| **Qwen3-ASR via sherpa-onnx** | 离线整段识别，VAD 断句后触发，准确率高于流式模型 | VAD 静音 800ms + 识别 ~500ms |
| ~~Sherpa-ONNX streaming paraformer~~ | ❌ 已移除 | — |

**统一 ASR**：对话和听写模式共用 Qwen3-ASR 离线识别，不再区分流式/离线两条路径。

### 6.2 LLM（流式输出）

| 模型 | 部署 | 流式支持 | 用途 |
|---|---|---|---|
| **deepseek-chat** | EvoLoop Gateway（`https://evoloop.cn/gateway/v1`） | ✅ token 流式 | Agent 图对话生成 + 推理 |
| **Qwen3-4B-Instruct-2507** | LM Studio（`127.0.0.1:1234`，OpenAI 兼容） | ✅ token 流式 | 听写润色（Tauri Rust 直连） |

**选型**：
- Agent 图（Supervisor/Worker/Finish）的 LLM 调用走 **EvoLoop Gateway**，模型为 `deepseek-chat`。
- 本地 Qwen3-4B-Instruct-2507 via LM Studio 只用于**听写模式**的本地润色——Tauri Rust 层通过 HTTP 直接调 LM Studio 本地接口（`127.0.0.1:1234`），流式接收 token，不经过 Python 后端。
- 旧路由系统（macro/skill 分类）的快速分类使用 `LightningService`，由 `LIGHTNING_MODE` 配置决定后端（当前为 `lm-studio`）。
- ~~Gemma-4 E4B~~：已测试，效果不好，弃用。

**关键**：LLM 必须支持 `stream=true`（OpenAI 兼容 API）。Python 收到 token 立即通过 WS 推送 `voice.token`，不等完整回复。Tauri 听写模式直接调 LM Studio，不经过 Python。

### 6.3 TTS（Tauri Rust 原生层 + Python 后端）

TTS 统一由火山引擎实时对话 API 合成，无引擎分裂问题。

### 6.4 VAD（Tauri Rust 原生层，快速端点检测）

| 方案 | 端点延迟 | 说明 |
|------|---------|------|
| **Silero VAD** | 100-300ms | ONNX 模型，Rust `sherpa-onnx` 加载，silence 800ms，max_speech 30s |
| ~~Sherpa-ONNX VAD~~ | — | ❌ 改用 Silero VAD |

**选型**：Silero VAD（sherpa-onnx 内置支持），静音阈值 800ms，最长语音 30s。VAD 在 Tauri Rust 层运行。

### 6.5 Embedding（Python 端，路由检索）

| 模型 | 维度 | 用途 |
|---|---|---|
| **bge-base-zh-v1.5** | 768 | 向量检索（LanceDB route_index） |

**选型**：沿用现有 bge-base-zh-v1.5。

### 6.6 技术栈总结

```text
Tauri Rust 原生层（src-tauri/）：
  ASR     → Qwen3-ASR via sherpa-onnx（离线整段识别，VAD 断句触发）
  VAD     → Silero VAD via sherpa-onnx（silence 800ms，max_speech 30s）
  AEC     → macOS VoiceProcessingIO AudioUnit（系统级回声消除）
  TTS     → 火山引擎实时对话 API（Python 侧）
  WS 客户端 → Rust WebSocket 连接 Python 后端

Tauri React UI 层（packages/desktop/）：
  设置界面 → 语音设置、模式选择、VAD/AEC 参数配置
  聊天界面 → 流式 token 显示、打断 UI 反馈
  状态显示 → listening / processing / speaking 状态指示

Python 后端（本地子进程）：
  路由LLM → deepseek-chat（EvoLoop Gateway，stream=true，`https://evoloop.cn/gateway/v1`）
  TTS 提供者 → 火山引擎实时对话 API
  Lightning → 本地 LM Studio Qwen3-4B（旧路由快速分类，由 LIGHTNING_MODE 控制）
  Embedding → bge-base-zh-v1.5
  检索    → LanceDB route_index
  通信    → WebSocket 127.0.0.1（文本信令 + token 流）
```

### 6.7 TTS 引擎实现（旧设计，仅供参考）

#### 6.7.1 三引擎架构

原设计使用三个 TTS 引擎（已扩展为五个，见 §6.3）。保留仅作参考。

```rust
pub enum TtsEngineKind {
    EdgeTts,   // 微软 Edge TTS（msedge-tts crate）
    QwenTts,   // 通义千问 TTS-Flash
}
```

#### 6.7.2 AVSpeechSynthesizer

- 调用 `say -v Ting-Ting -r 200 <text>` 直接播报
- 中文：`Ting-Ting` 音色，英文：`Samantha` 音色
- 延迟：< 100ms，离线可用

#### 6.7.3 Edge-TTS

- `msedge-tts` Rust crate → 微软 Edge TTS 服务 → WAV → `afplay`
- 中文音色：`zh-CN-XiaoxiaoNeural`、`zh-CN-YunxiNeural` 等
- 延迟：200-400ms，需联网

#### 6.7.4 Qwen-TTS-Flash

- HTTP API → 阿里云 DashScope → WAV → `afplay`
- 需要配置 API Key
- 延迟：300-600ms，需联网

#### 6.7.5 前端设置

在 `TTSSettings.tsx` 中增加 TTS 引擎选择下拉框：System / Edge TTS / Qwen TTS。通过 `invoke("set_tts_engine", { engine })` 持久化。

#### 6.7.6 Cargo.toml 依赖

```toml
msedge-tts = "0.4.0"
reqwest = { version = "0.12", features = ["json"] }
```

## 7. 协议设计 — ✅ 已完成

### 7.1 WebSocket 升级

- 保留现有 `ws://.../voice/ws` 路径。
- 主路径：Tauri Rust 原生层完成流式 ASR 后，通过 **文本控制信令 + token 流** 与 Python 后端交互。
- 所有信令均为 JSON 文本帧，正常路径不传输二进制语音。

### 7.2 信令总览

| 信令 | 方向 | 处理 |
|---|---|---|
| `voice.route` | Tauri→Python | ASR 最终文本，触发路由 + 执行 |
| `voice.route` | Tauri→Python | ASR 最终文本，触发路由 + 执行（优先用预加载缓存） |
| `voice.barge_in` | Tauri→Python | 打断：取消当前任务，状态→interrupted |
| `voice.cancel` | Tauri→Python | 取消执行，状态→idle |
| `voice.start` | Tauri→Python | 语音会话开始，状态→listening |
| `voice.stop` | Tauri→Python | 语音会话结束，listening→idle |
| `voice.dictation.finalize` | Tauri→Python | 听写云端 LLM 润色降级请求 |
| `voice.route_result` | Python→Tauri | 路由决策（即时）/ 执行完成 done / 执行失败 failed |
| `voice.token` | Python→Tauri | LLM token 流式推送（逐 token） |
| `voice.tts_boundary` | Python→Tauri | 句子边界信号（Tauri 立即触发 TTS 合成） |
| `voice.dictation.polished` | Python→Tauri | 听写润色结果 |

### 7.3 信令定义

```json
// ─── Tauri → Python：ASR 最终文本，触发路由 ───
{
  "type": "voice.route",
  "body": { "text": "今天天气怎么样", "thread_id": "...", "message_id": "..." }
}

// ─── Tauri → Python：打断（用户在 TTS 播放时说话）───
{
  "type": "voice.barge_in",
  "body": { "thread_id": "..." }
}

// ─── Tauri → Python：取消指定 thread 的执行 ───
{
  "type": "voice.cancel",
  "body": { "thread_id": "..." }
}

// ─── Python → Tauri：路由决策（即时）───
{
  "type": "voice.route_result",
  "body": {
    "thread_id": "...",
    "status": "routed",
    "target": { "type": "skill", "id": 12, "name": "..." },
    "params": {},
    "candidates": []
  }
}

// ─── Python → Tauri：LLM token 流（流式输出）───
// 每生成一个 token 就推送，Tauri 累积到句子边界就触发 TTS
{
  "type": "voice.token",
  "body": { "thread_id": "...", "token": "今天", "index": 0 }
}

// ─── Python → Tauri：句子边界（可开始 TTS）───
// LLM 输出到 。！？\n 等边界时发送，Tauri 立即对该句启动 TTS
{
  "type": "voice.tts_boundary",
  "body": { "thread_id": "...", "sentence": "今天天气不错。", "index": 0 }
}

// ─── Python → Tauri：生成/执行完成（终态）───
{
  "type": "voice.route_result",
  "body": { "thread_id": "...", "status": "done", "summary": "..." }
}

// ─── Python → Tauri：生成/执行失败（终态）───
{
  "type": "voice.route_result",
  "body": { "thread_id": "...", "status": "failed", "summary": "..." }
}

// ─── 听写模式（可选云端降级）───
// Tauri → Python
{
  "type": "voice.dictation.finalize",
  "body": { "raw_text": "今天的天气真不错啊", "target_locale": "zh" }
}
// Python → Tauri
{
  "type": "voice.dictation.polished",
  "body": { "polished_text": "今天天气真不错。", "changes": [] }
}
```

### 7.4 流式 LLM → TTS 时序

```text
Python LLM (stream=true):
  token: 今   → voice.token {token:"今"}
  token: 天   → voice.token {token:"天"}
  token: 天气  → voice.token {token:"天气"}
  token: 不错 → voice.token {token:"不错"}
  token: 。   → voice.token {token:"。"}
              → voice.tts_boundary {sentence:"今天天气不错。"}
  token: 明天  → voice.token {token:"明天"}
  ...

Tauri:
  收到 voice.tts_boundary → 立即对该句启动 TTS → 扬声器播放
  同时继续接收后续 voice.token → 累积下一句
  播放第1句的同时，正在合成第2句 ← 全双工重叠
```

## 8. 服务端状态机 — ✅ 已完成

每个 `thread_id` 维护一个状态机：

```text
idle ──voice.route──► processing
listening ──voice.route (final)──► processing
processing ──route_result + 无动作──► idle
processing ──route_result + 需执行──► speaking
speaking ──voice.token 流式 + tts_boundary──► speaking (持续)
speaking ──route_result(done) + 无排队──► idle
speaking ──voice.barge_in──► interrupted
interrupted ──cancel complete──► listening
```

### 8.1 状态说明

- `idle`：等待用户说话。
- `processing`：执行路由决策。
- `processing`：收到 final transcript，执行路由决策。
- `speaking`：LLM token 流式输出中，Tauri 在播放 TTS。此时 Python 仍在生成 token，Tauri 麦克风仍在录制（AEC 消除回声）。
- `interrupted`：用户打断，Python 正在取消 LLM 生成和执行，准备重新进入 listening。

### 8.2 全双工关键

- `speaking` 状态下，Python 持续推 `voice.token`，Tauri 持续播放 TTS + 录制麦克风。
- 用户说话时，Tauri VAD 检测 → 发 `voice.barge_in` → Python 停止生成 → Tauri 停止 TTS → 进入 `interrupted` → 新一轮 `listening`。
- 这实现了"机器说话时用户可以随时插话"的全双工体验。

### 8.3 听写模式状态机

听写模式不经过 `speaking` 状态，也没有 `interrupted`（不打断），其状态机简化为：

```text
idle ──voice.dictation.start──► listening
listening ──VAD silence──► processing
processing ──dictation.polished──► idle
```

- Tauri Rust 层直接调 LM Studio 完成润色时，不占用后端状态机。
- 仅当 Tauri 请求云端润色时，后端进入上述状态机。

## 9. 关键模块变更 — 🟡 部分实现（清理项未完成）

> 功能模块已完成。死代码清理状态：`router.py`（已清理）、`decompose.py`（✅ 已删除）、`route_cache.py`（✅ 已删除，但测试文件残留 `tests/unit/core/routing/test_route_cache.py` 需手动清理）、`retriever.py preheat`（仍被 `voice_ws.py` 调用但实际无意义——离线 ASR 无增量结果）。

### 9.1 WebSocket 层 (`app/api/routes/voice_ws.py`)

- 新增信令分支：
  - `voice.barge_in` / `voice.cancel` → 取消 LLM 生成和执行任务。
  - `voice.dictation.finalize` → 听写云端润色。
- `voice.route` 处理改为流式：路由决策后，LLM 用 `stream=true` 生成，逐 token 推送 `voice.token`，遇到句子边界推送 `voice.tts_boundary`。
- 将 `voice.cancel` 从日志改为真正取消：`task.cancel()` 已注册的执行 task + LLM 生成 task。
- 同一线程加锁：`asyncio.Lock` 保证同一 thread 同一时刻只有一个"听→处理→说"循环。

### 9.2 流式 LLM 输出 (`app/core/routing/executor.py`)

- 新增 `stream_llm_response(thread_id, prompt)`：
  - 调用 LLMFactory（路由专用实例）`stream=True`。
  - 逐 token 通过 `manager.push()` 发送 `voice.token`。
  - 检测句子边界（`。！？.!?\n`）发送 `voice.tts_boundary`。
  - 完成后发送 `voice.route_result(done)`。
- 新增 `VoiceTaskRegistry`：
  - 记录每个 `thread_id` 当前正在执行的 Agent task。
  - 支持 `cancel_voice_task(thread_id)`：取消执行任务。
  - Agent task 启动时注册，完成/异常时自动注销。
  - Agent 后台任务通过 `_voice_registry` + `thread_lock` 确保线程安全。
- 任务异常通过 `try/except` 捕获并推送 `voice.route_result(failed)`。

### 9.3 连接管理 (`app/core/routing/connection.py`)

- 部署模型为单桌面应用（Tauri + Python 本地子进程），进程内 `dict` 即可满足连接映射：
  - `thread_id → conn_id` 映射。
  - 终端结果 / token 流进度。
- 断线重连不必要：WebSocket 走 `127.0.0.1` 环回，不存在网络断开；后端重启后进程重建，连接映射自然为空，用户重新 F12 即可开始新会话。
- 发送失败清理不必要：`try/except WebSocketDisconnect` 在读取循环中已清理连接映射；本地 IPC 下发送失败窗口极短（毫秒级）。
- 无需 Redis，也无需跨实例共享。

### 9.4 流式 ASR（可选降级，`app/infrastructure/voice/stt/`）

- 实时语音流的 ASR 由 Tauri Rust 原生层完成（Sherpa-ONNX streaming）。
- Python 后端仍保留 `app/infrastructure/voice/stt/` 用于**文件级音频转写**：
  - `POST /api/v1/audio/transcribe`：聊天消息上传的音频文件、录屏技能合成时的音轨等。
  - 文件级转写接入 FunASR / Whisper / Aliyun SenseVoice 等 provider。
- 如果 Tauri 端 ASR 不可用，可临时降级为把语音流打到 Python 后端，但这不是主要路径。

### 9.5 流式 TTS（可选降级，`app/infrastructure/voice/tts/`）

- 实时语音流的 TTS 由 Tauri Rust 原生层完成（AVSpeechSynthesizer / Edge-TTS 流式）。
- Python 后端仍保留 `app/infrastructure/voice/tts/` 用于**文件级语音合成**：
  - `POST /api/v1/audio/tts`：把长文本合成音频文件后返回 URL。
- 如果 Tauri 端 TTS 不可用，可临时降级为 Python 后端流式 TTS，但同样不是主要路径。

### 9.6 VAD（Tauri 端）

- Tauri 端实现 VAD，不在 Python 后端：
  - Sherpa-ONNX VAD（与 ASR 复用框架）。
  - silence duration 调到 300-500ms。
- 用于：
  - 判断一句话结束（触发 `voice.route`）。
  - 判断用户是否在 TTS 播放时说话（触发 `voice.barge_in`）。

### 9.7 语音流降级网关（可选，`app/infrastructure/voice/stream_gateway.py`）

- 当 Tauri 端 ASR/TTS 不可用时，Python 后端接管语音流处理。
- 抽象 `VoiceStreamSession`：管理上传/下发语音缓冲区、chunk 排序。
- 提供 `VoiceStreamSessionManager`：按 `session_id` 存取会话。
- 正常路径下该模块不启用。

### 9.8 听写模式后端模块 (`app/core/voice/dictation.py`)

- 提供云端听写润色降级能力：
  - `POST /api/v1/voice/dictation`：接收 `raw_text` 和 `target_locale`，返回 `polished_text`。
  - 内部调用 LLM（复用现有 `LLMFactory` 的路由专用实例，`stream=true`）。
  - 使用 `evoloop-voice-buddy/prompts/dictation.md` 等价提示词，保持与本地润色逻辑一致。
- 润色规则：
  - 纠正 ASR 同音/近音错误；
  - 去除口语化重复、语气词；
  - 保持标点自然，不扩展原意；
  - 支持中英文混合。
- 输出 `changes` 字段，便于客户端展示修改对比（可选 UI）。
- 默认推荐 Tauri Rust 层直接调 LM Studio 完成听写润色，云端端点仅作为 LM Studio 不可用时的 fallback。

## 10. 语音对话架构重构（v2） — ✅ 已完成

### 10.1 原架构的问题

原设计将语音视为独立的路由管道：`voice.route` → 检索 → LLM 路由 → macro/agent 执行 → `voice.route_result`。这导致：

- **语音指令和文字对话各走一套系统**，Agent 没有语音会话的上下文
- **每轮语音指令互相独立**，用户说「帮我查一下项目 A」→ 查完了，再说「再看看项目 B」→ Agent 不知道上一轮说了什么
- **用户在语音中问「刚才那个结果呢」**，Agent 无法回答，因为它不记得之前那个异步任务
- **本质上和智能音箱一样**，说完就忘，没有持续对话

### 10.2 新架构：语音是 Agent 的一个通道

```
┌────────────────────────────────────────┐
│           Agent 对话系统                │
│                                        │
│  聊天界面 (文字)  ←────────────→  Agent 图│
│                                        │
│  语音通道 (语音)  ←────────────→  Agent 图│
│                                        │
│  共享同一份对话历史                      │
│  共享 Agent 状态和上下文                 │
└────────────────────────────────────────┘
```

**核心变化**：语音不再是独立的路由系统，而是 Agent 的一个输入/输出通道。用户通过语音说话，等同于在聊天界面发了一条消息。

### 10.3 语音分流架构

```
                用户语音
                    │
                    ▼
          ┌──────────────────┐
          │  L0 本地匹配      │  L0 模板 + 确定性 Macro，< 50ms
          │  (LocalMatcher)   │  < 50ms
          └────┬──────┬──────┘
               │      │
          命中  │      │ 未命中
               │      ▼
               │    ┌──────────────────┐
               │    │  进入 Agent 图    │
               │    │                  │
               │    │  Supervisor      │
               │    │  (单层 ReAct)    │
               │    │                  │
               │    │  ├─ 直接回答      │
               │    │  │  自发布事件    │
               │    │  │  TTS 播报     │
               │    │  │  < 500ms      │
               │    │  │               │
               │    │  └─ route_to     │
               │    │    (worker)      │
               │    │    → Worker      │
               │    │    → Finish 审计  │
               │    │    3-10s         │
               │    └──────────────────┘
               │
               ▼
         ┌──────────┐
         │ 本地执行   │  L0 命中
         │ TTS 确认  │  < 50ms
         └──────────┘
```

**L0 命中**：走 `LocalMatcher` 匹配 L0 硬编码模板 + 确定性 Macro，本地执行后 TTS 确认，延迟 < 50ms。

**L0 未命中**：直接进入 Agent 图。Supervisor 作为单层 ReAct 节点：
- **能直接回答的**（问候、知识问答、简单任务）：回复后自发布 `SessionCompletedEvent`，不走 Worker/Finish，1 次 LLM 调用
- **需要复杂执行的**（写代码、分析项目）：`route_to(worker)` → Worker 执行 → Finish 审计，3 次 LLM 调用

### 10.4 对话流程

```
1. 用户 F12 进入对话模式
2. 用户说「分析项目 A 的代码结构」
3. ASR → Layer 0 检测（未命中）→ 发消息给 Agent
4. Agent 收到：「用户说：分析项目 A 的代码结构」
   Agent 看历史（可能是空或已有上下文）
   Agent 开始 Supervisor → Worker → ... → 执行工具 → 生成回复
5. Agent 回复文本 → TTS 播报（若是直接回答则播报回答内容；若是派 Worker 则播放 Supervisor 说的确认语）
6. Agent 长任务（如分析代码需要几分钟）：
   → Supervisor 根据语音行为规则告诉用户需要时间（如"这个问题需要查一下，请稍等"）
   → TTS 播报确认语
   → Agent 后台继续跑（Worker 执行 + Finish 审计）
   → Worker 执行过程中产生的 AI/TOOL/SYSTEM 消息落库、推 SSE 显示在聊天界面，但不会被 TTS 朗诵
   → 完成后 SessionCompletedEvent 推语音消息 → TTS 播报短摘要（tts_summary）
   → 完成后推消息到对话历史
   → 语音收到通知 → TTS「分析结果已出，请在电脑上查看」
7. 用户继续说「再看看项目 B」
   → Agent 看到历史中有「项目 A」，知道现在问的是「项目 B」
   → 正常回复

用户也可以在聊天界面打字问：
  「项目 A 分析得怎么样了？」
  Agent 看到完整历史，知道项目 A 的分析任务，可以回答
```

### 10.5 Agent 长任务通知

语音只做简短通知，不播报 Agent 的长篇回复。播报内容由 LLM 根据语音行为规则生成，不是预设模板：

| 阶段 | 语音行为 |
|------|---------|
| Supervisor 直接回答 | TTS 播报回答内容 |
| Supervisor 认为需要派 Worker | TTS 播报确认语（如"这个问题需要查一下，请稍等"） |
| Agent 执行中（Worker） | 不打扰用户。Worker 产出的 AI/TOOL/SYSTEM 消息落库并推送到聊天界面，但不 TTS 朗诵 |
| Agent 完成后（Finish） | TTS 播报短摘要（tts_summary，如"分析结果已出，请在电脑上查看"） |
| 用户问「结果呢」 | Agent 看历史回答 |

### 10.6 实现变更

| 组件 | 变更 |
|------|------|
| **前端** | F12 循环切换模式、听写持续监听、语音日志 toast |
| **后端** | L0 未命中 → 直接 `dispatch_agent_run`，不走 LLM 路由 |
| **后端** | Agent 完成后 `VoiceChannel` 推结果 → TTS |
| **后端** | 删 `VoiceResultSubscriber`，改由 `VoiceChannel` 通过 channel 架构接收事件 |
| **后端** | `voice_ws.py` 不再硬编码 routed 推送，由 Supervisor AI 消息自然下发 |
| **Backend** | `finish.prompt.j2` 去掉 `is_voice`，始终生成完整报告 |
| **Rust** | Supervisor 直接回答：`voice.route_result {done}` 时 TTS 播报 summary（即 tts_summary） |
| **Rust** | Supervisor route_to Worker：`voice.route_result {routed}` 时 TTS 播报确认语 |
| **Rust** | Finish 完成后：`voice.route_result {done}` 时 TTS 播报 tts_summary |
| **Rust** | L0 命中时按 action 播确认语音（已静音/已截图等） |
| **Rust** | TTS 三引擎（System/Edge-TTS/Qwen-TTS），前端设置可切换 |

### 10.7 新信令

无需新增信令。VoiceChannel 通过已有 `voice.route_result` 推送 Agent 完成结果。

### 10.8 Layer 0 位置确认

Layer 0（`LocalMatcher`）放后端 `router.py`，不放客户端。原因：
- 匹配模板来自后端（已安装 App、Macro 列表等），同步到客户端的复杂度超过收益
- Tauri + Python 同机 IPC 延迟 ~1ms，不存在「占用后端资源」问题
- 后端 50+ 模板 + 拼音容错 + 模糊匹配已可用
- 未来如需离线场景，可考虑将模板子集编译到 Rust，但目前不必要

### 10.9 会话管理

#### 10.9.1 thread_id 策略

- 用户 F12 进入对话模式时，Rust 侧生成一个固定 `thread_id`（如 `voice-{device_id}`），**整个语音对话周期内不变**
- 所有语音轮次（包括被 Layer 0/1 快速处理的）共用同一个 `thread_id`
- 退出对话模式（F12 再按）时，`thread_id` 废弃，下次进入重新生成

#### 10.9.2 Agent 会话

- `voice.route` 中需走 Agent 时，**复用已有的会话线程**（通过 `thread_id` 关联），而不是每次新建
- Agent 图看到的是累积的对话历史（包括文字聊天记录和之前的语音轮次）
- 这和聊天界面打字走的是同一个 Agent 实例，共享上下文

#### 10.9.3 语音专用行为指令

语音行为规则在两个 Supervisor 模板中分别注入：

| 模板 | 路径 | 使用场景 |
|------|------|---------|
| `supervisor.prompt.j2` | 标准 | 默认 Agent 图（云端模型） |
| `supervisor_lightning.prompt.j2` | 轻量 | 闪电模式（本地模型） |

两个模板的语音规则逻辑一致：简短回复、禁 markdown、长任务先确认、完成后一句话通知、复杂结果引导看屏幕。轻量模板额外包含本地模型自知规则（不确定时 route_to worker）。

```
{% if is_voice %}
- 回复控制在 1-2 句话，简短自然，像真人对话
- 禁止使用 markdown、代码块、列表、表格——语音无法渲染
- 需要长时间执行的任务，立即回复「好的，我来处理」并开始执行
- 执行完成后回复 1 句话简短通知结果
- 复杂结果引导用户去电脑上查看，不在语音中详述
- 用户可能在说话过程中停顿（ASR 断句），这是正常的，不要打断用户
{% endif %}
```

这个段通过 `PromptAssemblyBuilder.add_section("voice_behavior", ...)` 在 `source="voice"` 时注入到最终 system prompt 末尾，对所有节点生效。

### 10.10 详细对话流程（时序）

由 `VoiceChannel`（`app/core/channel/voice_channel.py`）桥接 Agent→语音：

#### 10.10.1 语音链路

```
Rust 原生层                         Python 后端
────────────                       ──────────

用户说话
  │
  ▼
麦克风 → AEC → VAD → 缓存音频
                              VAD 断句 → Qwen3-ASR 离线识别
                              voice.route ──────► voice_ws._handle_route
                              {text, thread_id}      │
                                                      ├── L0 命中（< 50ms）
                                                      │     → voice.route_result {local, action}
                                                      │     → Rust 播确认语（已静音/已截图/好的）
                                                      │
                                                      └── L0 未命中
                                                            → dispatch_agent_run
                                                              metadata={"source": "voice"}
                                                            → run_agent_background
                                                              ctx.metadata.source = "voice"
                                                            → Agent 图执行
                                                              │
                                                              │ LLM: EvoLoop Gateway
                                                              │ deepseek-chat
                                                              │
                                                        Supervisor（第 1 次 LLM 调用）
                                                           │
                                                           ├── 直接回答
                                                           │   → SessionCompletedEvent
                                                           │   → VoiceChannel → push_voice_result(done, tts_summary)
                                                           │   → WS voice.route_result {done, summary: tts_summary}
                                                           │   → Rust 收到 → TTS 播报 tts_summary
                                                           │
                                                           └── route_to(worker)
                                                               → AI 消息（由 LLM 生成确认语，非预设模板，
                                                                  如"这个问题需要查一下资料，请稍等"）
                                                               → MessagePublisher
                                                                 ├── 落库 + 同步移动端
                                                                 ├── WebChannel → SSE（聊天 UI）
                                                                 └── VoiceChannel
                                                                       → push_voice_result(routed, summary)
                                                                       → WS voice.route_result
                                                                       → Rust 收到 → TTS 播报确认语
                                                               │
                                                               ▼
                                                         Worker 执行（云端 LLM）
                                                           │
                                                           ├── AI/TOOL/SYSTEM 消息
                                                           │   → 落库（对话历史）
                                                           │   → SSE 推送到聊天界面
                                                           │   → 同步移动端
                                                           │   → 不 TTS 朗诵（Worker 干活不打扰用户）
                                                           │
                                                           └── LLM 流式 token → TokenEvent → SSE 仅
                                                               （不进 VoiceChannel，不触发 TTS）
                                                               │
                                                               ▼
                                                         Finish 审计（第 2 次 LLM 调用）
                                                           │
                                                           ├── AI 消息 → 落库 + 同步移动端 + SSE
                                                           └── SessionCompletedEvent → system_bus
                                                               → VoiceChannel
                                                                 → push_voice_tts_boundary(tts_summary)
                                                                 → push_voice_result(done, tts_summary)
                                                                 → WS voice.route_result {done}
                                                                 → Rust 收到 → TTS 播报 tts_summary

用户可在任何时刻说话：
  VAD 检测 → 停 TTS → voice.barge_in ──────► cancel_voice_task → 新一轮
```

#### 10.10.2 L0 快反链路

L0 是语音最快响应路径，不进 Agent 图，< 50ms 完成。基于 `LocalMatcher` 匹配引擎，5 条规则，17 种本地动作。

##### L0 完整流程

```
ASR 文本 → Rust voice.route {text, thread_id, message_id}
  → Python _handle_route()
    ├── 幂等检查 → 重复 message_id 返回缓存结果
    ├── 抢话检测 → 如 TTS 播放中，取消当前任务
    ├── 绑定 thread → connection
    ├── 状态 → PROCESSING
    │
    ├── L0 匹配 ← _get_local_matcher().match(text)
    │   init_spec.py:43-107 → 50+ 模板，最长字面优先
    │   local_matcher.py:90-218 → 5 条规则匹配引擎
    │
    │   命中：
    │     → voice.route_result {status: "routed", target: {type: "local", action, params}}
    │     → WS → Rust voice_session.rs
    │       → handle_route_result(status="routed", target="local")
    │       → resolve_confirmation(action, lang) ← 泛化确认语池
    │       → TTS 播报（好的/搞定了/嗯哼/OK/Got it/Done 等）
    │     → 状态 → IDLE
    │     → 总计: < 50ms
    │
    │   未命中：
    │     → 走 Agent 图（见 §14.10 时序）
    │     → dispatch_agent_run(metadata={"source": "voice"})
```

##### LocalMatcher 匹配引擎（5 条规则）

| 规则 | 说明 | 代码 |
|------|------|------|
| 1. **锚定结构匹配** | 整段话必须完全匹配模板（去掉礼貌前后缀后），声明式句子含触发词不匹配 | `local_matcher.py:110` |
| 2. **最长字面优先** | 模板按字面长度降序排列，"取消静音" 优先于 "静音" | `local_matcher.py:114` |
| 3. **槽位验证** | 带 `{app}`/`{delta}`/`{key}` 的模板需通过字典验证 | `local_matcher.py:139-206` |
| 4. **拼音容错** | App 名拼音等值匹配（同音字距离 0），使用频率排行做平局裁决 | `local_matcher.py:171-185` |
| 5. **拉丁编辑距离** | ASCII app 名（≥4字符）允许编辑距离 ≤1 | `local_matcher.py:187-190` |

##### 17 种 L0 动作

| 动作 | 参数 | 说明 |
|------|------|------|
| `play_pause` | — | 播放/暂停 |
| `next_track` | — | 下一首 |
| `prev_track` | — | 上一首 |
| `set_volume` | `{delta: "+10"/"-10"/"100"/...}` | 音量调节 |
| `mute` | — | 静音 |
| `unmute` | — | 取消静音 |
| `open_app` | `{app: "Safari"}` | 打开 App |
| `focus_app` | `{app: "WeChat"}` | 切换到 App |
| `quit_app` | `{app: "Xcode"}` | 退出 App |
| `press_key` | `{key: "Return"/"Space"/"Up"/...}` | 按键模拟 |
| `screenshot` | — | 截图 |
| `lock_screen` | — | 锁屏 |
| `end` | — | 结束对话 |
| `clarify` | — | 请用户重复 |
| `rename` | `{name: "..."}` | 改名 |
| `paste` | — | 粘贴 |
| `speak` | — | 语音播报 |

##### 槽位验证

**app 槽位**（5 级匹配）：
1. 去掉尾缀噪音（浏览器/软件/App）
2. 精确名称/别名匹配
3. 全局别名映射（微信 → WeChat）
4. 拼音等值匹配，使用频率排行做 tiebreak
5. 拉丁名编辑距离 ≤1

**delta/key 槽位**（字典精确/子串匹配）：
- `key` 字典：回车→Return、空格→Space、删除→Delete、Tab、上/下/左/右...
- `delta` 字典：大一点→+10、小一点→-10、最大→100、一半→50、最小→0...
- 子串匹配时检查剩余字符是否仅为填充词（防止"把音量大一点再静音"误匹配）

##### RouteCatalog 生命周期

L0 模板和字典数据通过 `RouteCatalog` 下发：

```
build_init_spec()                    ← init_spec.py:282
  → _probe_apps()                    ← 扫描已安装 App + 拼音
  → enrich_spec_with_atlas_aliases() ← Atlas 菜单位置别名补充
  → cache.set("voice:init_spec:...") ← 写入 Redis 缓存
  → 重建周期：启动 / 每 6h / 按需
  → GET /route/init                  ← 客户端拉取（版本检查）
```

##### 确认语

确认语不再绑定具体 action（如"已静音"/"已截图"），改为**泛化确认语池**，按语言随机分配：

| 语言 | 确认语池 |
|------|---------|
| 中文 | 好的、搞定了、嗯哼、没问题、好嘞、收到、可以了、行、OK、没问题了 |
| 英文 | OK、Got it、Done、Sure、Alright、No problem、Gotcha、All set、Done deal、Easy |

同一 action 始终返回同一短语（通过 action 字符串哈希取模），不同 action 自然不同。切换前端语言后确认语自动跟随。

##### 关键文件

| 文件 | 职责 |
|------|------|
| `init_spec.py:43-107` | 50+ 模板定义 |
| `init_spec.py:109-141` | 槽位字典（app/key/delta）|
| `init_spec.py:282-322` | `build_init_spec()` 构建 |
| `local_matcher.py:90-218` | 匹配引擎（5 条规则）|
| `router.py:17-33` | `_get_local_matcher()` 工厂 |
| `voice_ws.py:133-178` | L0 命中/未命中处理 |
| `connection.py:78-93` | WS 推送 |
| `voice_session.rs:592-600` | `resolve_confirmation()` 确认语 |

#### 10.10.3 关键时间点

| 节点 | 耗时 | 说明 |
|------|------|------|
| WS 连接 | ~10ms | |
| L0 检查 | < 1ms | 50+ 正则模板 |
| 首个 LLM token | ~2s | deepseek-chat via EvoLoop Gateway（本地闪电模型 ~500ms） |
| 首句 TTS (TTFB) | ~2s | 用户听到第一次回应 |
| Agent 完成 | ~2.2s | |
| 完整播报结束 | +TTS 合成播放时间 | Edge-TTS ~3-5s/句 |

#### 10.10.4 语音链路特点

- **Agent 图使用 EvoLoop Gateway（model=deepseek-chat）**，不走本地 LM Studio
- 本地 LM Studio（qwen3-4b）仅用于：听写模式本地润色（Tauri Rust 直连）、旧路由系统快速分类（`_create_route_llm`）
- 如需让语音 Agent 走本地 LM Studio，需改造 `dispatch_agent_run` 在 `source="voice"` 时传 `model="qwen3-4b-instruct-2507"` + `base_url="http://127.0.0.1:1234/v1"`
- **VoiceChannel 逐 token 流式接收**，检测到句子边界（。！？）后立即推 TTS
- **推 TTS 前 strip 掉 markdown 符号**（`**`、`` ` ``、`#`、`>` 等），防止被 TTS 念出来
- **TTS**：火山引擎实时对话 API
- **VoiceChannel 去重**：已通过 token 流播过的内容，`SessionCompletedEvent` 不再重复播

#### 10.10.5 文字链路

```
用户打字 → POST /chat
            │
       dispatch_agent_run(metadata={})  ← 无 source
            │
       run_agent_background
            │
       ctx.metadata.source = ""  ← 覆盖残留
            │
       Agent 图执行（与语音路径完全相同）
            │
       AI 消息 → MessagePublisher
         ├── WebChannel → SSE → 聊天 UI
         ├── MobileChannel → 移动端推送
         └── VoiceChannel → _voice_registry 无此 thread → 跳过
            │
       SessionCompletedEvent
         → UniversalBridgeSubscriber
           ├── WebChannel → SSE（完整报告）
           └── VoiceChannel → source != "voice" → 跳过
```

#### 10.10.6 核心差异

| 维度 | 语音 | 文字 |
|------|------|------|
| 入口 | WS `voice_ws.py` | HTTP `_chat.py` |
| LLM 模型 | deepseek-chat（EvoLoop Gateway）；本地闪电模型可选 | 同左 |
| ctx.metadata.source | `"voice"` | `""` |
| Supervisor 提示词 | 追加语音规则（1-2 句、禁 markdown） | 标准 |
| Finish 报告 | 完整（VoiceChannel 取摘要 + strip markdown） | 完整（全部显示） |
| 输出通道 | WebChannel + VoiceChannel | 仅 WebChannel |
| Token 流 | ✅ VoiceChannel 累积 → 句子边界 → TTS | ❌ 不需要 |
| 输出格式 | 纯文本（strip markdown） | 完整 markdown |

#### 10.10.7 已清理的死代码

| 组件 | 原因 |
|------|------|
| `VoiceResultSubscriber` | 被 VoiceChannel（channel 架构）替代 |
| `execute_many` | 多意图编排被 Agent LLM 替代 |
| `route_many` | 同上 |
| `resolver.py` | 唯一下游 `execute_many` 已删 |
| `_DUPLICATE_ROUTE_CACHE` | 冗余优化 |
| `peek_voice` | 零生产调用者 |
| `chat` 节点 | 合并到 Supervisor |

```
Rust                      Python 后端
 │                          │
 │  voice.start ───────────►│ 创建/恢复 session
 │  (使用固定 thread_id)    │  和聊天界面共用同一个 thread_id
 │                          │
 │  Layer 0（快速指令）：     │
 │  voice.route ───────────►│ voice_ws._handle_route
 │                          │   → LocalMatcher 匹配
 │                          │   → 命中: push L0 结果 + TTS 确认
 │  ◄── voice.route_result  │   → 未命中: dispatch_agent_run → Agent 图
 │                           │
 │  Agent 对话：              │
 │  (L0 未命中后自动进入)      │
 │                          │
 │  ◄── voice.route_result  │  Agent 产生 AI 消息 → MessagePublisher
 │      {routed, "好的…"}    │   → VoiceChannel 推 routed + 内容
 │      TTS 播报             │   (Supervisor 决定派 Worker 时的即时回应)
 │                          │
 │  ◄── voice.route_result  │  Agent 完成 → SessionCompletedEvent
 │      {done, "结果…"}      │   → VoiceChannel 推 done + 摘要
 │      TTS 播报最终结果      │
 │                          │
 │  voice.stop ────────────►│ 结束语音会话
 │                          │
```

#### 10.10.8 关键变化

| 步骤 | 旧架构 | 新架构 |
|------|--------|--------|
| Agent 对话的 thread_id | 每次随机生成 | **和聊天共用固定 thread_id**，共享上下文 |
| Agent 如何拉起 | `execute_many` → `_run_agent`，无上下文 | `dispatch_agent_run` → `run_agent_background`，复用对话历史 |
| Agent 结果如何回到语音 | `VoiceResultSubscriber` → `push_voice_result(summary)` | **VoiceChannel**（channel 架构）→ `push_voice_result` |
| 首次即时响应 | `voice_ws.py` 硬编码推 `{routed, agent}` | ✂️ **已移除**，改由 Supervisor 的 AI 消息通过 MessageBlock → VoiceChannel 推 TTS |
| Finish 报告长度 | `{% if is_voice %}` 截断为 1-2 句 | ✂️ **已移除**，Finish 始终生成完整审计报告；VoiceChannel 只推 summary 给 TTS |

### 10.11 Agent 到语音的输出

Agent 的回复通过 `VoiceChannel`（`app/core/channel/voice_channel.py`）回到语音：

```
Agent 产生 AI 消息 (role=ai, content=..., tool_calls=...)
  → DatabaseCallbackHandler.on_llm_end()
    → MessagePublisher.publish(MessageBlock, channels={"sse", ...})
      → UniversalBridgeSubscriber
        → channel_registry.select({"sse", "voice"}, ...)
          → WebChannel.send() → SSE → 聊天 UI（完整内容）
          → VoiceChannel.send() → push_voice_result(thread_id, "routed", content)
            → WS voice.route_result {status:"routed", content:"..."}
            → Rust TTS 播报

Agent 完成（直接回答或 Worker+Finish）
  → SessionCompletedEvent / AgentRunCompletedEvent
    → 同上 UniversalBridgeSubscriber
      → VoiceChannel.send() → push_voice_result(done/failed, summary)
        → WS voice.route_result {status:"done", summary:"..."}
        → Rust TTS 播报最终结果
```

**VoiceChannel 的过滤规则**（`send()` 方法）：
- `MessageBlock(role=ai, content=...)` → 推 `{routed, content}`（播报 Agent 自然语言回复）
- `SessionCompletedEvent(source=voice)` → 推 `{done, summary}`（最终结果摘要）
- `AgentRunCompletedEvent(source=voice, status=failed)` → 推 `{failed, summary}`（失败通知）
- `MessageBlock(role=tool)` → 忽略（中间工具调用，无自然语言内容）
- 同线程内只推第一条 AI 消息（`_ack_sent` 去重），`SessionCompletedEvent` 重置

**不再需要** `VoiceResultSubscriber`，已被 VoiceChannel 替代。路径更简洁：Agent → `MessagePublisher` → `VoiceChannel` → TTS。

**`voice_ws.py` 不再硬编码推 `{routed, agent}`** 作为即时回应。Agent 什么时候回、回什么，
由 Agent 自己决定——Supervisor 决定派 Worker 时，LLM 生成"好的，我来处理"作为 AI 消息自然下发。

**Finish 始终生成完整审计报告**，不再因 `is_voice` 截断。VoiceChannel 只取 `summary` 字段推 TTS，
`SessionCompletedData.summary` 由 Finish 节点或其 bypass 路径设置，语音和 Web 各取所需。

### 10.12 状态机更新

| 状态 | 转换 | 说明 |
|------|------|------|
| `listening` | → `processing` | VAD 端点检测到 |
| `processing` | → `speaking` | Layer 0/1 命中或 Agent 开始回复 |
| `speaking` | → `listening` | TTS 播报完成，继续聆听 |
| `speaking` | → `interrupted` | 用户打断（barge-in） |
| `interrupted` | → `listening` | 打断完成，重新聆听 |

相比旧设计无变化，状态机保持原样。

### 10.13 Barge-in 处理

用户打断时：

```
Rust VAD 检测到用户说话
  → 停止 TTS
  → voice.barge_in → Python
  → cancel_voice_task：取消正在执行的 Agent 任务
  → 状态 = interrupted
  → 新一轮 ASR → voice.route
```

和旧设计一致，无变化。

### 10.14 多轮对话

多轮对话的上下文由 Agent 的消息历史自然维护，无需额外代码。
- 第 1 轮：L0 未命中 → Agent（Supervisor 直接回答或 Worker+Finish）
- 第 2+ 轮：通过共享 `thread_id` 的消息历史获得完整上下文
- Agent 的 LLM 自带指代解析能力，理解「那明天呢」「它的价格」等追问
- `ContextTrimmer` 自动裁剪历史，防止 token 窗口溢出

每次 F12 进入对话模式，Rust 侧维持固定 `session_id`，Python 端不做额外状态管理。

### 10.15 单句多意图

用户一句话可能包含多个意图，如「打开微信然后给张三发消息说今晚吃饭」。

#### 10.15.1 多意图检测

现有的 `decompose.decompose(text)` 函数已经能拆分多意图文本（通过连接词检测 + LLM 确认），返回 `list[Intent]`。

```python
# decompose("打开微信然后给张三发消息说今晚吃饭")
# → [
#     Intent(text="打开微信", depends_on=None),
#     Intent(text="给张三发消息说今晚吃饭", depends_on=[0]),
#   ]
```

#### 10.15.2 多意图处理流程

```
L0 未命中
  → decompose（检查是否有多个意图）
  → 如果单意图：走 Agent（Supervisor 直接回答或 Worker+Finish）
  → 如果多意图：
      按顺序逐个处理每个意图
      每个意图独立走 L0 → Agent 流程
      前一个意图的输出可作为后一个意图的参数
      全部完成后 TTS 汇总通知
```

#### 10.15.3 示例

```
用户：「打开微信然后给张三发消息说今晚吃饭」
  → Intent 1: "打开微信"（L0 匹配 open_app → 本地执行）
  → Intent 2: "给张三发消息说今晚吃饭"（Agent 处理）
  → TTS「微信已打开，消息已发送」
```

#### 10.15.4 注意事项

- 多意图的 decompose 依赖连接词检测（「然后」「并且」「再」等），没有连接词的单句不会触发
- 如果第一个意图是 L0 快速指令但第二个需要 Agent，第一个立即执行，第二个走 Agent 流程
- 多意图执行时如果有任一失败，不影响已成功的意图（部分完成）

### 10.16 跨轮指代与状态查询

#### 10.16.1 跨轮指代

用户说「查一下张三的订单」，然后说「把它的价格改一下」。Agent 需要知道「它」=「张三的订单」。

当前方案的局限：
- Agent 的 LLM 调用能看到消息历史，理论上能理解指代
- 但如果两轮之间隔了很长时间，或者中间有其他指令干扰，LLM 可能丢失上下文

实现方式：多轮对话上下文（§14.14）维持后，Agent 自然能看到前一轮的实体，指代由 LLM 自身能力解决。

#### 10.16.2 状态查询

用户说「分析完了吗？」，需要检查之前发起的异步任务状态。

当前限制：
- 异步任务完成后结果已通过 VoiceChannel 推回，后续查询触发新的 Agent 执行

解决方案：
- 对于异步任务，缓存最后结果
- 用户状态查询时，先查缓存结果，有则直接回复
- 无则 Agent 重新分析

### 10.17 ASR 后处理（模糊输入清洗）

ASR 输出可能包含语气词、停顿和重复：「那个…帮我看看…呃…就是那个…分析一下…」。

处理方式：在 `voice_ws.py` 收到 `voice.route` 后，先做轻量文本清洗：

```python
import re
def clean_asr_text(text: str) -> str:
    # 去掉语气词
    text = re.sub(r'呃|啊|那个|这个|就是', '', text)
    # 去掉重复
    text = re.sub(r'([，。！？]){2,}', r'\1', text)
    # 去掉多余标点
    text = re.sub(r'[，。！？…]{2,}', '，', text)
    return text.strip()
```

这样喂给 LLM 和 Agent 的文本更干净，减少误解。

### 10.18 完整场景覆盖清单

| # | 场景 | 处理路径 | 云端延迟 | 本地延迟 | 说明 |
|---|------|---------|---------|---------|------|
| 1 | 快速指令（音量/暂停/截图） | L0 匹配 → 本地执行 → TTS 确认 | < 50ms | < 50ms | 不进 LLM |
| 2 | App 操作（打开/切换/关闭） | L0 匹配 → 本地执行 → TTS 确认 | < 50ms | < 50ms | 不进 LLM |
| 3 | 闲聊问候（你好/谢谢/再见） | L0 miss → Supervisor 直接回答 | ~2s | ~500ms | 简单回复，本地 4B 够用 |
| 4 | 知识问答（什么是X/1+1） | Supervisor 直接回答 | ~2s | ~500ms | 本地 4B 可能编造 |
| 5 | 简单任务（查天气/翻译） | Supervisor 直接回答（需工具调用） | ~2s | ~1s | 本地 4B 工具调用不可靠 |
| 6 | 复杂任务（写代码/分析） | Supervisor → Worker（云端）→ Finish | 3-10s | 3-10s | Worker 始终走云端 |
| 7 | 多轮对话（第 2 轮起） | Agent 消息历史 → Supervisor 自理解 | ~2s | ~1s | 本地 4B 长上下文弱 |
| 8 | 跨轮指代（「它的价格」） | Agent 消息历史 → Supervisor 解析 | ~2s | ~1s | 本地 4B 指代解析弱 |
| 9 | 异步长任务通知 | Worker → Finish → SessionCompletedEvent → VoiceChannel → TTS | 任务完成时 | 同左 | Supervisor 仅负责发起，不阻塞 |
| 10 | 状态查询（「完了吗」） | WorkerRegistry → Supervisor 判断 query/new → 返回状态 | ~2s | ~500ms | 不取消旧任务，Supervisor 直接回答 |
| 11 | 打断纠错（「不，换一个」） | barge-in → cancel → 新 route | < 200ms | < 200ms | 不依赖 LLM |
| 12 | 混合指令（「打开然后发消息」） | Supervisor 自行拆解 → route_to(worker) | ~2s + 执行 | ~2s + 执行 | 本地 4B 拆解能力弱，建议走云端 |
| 13 | 模糊输入（「呃…那个」） | Qwen3-ASR 输出 → Supervisor 抗干扰 | ~2s | ~500ms | ASR 已过滤语气词 |
| 14 | 退出/取消（「算了」「停」） | L0 end 匹配 → 结束会话 | < 100ms | < 100ms | 不进 LLM |

结论：本地 4B 能稳定覆盖的只有 **L0 快速指令 + 简单问候**。涉及工具调用、知识问答、多轮上下文、任务拆解的场景，4B 大概率需要 `route_to(worker)` 交给云端。闪电模式的价值在于快速响应简单请求，不是替代云端。

---

## 11. Agent 引擎重构：Supervisor 直接回答 — ✅ 已完成

### 11.1 当前架构的问题（改造前架构，已过时）

当前 Agent 引擎是 LangGraph 4 节点流水线，面向复杂任务设计，不适合轻量语音交互：

```text
用户输入
  │
  ▼
Supervisor（路由，不干活）
  ├─ route_to(chat) → Chat（对话）→ Finish（审计）
  └─ route_to(worker) → Worker（执行）→ Finish（审计）
```
> ❌ 上图已过时——此为改造前架构。Chat 节点已删除合并到 Supervisor，Supervisor 现支持直接回答不走路由。

即使是「你好」，也必须走完 **3 次 LLM 调用**（Supervisor + Chat + Finish），总延迟 5-6 秒。

### 11.2 改造后架构

```text
用户输入
  │
  ▼
Supervisor（单层 ReAct，能直接回答也能调 Worker）
  ├─ 直接回答（问候/知识/状态查询/简单的）
  │    → 自发布完成事件
  │    → WS voice.route_result {done, summary}
  │    → Rust TTS 播报
  │    → 1 次 LLM 调用，< 500ms
  │
  └─ route_to(worker) → Worker（执行）→ Finish（审计）
       → 3 次 LLM 调用，3-10s
       → 只对复杂任务触发
```

### 11.3 具体变更

#### 11.3.1 Supervisor 节点 (`nodes/supervisor.py`)

**变更：从「只路由」改为「能干活也能路由」。**

当前：
- Supervisor 的 prompt 要求它**必须**调 `route_to`，不能直接输出文本（第 56 行 `"You MUST call route_to for task delegation. Never output plain text"`）
- Supervisor 的 LLM 调用只产出路由决策，不产出回复文本

改造后：
- prompt 中删除「禁止直接回复」的限制，改为：
  ```
  You are an AI assistant. Handle user requests:
  1. Direct response in PLAIN TEXT: For greetings, thanks, simple Q&A, 
     status queries, cancellations, or any task you can answer without tools.
  2. route_to(target="worker", ...): For tasks needing file operations, 
     code execution, device control, or multi-step workflows.
  3. route_to(target="finish"): When the session is complete.
  ```
- 当 Supervisor 选择直接回答时：
  - `_run` 方法检测到回复文本（不是工具调用）→ 直接发布 `SessionCompletedEvent`
  - 不经过 Finish 节点
  - Supervisor 回复文本同时作为 `summary`
- 当 Supervisor 选择 `route_to(worker)` 时：
  - 现有 Worker → Finish 流程不变
  - worker 输出受 Finish 审计把关

```python
# 简化后的 _run 逻辑
class SupervisorNode(BaseAgentNode):
    async def _run(self, state, config):
        # 1. 加载精简 prompt
        # 2. 1 次 LLM 调用
        ai_msg = await llm.ainvoke(messages)
        
        if ai_msg.tool_calls 且包含 route_to(worker):
            # 走 Worker → Finish 路径
            state.next_node = RoutingTarget.WORKER
            return StateUpdate(messages=..., next_node=RoutingTarget.WORKER)
        else:
            # 直接回答：提取回复文本
            reply = ai_msg.content.strip()
            # 自发布完成事件（不走 Finish）
            await publish_session_completed(data=SessionCompletedData(
                thread_id=thread_id,
                summary=reply,
                outcome="completed",
                source="voice",
            ))
            return StateUpdate(messages=..., next_node=RoutingTarget.END)
```

#### 11.3.2 Chat 节点删除 (`nodes/chat.py`)

Chat 节点的能力合并到 Supervisor。Chat 节点的代码和 prompt 可以删除。

`RoutingTarget.CHAT` 从路由表中移除，`route_supervisor` 函数不再允许路由到 `chat`。

#### 11.3.3 Finish 节点 (`nodes/finish.py`)

**不变。** Finish 节点保持审计职能，但只对 Worker 路径触发。

Supervisor 直接回答时**不经过 Finish**，不走审计流程。

**移除** Supervisor 直接回答时的审计：当前代码中 Finish 的 `_run` 方法第 192 行调 `AuditService.execute()`，这个只有在 `next_node=FINISH` 时才执行。Supervisor 直接回答时 `next_node=END`，不会触发 Finish。

#### 11.3.4 路由 (`routers.py`)

- 移除 `RoutingTarget.CHAT`
- `route_supervisor` 简化：不再需要 `terminal_targets` 白名单判断
- 新增 `route_supervisor_direct`：Supervisor 直接回答后一律 `END`

#### 11.3.5 Agent 循环 (`loop.py`)

- 移除 `RoutingTarget.CHAT` 分支
- 循环逻辑不变，只是少一个可路由目标

#### 11.3.6 Supervisor prompt (`supervisor.prompt.j2`)

- 删除「禁止直接回复」的硬约束
- 改为允许直接回答 + 允许 route_to(worker)
- 保留语音行为规则注入（`source == "voice"` 时）
- prompt 长度从 ~68 行减到 ~40 行

#### 11.3.7 语音入口 (`voice_ws.py` `_handle_route`)

L0 未命中后，不再调 `router.route_many()` 做 LLM 路由，直接走 Agent 图：

```python
# L0 未命中
→ dispatch_agent_run(thread_id, text, metadata={"source": "voice"})
  → Agent 图：Supervisor 直接回答 或 Supervisor → Worker → Finish
  → Supervisor AI 消息 → MessagePublisher → VoiceChannel → push_voice_result(routed, content)
  → Supervisor 直接回答 → SessionCompletedEvent → VoiceChannel → push_voice_result(done, summary)
  → Worker → Finish → SessionCompletedEvent → VoiceChannel → push_voice_result(done, summary)
```

#### 11.3.8 文字聊天保持不动

`POST /chat` 端点和现有 Agent 路径不受影响。`router.py` 的 LLM 路由（macro/skill 选择）只用于文字聊天路径，不走语音。

### 11.4 改造后完整工作流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           用户输入                                           │
│                    ┌──────────────────┐                                     │
│                    │  语音 (voice_ws)  │    ┌──────────────┐                 │
│                    │  voice.route     │    │ 文字 (POST   │                 │
│                    └────────┬─────────┘    │   /chat)     │                 │
│                             │              └──────┬───────┘                 │
│                             ▼                     ▼                         │
│                    ┌──────────────────┐                                     │
│                    │    L0 匹配        │                                     │
│                    │  (LocalMatcher)  │                                     │
│                    └────┬──────┬──────┘                                     │
│                   命中   │      │ 未命中                                      │
│                         │      ▼                                            │
│                         │    ┌──────────────────┐                           │
│                         │    │   Voice 快速路径   │                          │
│                         │    │  (voice_ws.py)   │                           │
│                         │    └────────┬─────────┘                           │
│                         │             │                                     │
│                         ▼             ▼                                     │
│              ┌──────────────────┐                                           │
│              │  本地执行 +      │                                           │
│              │  TTS确认 < 50ms  │                                           │
│              └──────────────────┘                                           │
│                                                                            │
│              ┌──────────────────────────────────────────────────────┐       │
│              │              Agent 图（单层入口 Supervisor）           │       │
│              │                                                      │       │
│              │  ┌──────────────────────────────────────────────┐   │       │
│              │  │  Supervisor（改造后：单层 ReAct，能干活）         │   │       │
│              │  │                                              │   │       │
│              │  │  prompt：                                     │   │       │
│              │  │  1. Direct response → 直接回答，自发布事件     │   │       │
│              │  │  2. route_to(worker) → Worker → Finish       │   │       │
│              │  │  3. route_to(finish) → 结束                  │   │       │
│              │  │                                              │   │       │
│              │  │  工具：route_to, recall, remember, 等          │   │       │
│              │  └──────────┬───────────────────────────┬───────┘   │       │
│              │             │                           │           │       │
│              │             ▼                           ▼           │       │
│              │  ┌──────────────────┐      ┌──────────────────┐    │       │
│              │  │  直接回答          │      │  Worker 执行      │    │       │
│              │  │                   │      │                  │    │       │
│              │  │  LLM 1 次调用     │      │  LLM 1 次调用     │    │       │
│              │  │  输出回复文本       │      │  执行工具          │    │       │
│              │  │                   │      │  产出执行结果      │    │       │
│              │  └────────┬──────────┘      └────────┬─────────┘    │       │
│              │           │                          │              │       │
│              │           ▼                          ▼              │       │
│              │  ┌──────────────────┐      ┌──────────────────┐    │       │
              │              │  │  Supervisor       │      │  Finish 审计      │    │       │
              │              │  │  自发布事件        │      │                  │    │       │
              │              │  │                  │      │  LLM 1 次调用     │    │       │
              │              │  │  publish_session_ │      │  质量闸门          │    │       │
              │              │  │  completed()      │      │  产出 summary     │    │       │
              │              │  └────────┬──────────┘      └────────┬─────────┘    │       │
              │              │           │                          │              │       │
              │              └───────────┼──────────────────────────┼──────────────┘       │
              │                          │                          │                      │
              │                          ▼                          ▼                      │
              │              ┌─────────────────────────────────────────┐                  │
              │              │   VoiceChannel                              │                  │
              │              │   push_voice_result(done, summary)       │                  │
              │              └──────────────────┬──────────────────────┘                  │
              │                                 │                                          │
              │                                 ▼                                          │
              │              ┌─────────────────────────────────────────┐                  │
              │              │   WS voice.route_result {done, summary}   │                  │
              │              └──────────────────┬──────────────────────┘                  │
              │                                 │                                          │
              │                                 ▼                                          │
              │              ┌─────────────────────────────────────────┐                  │
              │              │   Rust TTS 播报 summary                    │                  │
              │              └─────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘

调用次数对照:

                Supervisor 直接回答               Supervisor → Worker → Finish
                ──────────────────────           ────────────────────────────
  LLM 调用:     1 次（Supervisor 回答）            3 次（Sup + Worker + Fin）
  TTS 反馈:    直接播报 summary                   播报 summary 或通知
  审计:        无                                有（Finish 质量闸门）
  适用场景:    问候/问答/状态查询/简单任务           写代码/分析/多步操作/不可信输出
  目标延迟:    ~500ms                             3-10s
```

### 11.5 延迟对照

| 场景 | 现在 | 改造后 | 提升 |
|------|------|--------|------|
| 你好 | 6s（Sup→Chat→Fin，3 次 LLM） | **~500ms**（Sup 直接回答，1 次 LLM） | 12x |
| 1+1等于几 | 3s | **~500ms** | 6x |
| 查天气 | 8s | **~500ms** + 工具调用（如需） | 16x |
| 写代码 | 9s | 9s（不变） | — |
| 多轮对话第 2 轮 | 6s | **~500ms** + 历史上下文 | 12x |

### 11.6 实施阶段

#### Phase A：Supervisor 改造 + Chat 删除（✅ 已完成）

| # | 文件 | 操作 | 状态 |
|---|------|------|------|
| 1 | `supervisor.prompt.j2` | 删除第 56 行「Never output plain text」约束；删除第 11 行 `route_to(target="chat")` 选项 | ✅ |
| 2 | `chat.prompt.j2` | 删除整个文件 | ✅ |
| 3 | `nodes/chat.py` | 删除整个文件 | ✅ |
| 4 | `nodes/prompts/chat_builder.py` | 删除整个文件 | ✅ |
| 5 | `nodes/prompts/__init__.py` | 移除 `ChatPromptBuilder` 导入和导出 | ✅ |
| 6 | `nodes/__init__.py` | 移除 `ChatNode` 导入和导出 | ✅ |
| 7 | `loop.py` | 移除 `ChatNode` 导入和实例化；移除 `RoutingTarget.CHAT` 分支 | ✅ |
| 8 | `routers.py` | 移除 `RoutingTarget.CHAT` 枚举值 | ✅ |
| 9 | `agent_main.yaml` | 移除 chat 节点定义和路由映射 | ✅ |
| 10 | `tools/orchestration/routing.py` | 更新 docstring | ✅ |
| 11 | `context_trimmer.py` | 从 `node_source` 类型中移除 `"chat"` | ✅ |
| 12 | `supervisor.py` | `_build_fallback_outcome` 中增加直接回答分支 | ✅ |
| 13 | `voice_ws.py` | L0 未命中→直接 dispatch_agent_run | ✅ |
| 14 | 测试文件 `test_chat_node.py` | 删除 | ✅ |
| 15 | 测试文件 `test_all_routing_paths.py` | 更新 | ✅ |
| 16 | 测试文件 `test_conversation_fixes.py` | 更新 | ✅ |
| 17 | 调试测试文件 | 保持不动 | ✅ |

#### Phase B：测试

1. 跑全量单元测试，验证文字聊天路径无回归
2. 跑语音 E2E 测试，验证各场景延迟
3. 验证多轮对话上下文

#### Phase C：持续优化

1. 优化 Supervisor prompt 长度，减少首次 LLM 调用延迟
2. 完善直接回答的场景覆盖

---

## 12. 当前实现状态 — ✅ 已完成

### 12.1 已实现的变更（代码就绪）

| 模块 | 变更 | 文件 |
|------|------|------|
| 语音入口 | L0 未命中 → 直接 Agent 快速路径（跳过 LLM 路由） | `voice_ws.py` |
| Agent 上下文 | `source=voice` 传入 Agent 上下文元数据 | `runner.py` |
| Supervisor 提示词 | `is_voice` 注入语音行为规则（标准模板 + 轻量模板） | `supervisor_builder.py`, `supervisor.prompt.j2`, `supervisor_lightning.prompt.j2` |
| Finish 提示词 | 始终生成完整审计报告（去掉 `is_voice` 分支） | `finish.prompt.j2`, `finish_builder.py` |
| 语音结果通道 | `VoiceChannel`（channel 架构）替代 `VoiceResultSubscriber` | `voice_channel.py`, `registry.py`, `bridge.py` |
| 即时响应 | 移除硬编码 routed 推送，改由 Supervisor AI 消息自然下发 | `voice_ws.py` |
| 事件 schema | `AgentRunCompletedEvent` 增加 `source` 字段 | `event/schemas.py` |
| 打断修复 | `register_voice_task` 挂到真实 Agent 任务 | `voice_ws.py` |
| 死代码清理 | 删 `execute_many`、`route_many`、`resolver.py`、`peek_voice` | `executor.py`, `router.py` |
| 性能打点 | 全链路计时日志（`voice-perf`） | `voice_ws.py`, `voice_channel.py` |
| VAD 参数 | 静音阈值 800ms → 400ms | `voice_session.rs` |
| 任务注册 | Agent task 注册后支持打断取消 | `executor.py`, `voice_ws.py` |
| Rust 事件总线 | 解耦，`VoiceEventBus` trait 替代 Tauri AppHandle | `voice/event.rs`, `voice_session.rs` |
| Rust TTS | 收到 routed/done/failed 时播对应语音 | `voice_session.rs` |
| ASR 端点 | 禁用 ASR 自身端点检测，改依赖 VAD | `asr_engine.rs`, `voice_session.rs` |
| 模型路径 | 搜索 ~/.evoloop/models + 原型路径 | `voice_session.rs` |
| 听写粘贴 | 全局 Cmd+V 粘贴（arboard + core-graphics） | `voice_session.rs` |
| 听写提示词 | 对齐原型 `dictation.md` 16 条规则 | `templates/core/voice/dictation.md` |
| 隐私权限 | macOS 麦克风权限声明 | `entitlements.plist` |
| 托盘状态 | 语音激活时托盘图标变蓝 + tooltip | `tray.rs`, `lib.rs` |
| 前端 | F12 循环切换模式、听写持续监听 | `ChatInputArea.tsx` |
| 前端 | 语音日志 toast 显示 | `useVoiceEvents.ts` |
| 前端 | TTS 引擎/音色/语速设置 | `TTSSettings.tsx`, `useTTS.ts` |
| 前端 | L0 确认语（泛化短语池，按语言分） | `voice_session.rs` |
| 设计文档 | 新增 §14（v2 架构）+ §15（Agent 改造） | `full-duplex-voice-design.md` |

### 12.2 验证确认

以下项经代码核查和实测验证，结论为**无需额外实现**：

| 项目 | 核查结论 | 说明 |
|------|---------|------|
| 混合指令 decompose | ✅ Agent LLM 已覆盖 | 「打开微信然后发消息」直接给 Agent，LLM 自行拆解执行 |
| ASR 模糊输入清洗 | ✅ Agent LLM 已覆盖 | 实测「那个呃你好」→ 正确回「你好」 |
| 流式 TTS | ✅ 不需要 | 语音回复仅 1-2 句，非流式 TTS 延迟差 < 50ms |
| Qwen TTS 验证 | ✅ 代码已完成 | `speak_qwen_tts` 调 DashScope API，需设 `EVOLOOP_QWEN_TTS_KEY` |
| F12 快捷键冲突 | ✅ 系统配置问题 | macOS 占用 F12，设置界面可更换快捷键 |

### 12.3 清理记录

| 操作 | 原因 |
|------|------|
| 删除了 `session.py` | 多轮上下文由 Agent 消息历史维护，不需要独立模块 |
| 删除了 `voice/dictation_en.md` | LLM 提示词不分语言，中文版足够 |
| 删除了 `VoiceStateIndicator` 前端组件 | 窗口关闭后不可见，改用托盘图标 |
| 移除了 Rust 中 `set_app_handle` | 改为 `VoiceEventBus` trait 注入 |
| 删除了 `app_handle` 字段 | 改为 `event_bus` trait |
| 删除了 `VoiceResultSubscriber` | 被 `VoiceChannel`（channel 架构）替代 |
| 删除了 `execute_many`、`route_many` | 死代码，多意图编排被 Agent LLM 替代 |
| 删除了 `resolver.py` | 死代码，唯一下游 `execute_many` 已删 |
| 删除了 `peek_voice` | 死代码，零生产调用者 |
| 删除了 `_DUPLICATE_ROUTE_CACHE` | 冗余优化，`is_duplicate` + `get_terminal_result` 已足够 |
| 删除了 `chat` 节点（node/chat.py、prompt） | Agent 架构改造，Chat 节点被合并到 Supervisor |
| 移除了 `voice_ws.py` 硬编码 routed 推送 | 改由 Supervisor AI 消息通过 VoiceChannel 自然下发 |
| 移除了 `finish.prompt.j2` 中的 `is_voice` 分支 | Finish 始终生成完整报告，VoiceChannel 只取摘要 |
| **已清理：** `router.py` 中非 `_get_local_matcher` 函数 | ✅ 已清理（2026-07 代码核查确认）|
| **已清理：** `decompose.py` | ✅ 已删除（文件不存在）|
| **已清理：** `route_cache.py` | ✅ 已删除（⚠️ 测试文件 `tests/unit/core/routing/test_route_cache.py` 残留，导入将失败）|
| **已清理：** `finish.prompt.j2` `learn_from_trace` 引用 | ✅ 已清理（模板中已无引用）|
| **待清理：** `retriever.py` preheat 路径 | 仍被 `voice_ws.py` 调用，但离线 ASR 已无增量结果，实际无意义 |
| **✅ 已清理：** `dictation.rs`（Rust） | 死代码，旧 LM Studio 客户端，已删除 |
| **✅ 已清理：** `ws_client.rs:send_partial/send_cancel` | 不再调用 |
| **✅ 已清理：** `speak_text` Tauri 命令 | 全部走 `speak_direct` 或 `TtsEngine` |
| **✅ 已清理：** 在线 Paraformer ASR | 全部走 Qwen3-ASR 离线 |

---

## 13. 现有问题的处理结论 — ✅ 已完成

采用流式架构后，之前列出的后端问题需要按以下优先级处理：

| 问题 | 是否必须处理 | 优先级 | 说明 |
|---|---|---|---|---|
| 进程内连接管理 | 否，单桌面应用进程内 dict 即可 | P2 | |
| 连接异常处理 | 否，本地 IPC 下 WebSocketDisconnect 已在读取循环中清理 | ~~P0~~ **取消** | |
| 断线重连 | 否，WebSocket 走 127.0.0.1 无网络断开，后端重启重新 F12 即可 | ~~P1~~ **取消** | |
| `voice.cancel` 未实现 | 是，打断依赖它 | P0 | 全双工核心（✅ 已修复） |
| ~~`execute_many` 未注册~~ | 是，需要取消和异常处理 | P0 | **已删除** `execute_many`，Agent task 由 `VoiceTaskRegistry` 管理（✅ 已完成） |
| 同线程并发控制 | 是，否则打断会乱 | P0 | ✅ 已实现 |
| 缓存泄漏 | 是，可改为 session 级别 | P1 |
| terminal result 5 分钟 | 可接受，应用生命周期内足够 | P2 | |
| `/transcribe-stream` 501 | 否，Tauri 端做流式 ASR | P3 | 仅降级路径需要 |
| 无鉴权 | 否，本地 IPC 无需鉴权 | P3 | |

## 14. 延迟预算（端到端） — ✅ 已完成

```text
用户停嘴
  │
  ├─ VAD 端点检测           300-500ms
  ├─ ASR final transcript    50-100ms (流式已识别，仅 finalize)
  ├─ IPC (voice.route)        ~1ms
  ├─ L0 匹配                  ~1ms（未命中）
  ├─ LLM 首 token (云端)     ~2s (deepseek-chat via Gateway)
  │  （本地闪电模型首 token: ~500ms）
  ├─ 首句边界               300-600ms (累积到 。！？)
  ├─ TTS 首包               100-400ms (AVSpeech / Edge-TTS)
  │
  └─ 用户听到首段 TTS

L0 命中：< 50ms（跳过 LLM）
Agent 直接回答（本地闪电模型）：~1.5s
Agent 直接回答（云端 deepseek-chat）：~2s
Worker 执行：3-10s（首句 TTS 后流式）
```

**全双工重叠期**：首句 TTS 播放期间，LLM 继续生成后续 token，Tauri 继续录制麦克风。用户可在任何时刻打断。

---

## 16. 语音输出分层设计 — ✅ 已验证

> 代码已实现，尚未集成测试验证。§18-19 已被移至独立文档。

### 16.1 问题

当前语音通道把 Agent 产出的全部内容灌进 TTS 播报：

```
Supervisor 直接回答 → summary → TTS 播报全文 ✅（1-2 句，合适）
Supervisor → Worker → Finish
  ├── Supervisor 即时回应 "好的，我来处理" → TTS 播报 ✅
  ├── Worker 执行结果 → ❌ 过长，不适合 TTS
  └── Finish → summary → TTS 播报完整 summary ❌ 太长
```

**需要的三层输出：**

| 层 | 输出给谁 | 内容要求 |
|------|---------|---------|
| Supervisor 即时回复 | TTS | 短、自然、口语化 |
| Worker 中间结果 | 不需要 TTS | 沉默执行 |
| Finish 最终结果 | 文字 + TTS 分开 | 文字详细，TTS 只摘要 |

### 16.2 实现方案

#### 数据模型

`SessionCompletedData`（`lifecycle.py`）新增字段：

```python
summary: str | None = None      # 详细文字回复（聊天界面显示）
tts_summary: str = ""           # 短语音摘要（TTS 播报）
```

#### Finish 节点

`finish.prompt.j2` 在 `{% if is_voice %}` 时要求 LLM 输出两种格式：

```xml
<evoloop_final_report>
  完整详细回复，供前端显示
</evoloop_final_report>
<evoloop_tts_summary>
  1-2 句话简短语音摘要，TTS 播报用
</evoloop_tts_summary>
```

`finish.py` 从 LLM 输出提取 `<evoloop_tts_summary>` 填入事件。

#### VoiceChannel

`voice_channel.py` 处理 `SessionCompletedEvent` 时优先用 `data.tts_summary`：

```python
push_text = data.tts_summary if data.tts_summary else (data.summary or "")
```

#### Supervisor 直接回答

`supervisor.py` 在直接回答时填充 `tts_summary`：

```python
tts_summary=ai_content if source == "voice" else ""
```

### 16.3 改动的文件

| 文件 | 改动 |
|------|------|
| `lifecycle.py` | `SessionCompletedData` 加 `tts_summary: str = ""` |
| `supervisor.prompt.j2` | `{% if is_voice %}` 注入语音行为规则（简短回复、禁 markdown） |
| `supervisor_lightning.prompt.j2` | 同上 |
| `finish.prompt.j2` | `{% if is_voice %}` 要求输出 `<evoloop_tts_summary>` |
| `finish_builder.py` | `template_vars` 加 `is_voice` |
| `finish.py` | 从 LLM 输出提取 `tts_summary` 填入事件 |
| `supervisor.py` | 直接回答时填充 `tts_summary` |
| `voice_channel.py` | 优先用 `data.tts_summary`，无则 fallback `data.summary` |
| `supervisor_builder.py` | 传入 `has_running_worker` / `running_worker_desc`（WorkerRegistry） |

### 16.4 当前状态

| 组件 | 状态 |
|------|------|
| `tts_summary` 字段 | ✅ 已加入 `SessionCompletedData` |
| Supervisor 语音行为规则 | ✅ 标准模板 + 轻量模板均已注入 `is_voice` |
| Finish 双输出 | ✅ `finish.prompt.j2` 支持 `{% if is_voice %}`，`finish.py` 提取 tts_summary |
| VoiceChannel 优先使用 tts_summary | ✅ 已实现 |
| Supervisor 直接回答填充 tts_summary | ✅ 已实现 |
| Finish builder 传入 is_voice | ✅ 已实现 |

### 16.6 实施阶段

**Phase A：Supervisor 语音感知（标准模板）**

| # | 文件 | 操作 | 状态 |
|---|------|------|------|
| 1 | `supervisor.prompt.j2` | 根据 `is_voice` 追加行为指令：简短回复、复杂任务先确认 | ⏳ |
| 2 | `supervisor_builder.py` | 确认 `is_voice` 已正确传入模板 | ✅ 已完成 |

**Phase B：Finish 双输出**

| # | 文件 | 操作 | 状态 |
|---|------|------|------|
| 1 | `lifecycle.py` | `SessionCompletedData` 加 `tts_summary: str = ""` | ⏳ |
| 2 | `finish_builder.py` | 传 `is_voice`，指令 LLM 在 `is_voice=true` 时产出 `summary` + `tts_summary` | ⏳ |
| 3 | `finish.prompt.j2` | 根据 `is_voice` 添加双输出模板 | ⏳ |
| 4 | `supervisor.py` | 直接回答时填充 `tts_summary` | ⏳ |
| 5 | `finish.py` | 从 LLM 输出提取 `tts_summary` 填入事件 | ⏳ |

**Phase C：VoiceChannel 使用 tts_summary**

| # | 文件 | 操作 | 状态 |
|---|------|------|------|
| 1 | `voice_channel.py` | `SessionCompletedEvent` 处理时优先用 `data.tts_summary` | ⏳ |
| 2 | `voice_channel.py` | Supervisor ack 用已有 `summary`（已够短） | ⏳ |

## 17. 模型管理 — ⏳ 待实施

### 17.1 问题

当前语音模型全部依赖用户手动下载到 `~/.evoloop/models/`，没有自动下载机制。模型总量 ~3.1GB，无法打包进 Tauri 二进制。

### 17.2 模型清单

| 模型 | 大小 | 用途 | 分发方式 | 前端控制 |
|------|------|------|---------|---------|
| Silero VAD | 629KB | VAD 断句 | Tauri 打包 | 自动可用 |
| Qwen3-ASR | 954MB | ASR 识别 | 首次设置下载 | 未下载锁住整个语音入口 |


### 17.3 锁住的位置

| 模型 | 未下载时锁住 | 组件 |
|------|-------------|------|
| Qwen3-ASR | 对话/听写按钮不可用，TTS 设置中 STT 选项禁用 | `VoiceControlSettings`、`tray.rs` 菜单 |


### 17.4 后端接口

```
GET  /api/v1/models/status           → 各模型下载状态
POST /api/v1/models/download         → 触发下载 {model_id: str}
GET  /api/v1/models/download/progress → SSE 下载进度流
```

### 17.5 接口详情

#### `GET /api/v1/models/status`

```json
{
  "models": [
    {"id": "qwen3_asr", "name": "Qwen3-ASR", "size": 954, "unit": "MB", "downloaded": false, "available": false}
  ]
}
```

VAD 已打包，不在此列。

#### `POST /api/v1/models/download`

```json
// 请求
{"model_id": "qwen3_asr"}
// 响应
{"status": "started", "model_id": "qwen3_asr"}
```

#### `GET /api/v1/models/download/progress?model_id=qwen3_asr`

SSE 流：
```
data: {"model_id": "qwen3_asr", "progress": 0.45, "speed": "12MB/s", "eta": "45s"}
data: {"model_id": "qwen3_asr", "progress": 1.0, "status": "completed"}
```

### 17.6 前端交互

- 语音设置页增加模型状态区域
- 每个模型显示：模型名、大小、下载状态、下载按钮
- 下载中显示进度条 + 速度 + 预估时间
- 下载完成后自动解锁对应功能
- TTS 引擎下拉和 STT 提供商下拉检测模型状态，未下载的选项禁用并提示"请先下载模型"

### 17.7 实现阶段

| Phase | 内容 |
|-------|------|
| A | 后端模型状态/下载/进度接口 |
| B | 前端模型管理 UI（状态显示 + 下载按钮 + 进度） |
| C | TTS/STT 选项联动锁住 |
| D | tray 菜单禁用 |

## 18. 实施阶段 — ✅ 已完成（部分已过时）

> 以下为项目实施记录。部分早期 Phase 的技术选型已变更，标注"已演进"。
>
> **技术演进总览**：
> - ASR：流式 Paraformer → **Qwen3-ASR 离线整段**
> - VAD：Sherpa-ONNX VAD → **Silero VAD**（800ms 静音，30s 最大语音）
> - TTS：统一为火山引擎实时对话 API
> - voice.partial：已移除（离线 ASR 无增量中间结果）
> - 听写润色：LM Studio → **Qwen3-ASR + Python LLM polish**（可选）

### Phase 1：流式基础设施（已演进）

> 当前 ASR 已改为 Qwen3-ASR 离线，VAD 改为 Silero。以下记录原设计方案供参考。

1. ✅ ~~在 Tauri 端实现音频采集、AEC、VAD（Sherpa-ONNX VAD，silence 300-500ms）和流式 ASR（Sherpa-ONNX streaming）。~~ → 已演变为 Qwen3-ASR 离线 + Silero VAD 800ms
2. ✅ ~~在 Tauri 端实现流式 TTS（AVSpeechSynthesizer / Edge-TTS / Qwen-TTS）。~~ → 已扩展为 5 引擎（见 §6.3）
3. ✅ 保留并验证 Python 后端 `POST /api/v1/audio/transcribe` 文件级音频转写能力。
4. ✅ 验证 LM Studio Qwen3-4B `stream=true` token 流式输出。

### Phase 2：WebSocket 协议升级

1. ✅ 扩展 `voice_ws.py` 支持新信令：`voice.barge_in`、`voice.cancel`。
2. ✅ 实现 `voice.token` / `voice.tts_boundary` 流式推送。
3. ✅ 引入服务端语音状态机。
4. ✅ 实现 `VoiceTaskRegistry` 和真正的取消逻辑。
5. ✅ 同线程并发锁。

### Phase 3：流式 LLM 输出

1. ✅ 在 `executor.py` 实现 `stream_llm_response()`：LLM `stream=true`，逐 token 推送 `voice.token`。
2. ✅ 实现句子边界检测（`。！？.!?\n`），推送 `voice.tts_boundary`。
3. ✅ Tauri 端实现 token 缓冲 + 句子切分 + 流式 TTS 触发。

### Phase 4：ASR 增量预加载（已废弃）

> `voice.partial` 已随在线流式 ASR 一同移除。Qwen3-ASR 离线整段识别无增量中间结果。

### Phase 5：听写模式（已演进）

> 当前听写 ASR 已改为 Qwen3-ASR 离线，不再经过 LM Studio 润色。

1. ✅ ~~在 Tauri Rust 层实现听写模式：短按 F12 → 流式 ASR → Qwen3-4B via LM Studio 流式润色 → Cmd+V 粘贴。~~ → 已演变为 VAD + Qwen3-ASR + 可选 LLM polish
2. ✅ 定义润色提示词，对齐原型 `dictation.md`。
3. ✅ 后端实现 `POST /api/v1/voice/dictation` 云端降级端点。
4. ✅ 优先级：Tauri 优先直接调 LM Studio 本地润色，LM Studio 不可用时 fallback 到 Python 后端。

### Phase 6：连接与状态管理

1. ✅ 单桌面应用内，进程内 `dict` 满足 `thread_id → conn_id` 映射。
2. ✅ 实现 Tauri 重连后恢复 `thread_id` 绑定。
3. ✅ 改进发送异常处理，自动清理失效连接。

### Phase 7：Tauri Rust 原生层全双工（已演进）

> ASR 已改为 Qwen3-ASR 离线，TTS 已扩展为 5 引擎。

1. ✅ 持续采集麦克风，实现 AEC（回声消除）。
2. ✅ ~~接入流式 ASR（Sherpa-ONNX streaming）和流式 TTS（AVSpeechSynthesizer / Edge-TTS）。~~ → 已演变为 Qwen3-ASR 离线 + 5 引擎 TTS
3. ✅ 实现 token 缓冲 + 句子切分 + 流式 TTS 播放和打断。
4. ✅ 实现 VAD 检测 + barge-in 触发。

### Phase 8：压测与调优

1. ✅ 端到端延迟测试（测得首句 TTS TTFB ~1.5-2s，当前因架构变化需重新测量）。
2. ✅ 全双工测试：TTS 播放时用户插话，打断响应 < 200ms。
3. ✅ 多层 LLM 策略（本地闪电 + 云端 Gateway）设计完成。

### Phase 9：ASR/TTS 架构统一（近期完成）

1. ✅ Qwen3-ASR 替换流式 Paraformer，对话和听写模式统一。
2. ✅ 移除 voice.partial、在线流式 ASR 相关死代码。
3. ✅ TTS 统一为火山引擎实时对话 API。
4. ✅ `BaseTTSProvider` 抽象 + `TTSFactory` + 统一 `POST /voice/tts` 端点。
5. ✅ Rust 侧 TTS 统一管理（`speak_text` → `speak_direct`，全部走 `TtsEngine`）。
6. ✅ 配置同步双写（localStorage + 后端 DB） + WS 广播。
7. ✅ 删除 `dictation.rs`、`send_partial` 等死代码。
8. ✅ 修复 VAD 参数（5s → 30s max_speech）。
9. ✅ 修复 Qwen3-ASR tokens 配置（空字符串 → 正确路径）。
10. ✅ L0 确认语改为泛化短语池（按语言分中文/英文）。

### Phase 10：语音输出分层 + 状态查询（代码已完成，待测试验证）

1. ✅ `SessionCompletedData` 新增 `tts_summary` 字段，区分文字回复和语音摘要。
2. ✅ `voice_channel.py` 优先使用 `tts_summary` 做 TTS，`summary` 给前端显示。
3. ✅ `finish.prompt.j2` 在 `is_voice` 时要求输出 `<evoloop_tts_summary>`。
4. ✅ 标准 Supervisor 模板 + 轻量模板均注入 `is_voice` 语音行为规则。
5. ✅ `WorkerRegistry` 跟踪 Worker 状态，新请求可查询运行中的 Worker 进度。
6. ✅ `_handle_route` 锁策略变更：锁只覆盖 L0 + dispatch，Worker 执行在锁外。
7. ✅ 新请求可检查 WorkerRegistry → Supervisor 判断 query/new，不误杀旧任务。
8. ⏳ 集成测试验证（待执行）。

## 20. 三端共享状态（SSOT）设计

### 20.1 背景

voice.route / voice.dictation.finalize 等信令需要带上 `project_id` 等全局上下文，但当前 Rust 端没有可靠途径获取这些值——`send_route()` 只发了 `thread_id`、`text`、`message_id`，`project_id` 缺省导致 Python 始终使用默认值 0。

同时 TTS 配置（TTS_ENGINE / TTS_VOICE / TTS_SPEED / QWEN_TTS_API_KEY）在 React localStorage、Rust 内存、Python DB 三处分别存储，没有单一权威源，存在写冲突风险。

### 20.2 架构：Python 为 SSOT，WS 推 Rust，SSE 推 React

```
Python SharedState (进程内 dict) ← authoritative
  │
  ├── WS system:state_snapshot ───→ Rust 本地缓存 (Arc<RwLock<HashMap>>)
  │   (system.init 握手时全量)        │
  │   (system.state_changed 增量)     ├── send_route() 读 project_id
  │                                  ├── send_dictation_finalize() 读 project_id
  │                                  └── TTS 引擎读 engine/voice/speed/key
  │
  ├── SSE system:state_snapshot ──→ React zustand store
  │   (UniversalBridgeSubscriber)     (useSharedStore)
  │
  └── POST /api/v1/shared/state ← React 写入
      (桌面端/移动端切 project 等)
```

**关键原则**：所有写入都经 Python（桌面端切 project 也 POST 到 Python，不直写 Rust），Python 再通过 WS 推 Rust、SSE 推 React，保证最终一致性。

### 20.3 SharedState 初始结构

```python
# backend/app/core/shared_state.py
class SharedState:
    _store: dict[str, str] = {
        "project_id": "0",
        "thread_id": "",
        "TTS_ENGINE": "edge-tts",
        "TTS_VOICE": "zh-CN-XiaoxiaoNeural",
        "TTS_SPEED": "1.0",
        "QWEN_TTS_API_KEY": "",
    }
```

### 20.4 三端行为

| 端 | 初始化 | 读取 | 写入 |
|---|--------|------|------|
| **Python (SSOT)** | `_store` 默认值 | 任意模块 `SharedState.get("key")` | `SharedState.set("key", "val")` → publish event |
| **Rust (缓存)** | WS `system.init` 握手时写入 `shared_state: Arc<RwLock<HashMap>>` | `send_route()` 前 `self.shared_state.read()["project_id"]` | 仅被动接收 Python 推送，不主动写 |
| **React (缓存)** | `system:state_snapshot` event → `useSharedStore` zustand | UI 显示、调用 API 时读取 | `POST /api/v1/shared/state` + 乐观更新本地 store |

### 20.5 WS 信令扩展

现有 `system.init` 握手扩展 `state` 字段：

```json
// Python → Rust (system.init 握手)
{
  "type": "system.init",
  "body": {
    "client_id": "...",
    "device_key": "",
    "configs": { "TTS_ENGINE": "...", ... },
    "state": {                          // ← 新增
      "project_id": "123",
      "thread_id": "voice-abc"
    }
  }
}
```

新增 `system.state_changed` 增量推送：

```json
// Python → Rust (增量更新)
{
  "type": "system.state_changed",
  "body": {
    "key": "project_id",
    "value": "456"
  }
}
```

### 20.6 Rust 端实现要点

- `voice_session.rs` 的 `system.init` 处理器：除了转发 `configs`，也写入 `shared_state` 本地缓存
- 新增 `system.state_changed` 处理器：更新缓存中的对应 key
- `ws_client.rs` 的 `send_route()` 和 `send_dictation_finalize()`：从缓存读 `project_id` 塞进 body

### 20.7 变更清单

| 文件 | 改动 |
|------|------|
| `backend/app/core/shared_state.py` | **新建**：SharedState 类（进程内 dict + asyncio.Lock + publish_event） |
| `backend/app/core/events/publishers.py` | 新增 `publish_state_changed(key, value)` |
| `backend/app/core/events/schemas/lifecycle.py` | 新增 `StateChangedEvent` |
| `backend/app/api/routes/voice_ws.py` | `system.init` 增加 `state` 字段；新增 `system.state_changed` 广播 handler；新增 `POST /api/v1/shared/state` |
| `backend/app/core/events/subscribers/bridge.py` | `UniversalBridgeSubscriber` 增加 `StateChangedEvent` → SSE 推送 |
| `frontend/src-tauri/src/voice/voice_session.rs` | `system.init` 处理器写入 `shared_state` 缓存；新增 `system.state_changed` 处理器 |
| `frontend/src-tauri/src/voice/ws_client.rs` | `send_route()` 读缓存塞 `project_id`；`send_dictation_finalize()` 同 |
| `frontend/src-tauri/src/voice/mod.rs` 或 `lib.rs` | 新增 `VoiceSession.shared_state` 字段声明 |
| `frontend/packages/desktop/src/hooks/useVoiceEvents.ts` | 新增 `system:state_snapshot` 监听 → 更新 zustand store |
| `frontend/packages/desktop/src/stores/sharedStore.ts` | **新建**或扩展 `voiceStore`：`sharedState` 字段 |

### 20.8 不涉及的模块

- `voice_channel.py`：不变
- `MessagePublisher`：不变
- `WorkerRegistry` / `VoiceTaskRegistry`：不变
- `voice.start` / `voice.stop` / `voice.barge_in` 信令：不变
- `voice.route` 信令格式：不变（`send_route` 内部只多了 `project_id` 字段）

## 20. 三端共享状态（SSOT）设计

### 20.1 背景

## 21. 输入通道（InputChannel）设计

### 21.1 背景

当前系统有对称的输出通道抽象（`Channel` + `ChannelRegistry`），但输入侧没有统一抽象。三个消息来源各自硬编码：

| 输入来源 | 当前入口 |
|---------|---------|
| 语音 | `voice_ws.py` 直接调 `dispatch_agent_run()` |
| 移动端 | `EngineCommandSubscriber` 直接调 `dispatch_agent_run()` |
| 网页聊天 | `_chat.py` 直接调 `dispatch_agent_run()` |

所有路径汇聚于 `dispatch_agent_run()`，但参数格式、source 标记、前处理逻辑分散在三处。

### 21.2 架构

```
channel/
├── base.py              ← output Channel + input InputChannel 抽象基类 + IncomingMessage
├── input/
│   ├── __init__.py
│   ├── base.py          ← 重导出 IncomingMessage/InputChannel（防循环引用）
│   ├── voice_input.py   ← VoiceInputChannel: voice.route 消息 → IncomingMessage
│   ├── mobile_input.py  ← MobileInputChannel: mobile chat 消息 → IncomingMessage
│   └── web_input.py     ← WebInputChannel: web chat 消息 → IncomingMessage
├── output/
│   ├── voice_channel.py ← VoiceChannel（从 channel/ 移入）
│   ├── web_channel.py   ← WebChannel（从 channel/ 移入）
│   └── mobile_channel.py← MobileChannel（从 channel/ 移入）
└── registry.py
```

核心抽象（`base.py`）：

```python
@dataclass
class IncomingMessage:
    source: str           # "voice" | "mobile" | "web"
    thread_id: str
    text: str
    project_id: int = 0
    references: list | None = None
    metadata: dict | None = None
    member_id: int = 0
    command_id: int | None = None
    message_id: str | None = None
    checkpoint_id: str | None = None
    model: str | None = None
    context: Any = None
    is_retry: bool = False
    skip_message_persistence: bool = False

class InputChannel(ABC):
    name: str

    @abstractmethod
    async def receive(self, raw: Any, **kwargs) -> IncomingMessage | None: ...

    async def dispatch(self, msg: IncomingMessage) -> DispatchResult:
        # 内部调 dispatch_agent_run()
```

### 21.3 各 InputChannel 实现

| InputChannel | receive 输入 | 位置 |
|-------------|------------|------|
| `voice_input` | `voice.route` body dict + `metadata` kwargs | `channel/input/voice_input.py` |
| `mobile_input` | `command.relay/chat` body dict + `member_id` kwargs | `channel/input/mobile_input.py` |
| `web_input` | 请求体 dict + `context`/`member_id` kwargs | `channel/input/web_input.py` |

### 21.4 调用点迁移

| 调用点 | 旧代码 | 新代码 |
|--------|-------|-------|
| `voice_ws.py:165` | `dispatch_agent_run(thread_id, ...)` | `voice_input.receive(body) → voice_input.dispatch(msg)` |
| `subscribers.py:412` | `dispatch_agent_run(thread_id, source="mobile", ...)` | `mobile_input.receive(command, ...) → mobile_input.dispatch(msg)` |
| `_chat.py:119` | `dispatch_agent_run(thread_id, ...)` | `web_input.receive(req_dict, ...) → web_input.dispatch(msg)` |

### 21.5 不变的部分

- 各输入源的前处理逻辑（L0 匹配、reference 提取等）仍在各自的入口文件中
- `dispatch_agent_run()` 本身不变
- `ChannelRegistry` / `VoiceChannel` / `WebChannel` / `MobileChannel` 接口不变（仅物理位置移到 `output/` 下）
- `voice_ws.py` 的连接管理、config sync、TTS endpoint 不变

### 21.6 变更清单

| 文件 | 改动 |
|------|------|
| `channel/base.py` | 新增 `IncomingMessage` + `InputChannel` 抽象类 |
| `channel/__init__.py` | 新增导出 `IncomingMessage`、`InputChannel`、`voice_input`、`mobile_input`、`web_input` |
| `channel/input/__init__.py` | **新建** |
| `channel/input/base.py` | **新建**（重导出，防循环引用） |
| `channel/input/voice_input.py` | **新建**：`VoiceInputChannel` |
| `channel/input/mobile_input.py` | **新建**：`MobileInputChannel` |
| `channel/input/web_input.py` | **新建**：`WebInputChannel` |
| `channel/output/` | 三个文件从 `channel/` 移入，import 改为 `..base` |
| `channel/registry.py` | import 指向 `output/` |
| `voice_ws.py` | 改用 `voice_input.receive().dispatch()` |
| `subscribers.py` | 改用 `mobile_input.receive().dispatch()` |
| `_chat.py` × 2 | 改用 `web_input.receive().dispatch()` |
| 两个测试文件 | import 指向 `output/` |

## 22. 风险与依赖 — ✅ 已完成

- **AEC 必须在 Tauri Rust 原生层完成**：Python 后端没有扬声器播放的参考信号，无法做回声消除。如果 Rust 层不做 AEC，麦克风会把扬声器播放的 TTS 录进去，导致 VAD 误判为用户说话。这是全双工的硬性前提。
- **LLM 流式延迟**：本地闪电模型（Qwen3-4B via LM Studio）首 token 200-400ms；Gateway deepseek-chat 首 token ~2s。后续 token 50-100ms/token。
- **TTS 首包延迟**：AVSpeechSynthesizer < 100ms，Edge-TTS 200-400ms。Edge-TTS 依赖网络，可能不稳定。
- **VAD 精度**：silence 300-500ms 是折中值。太短会误断句，太长会增加延迟。需要根据实际场景调优。
- **ASR/TTS/LLM 本地资源占用**：同时跑流式 ASR + 流式 TTS + LLM 推理，对笔记本 CPU/GPU 有要求。需要限制并发（通常同一时刻只有一个语音会话活跃）。
- **IPC 延迟**：Tauri 与 Python 后端通过 WebSocket 通信，环回延迟很低（~1ms），但 token 流数据量大时需要避免主线程阻塞。
- **状态机复杂度**：打断、流式输出、模式切换、并发需要大量边界测试。
- **进程重启丢失状态**：Tauri 或 Python 重启后，所有连接映射和音频流状态丢失。由于这是单桌面应用，这是可接受的；如需持久化，另行设计。
- **Layer 0 覆盖率**：全双工体验依赖快速响应，Layer 0 模板命中率直接影响延迟。需要持续迭代模板。

## 23. L0 应用执行层设计

### 23.1 目标

| 目标 | 说明 |
|------|------|
| **Agent 前拦截** | L0 优先处理，不命中才走到 Agent |
| **确定性动作走 Macro** | 所有确定性动作统一由 Macro 引擎承载，不在 L0 直接调系统命令 |
| **内置命令面向 Evoloop 自身** | L0 内置命令是 Evoloop 的系统命令（end/clarify/rename/ack/cancel），不是 macOS 系统命令 |
| **先跑通，后加固** | 第一阶段不设安全限制，先跑通全套链路 |

### 23.2 现状问题

当前 L0 匹配命中后只走 `_push_local_result()` → WS `voice.route_result` → Rust TTS 播确认语，**没有执行任何系统操作**。同时：

| 能力 | 有？ | 在哪 |
|------|------|------|
| L0 模板匹配 | ✅ `LocalMatcher` | `routing/local_matcher.py` |
| L0 模板内容 | ❌ 混杂了 Evoloop 命令 + macOS 系统操作 | `routing/init_spec.py` |
| Macro 触发词 | ✅ `trigger_patterns` 字段 | `models/macro.py:32` |
| Macro → L0 注入 | ❌ 当前只进了 L1 嵌入索引，没进 L0 模板 | `routing/sync.py` |
| Macro 执行（Voice） | ⚠️ 入口就绪但 `VOICE_POLICY` 阻塞 applescript | `execution/macro/runner.py` |
| L0 → Macro 执行通路 | ❌ 不存在 | — |
| 环境控制（DesktopController） | ✅ 已支持 applescript/key_press/open_app/screenshot | `environment/controllers/desktop/` |
| ActionRegistry applescript mapping | ✅ 已注册 `applescript` → `"applescript"` (desktop) | `environment/capabilities/registry.py:267` |

### 23.3 架构

```
voice.route → L0 Matcher
  │
  ├── 命中内置命令（Evoloop 自身）→ _handle_builtin()
  │     ├── end      → 通知 Rust 关闭语音会话
  │     ├── clarify  → 请求 Rust 重播 TTS
  │     ├── rename   → 更新配置
  │     ├── ack      → 确认信号（后续实现）
  │     └── cancel   → 取消信号（后续实现）
  │     → _push_local_result()  → WS voice.route_result {status:"routed", target:{type:"local"}}
  │       → Rust 播通用确认语（现有路径，不改）
  │
  ├── 命中 Macro 触发词 → _dispatch_macro()
  │     → MacroRunner.run_deterministic(VOICE_POLICY)  （await，同步等结果）
  │       → MacroEngine.execute() → _execute_desktop_step()
  │         → DesktopController.execute(action="applescript"/"open_app"/...)
  │     → 成功 → _push_macro_result()  → WS voice.route_result {status:"done", summary:"已静音"}
  │               → Rust 播 summary（复用现有 done 路径，不改 Rust）
  │     → 失败 → _push_macro_result()  → WS voice.route_result {status:"failed", summary:"静音失败"}
  │               → Rust 播错误提示（复用现有 failed 路径，不改 Rust）
  │
  └── 未命中 → dispatch_agent_run()
```

**TTS 路径决策**：Macro 执行结果走 WS `voice.route_result` 的 `status:"done"`/`"failed"` + `summary` 字段，复用 Rust 现有的 done/failed 处理分支（`voice_session.rs:693-710`）。**Rust 侧不需要改**。内置命令继续走 `status:"routed"` + `target.type:"local"` 现有路径。

L0 Matcher 的模板来源：

```
                    ┌─ 硬编码模板（5 条）：end, clarify, rename, ack, cancel
L0 templates = ────┤
                    └─ DB 动态加载：Macro.trigger_patterns（预置 + 用户 + 合成）
                         → enrich_spec_with_macro_triggers() 在 build_init_spec 后追加
                         → {{slot}} 转为 {slot}，slot 名从 Macro.parameters 提取
```

### 23.4 逐文件 加 / 改 / 删 清单

#### 23.4.1 `routing/init_spec.py`

**删：**

| 对象 | 内容 | 原因 |
|------|------|------|
| `_TEMPLATES` 中 13 条系统模板 | play_pause×2, next_track, prev_track, set_volume, mute, unmute, open_app, focus_app, quit_app, press_key, screenshot, lock_screen | 改由预置 Macro 承载 |
| `_VOICE_LOCAL_ACTIONS` 中 12 条系统条目 | play_pause, next_track, prev_track, set_volume, mute, unmute, focus_app, quit_app, press_key, screenshot, lock_screen | 不再作为 L1 local entry，改由 Macro entry 覆盖 |
| `_KEY_DICT` | 整个字典 | 仅被已删的 press_key/set_volume 模板使用 |
| `_DELTA_DICT` | 整个字典 | 仅被已删的 set_volume 模板使用 |
| `build_init_spec()` 中 `slot_dictionaries` 的 `"key"` 和 `"delta"` 项 | 两个 dict 项 | 无对应模板 |
| `_registry_actions()` 中 `open_app` 过滤 | `if a.id in ("open_app",)` 分支 | open_app 改由预置 Macro 覆盖 |

**加：**

| 对象 | 内容 |
|------|------|
| `_TEMPLATES` 新增 2 条 | `ack`：对对对/没错/就这个/可以/对的/是的；`cancel`：算了/不用了/不要/取消 |
| `_VOICE_LOCAL_ACTIONS` 新增 2 条 | `{"id": "ack", "params": {}}`，`{"id": "cancel", "params": {}}` |
| `enrich_spec_with_macro_triggers(spec)` | async 函数：从 DB 查 `is_routable()` 的 Macro，将 `trigger_patterns` 转为 L0 templates（`{{slot}}` → `{slot}`，slot 名从 `parameters` 提取），追加到 `spec.templates` |

`enrich_spec_with_macro_triggers` 签名：

```python
async def enrich_spec_with_macro_triggers(spec: RouteCatalog) -> RouteCatalog:
    """从 DB 加载 routable Macro 的 trigger_patterns，注入为 L0 templates。
    
    作用域：全局（project_id IS NULL）+ 当前项目（shared_state.project_id）。
    冲突去重：preset 优先于用户，同 pattern 只保留第一条。
    """
    from app.core.state import shared_state
    from app.infrastructure.database import session_scope
    from app.models.macro import Macro
    from sqlmodel import select, case

    current_project_id = int(await shared_state.get("project_id", "0"))

    async with session_scope() as session:
        stmt = select(Macro).where(
            Macro.is_active.is_(True),
            Macro.status == "verified",
            # 全局 + 当前项目
            (Macro.project_id.is_(None)) | (Macro.project_id == current_project_id),
        ).order_by(
            # preset 优先（namespace="preset" 排在最前）
            case((Macro.namespace == "preset", 0), else_=1),
            Macro.created_at.asc(),
        )
        macros = (await session.execute(stmt)).scalars().all()

    seen_patterns: set[str] = set()
    for macro in macros:
        triggers = macro.trigger_patterns or []
        deduped = []
        for trigger in triggers:
            pattern = trigger.replace("{{", "{").replace("}}", "}")
            if pattern in seen_patterns:
                logger.warning(
                    "[init_spec] trigger pattern '%s' skipped (macro %d, already bound)",
                    pattern, macro.id,
                )
                continue
            seen_patterns.add(pattern)
            deduped.append(pattern)
        if not deduped:
            continue
        # 从 parameters 提取 slot 名
        slot_names = [p.get("name") for p in (macro.parameters or []) if p.get("name")]
        slots = {name: "str" for name in slot_names}
        spec.templates.append({
            "action": f"macro:{macro.id}",
            "patterns": deduped,
            "slots": slots,
            "args": {},
        })
    return spec
```

**不改：** `_ALIASES`、`_probe_apps()`、`slot_dictionaries["app"]`、`enrich_spec_with_atlas_aliases()` — 保留，仍用于 client spec 和 Atlas enrichment。

#### 23.4.2 `routing/router.py`

**改：**

`_get_local_matcher()` 在 `build_init_spec()` 后追加 enrichment 调用：

```python
spec = await asyncio.to_thread(init_spec.build_init_spec)
spec = await init_spec.enrich_spec_with_macro_triggers(spec)  # 新增
_LOCAL_MATCHER = LocalMatcher(
    templates=spec.templates,
    slot_dictionaries=spec.slot_dictionaries,
    aliases=spec.aliases,
    app_usage_rank=spec.app_usage_rank,
)
```

**加：**

```python
async def rebuild_local_matcher() -> None:
    """置空并立即重建 LocalMatcher（Macro 变更 / 项目切换后调用）。"""
    global _LOCAL_MATCHER
    async with _LOCAL_MATCHER_LOCK:
        spec = await asyncio.to_thread(init_spec.build_init_spec)
        spec = await init_spec.enrich_spec_with_macro_triggers(spec)
        _LOCAL_MATCHER = LocalMatcher(
            templates=spec.templates,
            slot_dictionaries=spec.slot_dictionaries,
            aliases=spec.aliases,
            app_usage_rank=spec.app_usage_rank,
        )
        logger.debug("[router] local matcher rebuilt")
```

**项目切换触发重建**：监听 `StateChangedEvent` 的 `project_id` key → 调 `rebuild_local_matcher()`。`shared_state.set("project_id", ...)` 已在项目切换时触发 `StateChangedEvent`（见 `project/event/subscribers.py`），只需新增一个 subscriber。

#### 23.4.3 `routing/sync.py`

**删：** `_LOCAL_DESC` 中 12 条系统 action 描述（play_pause, next_track, prev_track, set_volume, mute, unmute, focus_app, quit_app, press_key, screenshot, lock_screen, open_app）。

**加：** `_LOCAL_DESC` 新增 `"ack": "确认"`, `"cancel": "取消"`。

#### 23.4.4 `channel/input/voice_input.py`

**改：**

`receive()` 中 L0 命中后分流：

```python
if l0_match is not None:
    action, args = l0_match
    if action.startswith("macro:"):
        macro_id = int(action.split(":", 1)[1])
        await self._dispatch_macro(thread_id, macro_id, args, project_id)
    else:
        await self._handle_builtin(thread_id, action, args)
    return None
```

**加：**

`_dispatch_macro(thread_id, macro_id, args, project_id)`：

```python
async def _dispatch_macro(self, thread_id, macro_id, args, project_id):
    """加载 Macro → preflight → run_deterministic → 推 done/failed/cancelled。
    
    超时保护：5 秒上限，防止 osascript 阻塞（如系统对话框等待）。
    Barge-in：包装为 task 注册到 worker_registry，用户说"停"时可 cancel。
    """
    from app.core.learning.macro.runner import (
        VOICE_POLICY, MacroGateError, load_macro, preflight, run_deterministic,
    )

    # 设为 SPEAKING 状态，阻止后续 voice.route 进入
    if self._state_machine is not None:
        await self._state_machine.set(thread_id, self._state_enum.SPEAKING)

    macro = await load_macro(macro_id)
    if macro is None:
        await self._push_macro_result(thread_id, "failed", "未找到该宏")
        return
    try:
        script = preflight(macro, args)
    except MacroGateError as e:
        await self._push_macro_result(thread_id, "failed", e.message)
        return

    # 包装为 task 并注册到 worker_registry，使 barge-in 能 cancel
    async def _run():
        return await run_deterministic(
            macro, thread_id=thread_id, params=args, project_id=project_id,
            script=script, policy=VOICE_POLICY,
        )

    task = asyncio.create_task(_run())
    if self._worker_registry is not None:
        await self._worker_registry.register_worker(
            thread_id, task, description=f"macro:{macro_id}",
        )

    try:
        outcome = await asyncio.wait_for(task, timeout=5.0)
    except asyncio.TimeoutError:
        await self._push_macro_result(thread_id, "failed", "执行超时")
        return
    except asyncio.CancelledError:
        # barge-in: 用户打断，推 cancelled
        await self._push_macro_result(thread_id, "cancelled", "已取消")
        raise

    status = "done" if outcome.ok else "failed"
    summary = outcome.message or ("完成" if outcome.ok else "执行失败")
    await self._push_macro_result(thread_id, status, summary)
```

`_push_macro_result(thread_id, status, summary)`：

```python
async def _push_macro_result(self, thread_id, status, summary):
    """推 voice.route_result {status:"done"/"failed"/"cancelled", summary:...}。
    复用 Rust 现有的 done/failed/cancelled 处理分支。"""
    body = {"thread_id": thread_id, "status": status, "summary": summary}
    await self._manager.push(
        thread_id, self._envelope(self._message_type.VOICE_ROUTE_RESULT, body)
    )
    await self._state_machine.set(thread_id, self._state_enum.IDLE)
```

`_handle_builtin(thread_id, action, args)`：

```python
async def _handle_builtin(self, thread_id, action, args):
    """处理 Evoloop 内置命令，走现有 routed/local 路径。"""
    # end/clarify/rename/ack/cancel 的具体逻辑后续实现
    # 当前先走通 TTS 确认
    await self._push_local_result(thread_id, action, args)
```

#### 23.4.5 `execution/macro/runner.py`

**改：**

```python
VOICE_POLICY = ExecutionPolicy(
    allow_self_heal=False,
    allowed_sources=frozenset({"desktop", "dom"}),
    # allowed_families 和 max_risk_tier 设为 None — 先跑通，后续迭代加安全
)
```

#### 23.4.6 `execution/macro/event/`

**加：**

- `MacroVerifiedEvent`：Macro 状态变为 verified 时发布
- `MacroDeactivatedEvent`：Macro 被停用时发布
- Subscriber：监听上述事件 → 调 `router.rebuild_local_matcher()`
- Subscriber：监听 `StateChangedEvent` key="project_id" → 调 `router.rebuild_local_matcher()`（项目切换时重建，加载新项目的 Macro）

触发时机覆盖：Macro 创建、更新 trigger_patterns、验证通过、停用、删除、项目切换。

#### 23.4.7 数据迁移（Alembic）

**加：** 23 条预置 Macro 种子数据。

### 23.5 预置 Macro 种子数据

所有预置 Macro：`project_id=NULL`（全局），`status="verified"`，`is_active=True`，`parameters=[]`（无 slot），`namespace="preset"`。

`macro_script` 字段存储 YAML 字符串，格式如下：

```yaml
# applescript 示例
- type: action
  event_type: applescript
  source: desktop
  payload:
    script: "set volume with output muted"

# open_app 示例
- type: action
  event_type: open_app
  source: desktop
  payload:
    app_name: "WeChat"

# key_press 示例
- type: action
  event_type: key_press
  source: desktop
  payload:
    key: "Return"

# screenshot 示例
- type: action
  event_type: screenshot
  source: desktop
```

| # | name | trigger_patterns | macro_script event_type | payload |
|---|------|-----------------|----------------------|---------|
| 1 | mute | 静音, 别出声, 不要声音, 安静 | applescript | `set volume with output muted` |
| 2 | unmute | 取消静音, 恢复声音, 打开声音, 不静音了 | applescript | `set volume without output muted` |
| 3 | volume_up | 音量大一点, 调高音量, 大声一点, 声音大一点, 调大音量 | applescript | `set volume output volume ((output volume of (get volume settings)) + 10)` |
| 4 | volume_down | 音量小一点, 调低音量, 小声一点, 声音小一点, 调小音量 | applescript | `set volume output volume ((output volume of (get volume settings)) - 10)` |
| 5 | volume_max | 音量最大, 最大声, 声音调到最大, 最大音量 | applescript | `set volume output volume 100` |
| 6 | volume_mid | 音量一半, 音量中等, 声音一半 | applescript | `set volume output volume 50` |
| 7 | volume_min | 音量最小, 最小声 | applescript | `set volume output volume 0` |
| 8 | play_pause | 暂停, 继续播放, 开始播放, 继续, 接着放, 停一下, 别放了, 先停 | applescript | `tell application "System Events" to key code 16` |
| 9 | next_track | 下一首, 下一曲, 切歌, 换一首, 下首歌 | applescript | `tell application "System Events" to key code 17` |
| 10 | prev_track | 上一首, 上一曲, 回上一首, 上一首歌 | applescript | `tell application "System Events" to key code 15` |
| 11 | screenshot | 截图, 截屏, 屏幕截图, 截个图, 截一下屏 | screenshot | — |
| 12 | lock_screen | 锁屏, 锁定屏幕, 锁电脑, 锁一下 | applescript | `tell application "System Events" to keystroke "q" using command down` |
| 13 | open_wechat | 打开微信, 启动微信, 开一下微信 | open_app | `app_name: "WeChat"` |
| 14 | open_chrome | 打开Chrome, 启动Chrome, 开一下Chrome | open_app | `app_name: "Chrome"` |
| 15 | open_safari | 打开Safari, 启动Safari, 开一下Safari | open_app | `app_name: "Safari"` |
| 16 | open_terminal | 打开终端, 启动终端, 开一下终端 | open_app | `app_name: "Terminal"` |
| 17 | open_finder | 打开Finder, 打开访达, 开一下访达 | open_app | `app_name: "Finder"` |
| 18 | open_vscode | 打开VS Code, 打开VSCode, 启动VS Code | open_app | `app_name: "Visual Studio Code"` |
| 19 | quit_wechat | 退出微信, 关闭微信, 关掉微信 | applescript | `tell application "WeChat" to quit` |
| 20 | quit_chrome | 退出Chrome, 关闭Chrome, 关掉Chrome | applescript | `tell application "Chrome" to quit` |
| 21 | quit_safari | 退出Safari, 关闭Safari, 关掉Safari | applescript | `tell application "Safari" to quit` |
| 22 | press_enter | 按回车, 按一下回车, 按下回车 | key_press | `key: "Return"` |
| 23 | press_space | 按空格, 按一下空格, 按下空格 | key_press | `key: "Space"` |

> **quit_app 说明**：`macos_driver` 没有 `quit_app` 方法，`DesktopController` 没有 `close_app` 分支，`_execute_desktop_step()` 也没有 `close_app` 分支。因此退出应用必须通过 `applescript`（`tell application "X" to quit`），不能用 `close_app` event_type。

> **open_app 说明**：`open_app` 动作会启动应用或切到已运行的前台。"切到微信"由 `open_wechat` 覆盖，不需要独立的 focus Macro。

> **source: desktop**：是语音触发的硬性要求。Desktop 来源的 MacroStep 走 `_execute_desktop_step()`，DOM 来源走 `_execute_browser_step()`，必须明确指定。

### 23.6 匹配 → 执行完整流

```
用户说"静音"
  │
  ├── LocalMatcher.match("静音")
  │     → 命中 template {action: "macro:42", patterns: ["静音","别出声",...]}
  │     → return ("macro:42", {})
  │
  ├── voice_input.receive()
  │     → action.startswith("macro:") → True
  │     → _dispatch_macro(thread_id, macro_id=42, args={}, project_id)
  │
  ├── _dispatch_macro()
  │     → load_macro(42) → Macro(status=verified, is_active=True)
  │     → preflight(macro, {}) → MacroScript(steps=[...])
  │     → run_deterministic(macro, VOICE_POLICY)
  │       → _scan_steps_risk() → pass（VOICE_POLICY 不限制）
  │       → MacroEngine.execute(script)
  │         → _execute_desktop_step("applescript", payload.script)
  │           → DesktopController.execute(action="applescript", script="set volume with output muted")
  │             → macos_driver.run_applescript("set volume with output muted")
  │       → return (True, "AppleScript executed successfully.", None)
  │     → outcome = ExecutionOutcome(ok=True, message="...")
  │
  ├── _push_macro_result(thread_id, "done", "已静音")
  │     → WS voice.route_result {status:"done", summary:"已静音"}
  │     → Rust handle_route_result: status=="done" → TTS 播 "已静音"
  │     → Rust: session_state.force_set(Listening) → 准备下一轮
  │     → Python: state_machine.set(IDLE)
  │
  └── 返回 None（不走 Agent）
```

**内置命令流（end 为例）**：

```
用户说"再见"
  → LocalMatcher.match("再见") → ("end", {})
  → _handle_builtin(thread_id, "end", {})
  → _push_local_result(thread_id, "end", {})
  → WS voice.route_result {status:"routed", target:{type:"local", action:"end"}}
  → Rust: target.type=="local" → TTS 播通用确认语
  → Python: state_machine.set(IDLE)
```

### 23.7 TTS 确认语音频缓存

#### 问题

当前每次 TTS 播放都走完整合成链路：

| 引擎 | 链路 | 延迟 |
|------|------|------|
| 火山引擎 TTS | 实时对话 API → WS binary → ffplay | 200-500ms |

L0 确认语是固定文本集（"好的"/"搞定了"/"已静音"/"执行失败"），每次合成相同音频是纯浪费。缓存后 `afplay` 直接播本地文件，延迟 < 50ms。

#### 缓存设计

**插入点**：`voice_session.rs` 的 WS audio_frame 处理，在将 PCM 写入 ffplay stdin **之前**。

```
speak(text, lang)
  │
  ├── 构造 cache_key = hash(text + engine + voice + speed)
  ├── cache_dir = app_data_dir/tts_cache/
  ├── cache_path = cache_dir/{cache_key}.mp3
  │
  ├── 命中（文件存在且 size > 0）
  │     → play_audio(cache_path, afplay_child)
  │     → speaking = false → speak_next(lang)
  │     → return（跳过 TTS 引擎）
  │
  └── 未命中
        → 走原有 TTS 引擎合成
        → 合成成功后，将音频字节写入 cache_path
        → play_audio(cache_path, afplay_child)
        → return
```

**缓存 key**：

```rust
fn cache_key(text: &str, engine: TtsEngineKind, voice: &str, speed: f32) -> String {
    // SHA-256 of "edge-tts|zh-CN-XiaoxiaoNeural|1.0|已静音"
    let material = format!("{}|{}|{}|{}", engine.as_str(), voice, speed, text);
    sha256(material)
}
```

engine/voice/speed 参与 hash，确保切换引擎或音色时不会播错缓存。

**缓存目录**：`~/.evoloop/tts_cache/`（与 LanceDB 的 `~/.evoloop/vectors/` 同级）。

**缓存清理**：不做主动清理。23 条预置 Macro 的确认语 + 10 条内置确认语 + 通用错误语，合计约 35 条 × 2 语言 = 70 个文件，每个 < 50KB，总量 < 4MB。用户 Macro 的 summary 是动态文本，长尾有限。

**不影响 barge-in**：缓存命中的播放路径和未命中一样走 `play_audio()` + `afplay_child`，`stop()` 能正常 kill。

#### 受影响的缓存文本

| 来源 | 文本 | 数量 | 特点 |
|------|------|------|------|
| `resolve_confirmation()` | 好的/搞定了/嗯哼/没问题/好嘞/收到/可以了/行/OK/没问题了 | 10 条 × 2 语言 | 完全固定 |
| Macro done summary | 已静音/已取消静音/音量已调高/音量已调低/音量已最大/音量已一半/音量已最小/已暂停/已播放下一首/已播放上一首/截图已保存/已锁屏/已打开微信/已打开Chrome/已打开Safari/已打开终端/已打开Finder/已打开VS Code/已退出微信/已退出Chrome/已退出Safari/已按回车/已按空格 | 23 条 | 预置 Macro 固定 |
| Macro failed summary | 执行失败 | 1 条 | 固定 |
| Rust 内置错误 | 抱歉，处理出错了 | 1 条 × 2 语言 | 固定 |

首次播放后自动缓存，后续命中直接播放。

#### 改动

| 文件 | 改动 |
|------|------|
| `frontend/src-tauri/src/voice/tts_engine.rs` | `speak()` 方法增加缓存查表逻辑；各 `speak_*` 方法合成成功后写缓存文件 |

§23.8 中 `voice_session.rs` 仍不改——缓存逻辑在 `tts_engine.rs` 内部，`voice_session.rs` 的 `handle_route_result` 调用 `queue_sentence()` + `speak_next()` 的方式不变。

### 23.8 Macro 执行路径性能优化

#### 23.8.1 问题分析

完整执行路径逐环节延迟拆解（以"静音"为例）：

| 环节 | 耗时 | 说明 |
|------|------|------|
| WS + L0 match | ~2ms | 正则匹配 |
| `load_macro(42)` | ~3-5ms | DB 查询 by PK |
| `preflight()` YAML parse | ~1ms | 1-step YAML 解析 |
| **`activity_monitor.log_event()`** | **~5-15ms** | **每次 cache 往返 + event bus publish** |
| `DesktopController` setup | ~1ms | recorder 查找 |
| `review_applescript()` | ~0.5ms | 正则安全扫描 |
| `osascript` subprocess | ~50-100ms | 系统调用（不可减） |
| `_push_macro_result` WS | ~1ms | |
| Rust TTS (cached) | ~50ms | §23.7 缓存后 |
| **合计** | **~115-175ms** | |

以"打开微信"（open_app）为例：

| 环节 | 耗时 | 说明 |
|------|------|------|
| log_event | ~5-15ms | cache 往返 + event bus |
| get_bundle_id + is_dynamic_app | ~6-10ms | 2 次 DB 查询 |
| open subprocess | ~50-100ms | 系统调用 |
| **screenshot + get_current_app** | **~150-300ms** | **recording_func 触发截图子进程 + osascript** |
| **合计** | **~270-480ms** | **边界值** |

#### 23.8.2 嵌入式模式下的 cache 底层

系统在 `EMBEDDED_MODE=true` 时使用 `FileCache`（文件系统），不是 Redis：

```python
# infrastructure/cache/__init__.py:54
if settings.EMBEDDED_MODE:
    _cache_instance = FileCache()
else:
    _cache_instance = RedisCache()
```

`FileCache.lpush()` + `ltrim()` 的实现（`cache/file/_core.py:219-241`）：

```python
async def lpush(self, name, *values):
    data = self._read("lists", name)   # 文件读 JSON
    data.insert(0, value)
    self._write("lists", name, data)   # 文件写 JSON

async def ltrim(self, name, start, end):
    data = self._read("lists", name)   # 文件读 JSON
    trimmed = data[start:end]
    self._write("lists", name, trimmed)  # 文件写 JSON
```

**每次 `log_event` = 2 次文件读 + 2 次文件写**（lpush 读+写一次，ltrim 读+写一次），比 Redis 内存操作慢一个数量级。嵌入式模式下 `log_event` 的实际延迟为 **~10-30ms**，而非 Redis 的 ~5-15ms。

#### 23.8.3 三个性能硬伤

**硬伤 1：`activity_monitor.log_event()` — 每个 step 做 cache 往返 + event bus publish**

`engine/__init__.py:132`：
```python
await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
```

`activity.py:352-370`：
```python
pipe = cache.pipeline()
pipe.lpush(f"system:logs:{event_type}", payload.model_dump_json())
pipe.ltrim(f"system:logs:{event_type}", 0, 99)
await pipe.execute()            # cache 往返（Redis ~5-15ms / FileCache ~10-30ms）
await system_bus.publish(...)   # event bus publish
```

语音用户不需要在活动流里看到 "Execute Macro Step 1: applescript"。对 1-step 预置 Macro 影响 5-30ms，对 N-step 用户 Macro 影响 N × 5-30ms。

**硬伤 2：`open_app` / `key_press` 的 recording_func 截图**

`desktop/__init__.py:96`：
```python
recording_ctx = RecordingContext(
    screenshot_actions=("click", "double_click", "type_text", "key_press", "open_app", "drag_drop")
)
```

`open_app` 和 `key_press` 在 `screenshot_actions` 中，执行完动作后调 `recording_func()`，触发：
- `macos_driver.screenshot()` — `screencapture -x` 子进程，~100-200ms
- `_get_cached_app_info()` → `macos_driver.get_current_app()` — osascript 子进程，~50-100ms

语音预置 Macro 不需要录制截图。这 150-300ms 是纯浪费。

`applescript` 和 `screenshot` 不在 `screenshot_actions` 中，不受影响。

**硬伤 3：无 MacroScript 解析缓存**

每次 `preflight()` 都调 `MacroScript.from_yaml(macro.macro_script)` 重新解析 YAML。对 1-step 预置 Macro ~1ms，对 20-step 用户 Macro ~5-10ms。`load_macro()` 也无缓存，每次 L0 命中都做 DB 查询。

#### 23.8.4 优化方案

**优化 1：跳过 activity log（voice 路径）**

`MacroEngine.execute()` / `execute_steps()` / `_execute_steps_inner()` 新增 `skip_activity_log: bool = False` 参数。`run_deterministic()` 在 `policy` 为 `VOICE_POLICY` 时传 `True`。

```python
# engine/__init__.py _execute_steps_inner
if not skip_activity_log:
    await activity_monitor.log_event("macro_thought", {"text": desc}, thread_id)
logger.info(f"[{thread_id}] {desc}")  # 日志保留，只是不写 cache + 不发 event
```

`logger.info` 保留——本地日志几乎零成本，去掉只影响调试。

**优化 2：跳过 recording 截图（voice 路径）**

`DesktopController.execute()` 新增 `skip_recording: bool = False` 参数。

```python
# desktop/__init__.py execute()
recorder = None
if not skip_recording:
    session_id = ContextManager.get_var("thread_id")
    if session_id:
        recorder = get_recorder(session_id)

recording_ctx = RecordingContext(
    platform="macos",
    recorder=recorder,  # None 时 record() 为 no-op
    screenshot_actions=(...) if not skip_recording else (),
)
```

`_execute_desktop_step()` 新增 `skip_recording` 参数并透传。`MacroEngine` 在 `skip_activity_log=True` 时同时传 `skip_recording=True`。

**优化 3：MacroScript 内存缓存**

`runner.py` 新增模块级缓存：

```python
_SCRIPT_CACHE: dict[int, tuple[str, MacroScript]] = {}  # {macro_id: (updated_at, script)}

def _get_cached_script(macro: Macro) -> MacroScript:
    cached = _SCRIPT_CACHE.get(macro.id)
    if cached and cached[0] == macro.updated_at.isoformat():
        return cached[1]
    script = MacroScript.from_yaml(macro.macro_script)
    _SCRIPT_CACHE[macro.id] = (macro.updated_at.isoformat(), script)
    return script
```

`preflight()` 改用 `_get_cached_script(macro)` 而非每次 `MacroScript.from_yaml()`。`updated_at` 变化时自动失效。

`load_macro()` 加进程内缓存同理，用 `(macro_id, updated_at)` 做 key，命中跳过 DB 查询。Macro 更新时通过生命周期事件清缓存。

#### 23.8.5 优化后延迟估算

"静音"（applescript）：

| 环节 | 优化前 | 优化后 |
|------|--------|--------|
| log_event | ~5-30ms | **0ms** |
| MacroScript parse | ~1ms | **0ms**（缓存） |
| load_macro DB | ~3-5ms | **0ms**（缓存） |
| osascript | ~50-100ms | ~50-100ms |
| TTS (cached) | ~50ms | ~50ms |
| **合计** | ~115-175ms | **~105-160ms** |

"打开微信"（open_app）：

| 环节 | 优化前 | 优化后 |
|------|--------|--------|
| log_event | ~5-30ms | **0ms** |
| screenshot + get_current_app | ~150-300ms | **0ms** |
| get_bundle_id + is_dynamic_app | ~6-10ms | ~6-10ms |
| open subprocess | ~50-100ms | ~50-100ms |
| TTS (cached) | ~50ms | ~50ms |
| **合计** | ~270-480ms | **~110-170ms** |

"按回车"（key_press）：

| 环节 | 优化前 | 优化后 |
|------|--------|--------|
| log_event | ~5-30ms | **0ms** |
| screenshot | ~100-200ms | **0ms** |
| key_press subprocess | ~50-100ms | ~50-100ms |
| TTS (cached) | ~50ms | ~50ms |
| **合计** | ~200-350ms | **~105-160ms** |

所有预置 Macro 的端到端延迟降至 **~105-170ms**，用户无等待感。

#### 23.8.6 改动清单

| 文件 | 改动 | 原方案标记 |
|------|------|----------|
| `execution/macro/engine/__init__.py` | `execute()`/`execute_steps()`/`_execute_steps_inner()` 新增 `skip_activity_log` 参数 | 原标"不改"→**需改** |
| `execution/macro/runner.py` | `run_deterministic()` 传 `skip_activity_log=True`；新增 `_get_cached_script()` + `load_macro` 缓存 | 原已需改 |
| `execution/macro/engine/_executors.py` | `_execute_desktop_step()` 新增 `skip_recording` 参数并透传 | 原标"不改"→**需改** |
| `environment/controllers/desktop/__init__.py` | `execute()` 新增 `skip_recording` 参数，为 True 时 recorder=None + screenshot_actions=() | 原标"不改"→**需改** |

所有新增参数默认 `False`，不影响现有 web 路径。

### 23.9 健壮性保障

#### 23.9.1 Macro 作用域：全局 + 当前项目

Macro 加载范围通过 `SharedState.project_id` 动态过滤：

```sql
SELECT * FROM macros
WHERE is_active = True AND status = 'verified'
  AND (project_id IS NULL OR project_id = :current_project_id)
```

- 预置 Macro（`project_id=NULL`）：始终加载
- 当前项目用户 Macro：加载
- 其他项目 Macro：不加载

项目切换时 `shared_state.set("project_id", ...)` 触发 `StateChangedEvent`，subscriber 调 `rebuild_local_matcher()` 重建 L0 matcher，加载新项目的 Macro。

#### 23.9.2 Trigger 冲突去重

DB 查询排序 `preset 优先 → created_at ASC`：

```python
stmt = select(Macro).where(...).order_by(
    # preset 优先（namespace="preset" 排在最前）
    case((Macro.namespace == "preset", 0), else_=1),
    Macro.created_at.asc(),
)
```

加载时维护 `seen_patterns: set[str]`：

```python
if pattern in seen_patterns:
    logger.warning("trigger '%s' skipped (macro %d, already bound)", pattern, macro.id)
    continue
seen_patterns.add(pattern)
```

同 pattern 只保留第一条（预置优先），冲突项跳过并 warn。

#### 23.9.3 执行超时保护

`_dispatch_macro` 用 `asyncio.wait_for(task, timeout=5.0)` 包裹 `run_deterministic()`：

- 正常 1-step applescript ~100ms，5 秒绰绰有余
- 多步 Macro 也能在 5 秒内完成
- 超时推 `failed "执行超时"`
- 防止 osascript 弹系统对话框（如 `tell application "WeChat" to quit` 触发确认弹窗）导致语音路径卡死

#### 23.9.4 Barge-in 支持

`_dispatch_macro` 将 `run_deterministic()` 包装为 `asyncio.create_task` 并注册到 `worker_registry`：

```python
task = asyncio.create_task(_run())
await self._worker_registry.register_worker(thread_id, task, description=f"macro:{macro_id}")
```

用户在 Macro 执行期间说话 → Rust 检测 → 发 `voice.barge_in` → Python `executor.cancel_voice_task(thread_id)` → `worker_registry.cancel_worker(thread_id)` → `task.cancel()` → `_dispatch_macro` 捕获 `CancelledError` → 推 `cancelled "已取消"`。

#### 23.9.5 已知限制

| 限制 | 影响 | 后续方案 |
|------|------|---------|
| barge-in 后子进程泄漏 | `osascript` 被 cancel 但子进程仍在后台运行，直到自身 timeout（30s）退出 | 改 `macos_driver.run_applescript` 用 `subprocess.Popen` + 手动 wait，cancel 时 kill |
| voice_ws.py 锁阻塞 barge-in | `_dispatch_macro` 持有 voice_ws.py 的锁，`voice.barge_in` 消息被阻塞到 Macro 执行完才处理。1-step 预置 Macro ~100ms 不受影响，多步用户 Macro 实际依赖 5 秒超时兜底 | `_dispatch_macro` 改为无锁异步执行，或 barge-in 消息走独立锁 |
| 5 秒超时对复杂多步 Macro 不够 | 超过 5 秒的 Macro 被截断 | 后续按 step 数动态调整 timeout |
| 预置 Macro `quit_app` 弹系统确认框 | `tell application "WeChat" to quit` 可能触发 macOS 确认对话框 | 用 `kill` 命令替代（但绕过安全审查） |

### 23.10 安全后置（后续迭代）

| 安全措施 | 优先级 | 方案 |
|---------|--------|------|
| applescript 安全审查 | P1 | 复用 `ScriptGate.review_applescript()` |
| VOICE_POLICY family 限制 | P2 | 限定 `applescript` 在白名单内 |
| 用户 Macro 审查 | P3 | 验证后才允许语音触发 |

### 23.11 实现完整度

#### 已完成（可跑通）

| # | 文件 | 改动内容 | 状态 |
|---|------|---------|------|
| 1 | `execution/macro/runner.py` | `VOICE_POLICY` 放开 family/risk；`_get_cached_script()` MacroScript 缓存；`load_macro` 进程内缓存（带 `updated_at` 失效）；`invalidate_macro_cache()` 缓存失效函数；`run_deterministic` 透传 `skip_activity_log` + `skip_recording` | ✅ |
| 2 | `environment/controllers/desktop/__init__.py` | `execute()` 新增 `skip_recording: bool = False`，为 True 时 recorder=None + screenshot_actions=() | ✅ |
| 3 | `execution/macro/engine/_executors.py` | `_execute_desktop_step()` 新增 `skip_recording` 参数，透传到所有 8 个 `DesktopController.execute()` 调用 | ✅ |
| 4 | `execution/macro/engine/__init__.py` | `execute()`/`execute_steps()`/`_execute_steps_inner()` 新增 `skip_activity_log` + `skip_recording` 参数；`log_event` 在 `skip_activity_log=True` 时跳过，`logger.info` 保留 | ✅ |
| 5 | `routing/sync.py` | `_LOCAL_DESC` 删除 13 条系统 action 描述，新增 `ack`/`cancel` | ✅ |
| 6 | `routing/init_spec.py` | `_TEMPLATES` 保留 5 条 Evoloop 内置命令（clarify/rename/end/ack/cancel）；`_VOICE_LOCAL_ACTIONS` 保留 7 条；删除 `_KEY_DICT`/`_DELTA_DICT`；删除 `ActionRegistry` 导入；`_registry_actions()` 返回空；`slot_dictionaries` 只保留 `app`；新增 `enrich_spec_with_macro_triggers()`（SharedState 作用域过滤 + `case()` preset 优先排序 + `seen_patterns` 去重 + `{{slot}}` → `{slot}` 转换 + 准确的 `added` 计数日志） | ✅ |
| 7 | `routing/router.py` | `_get_local_matcher()` 追加 `enrich_spec_with_macro_triggers()` 调用；新增 `rebuild_local_matcher()` | ✅ |
| 8 | `channel/input/voice_input.py` | `receive()` L0 命中分流（`macro:` vs builtin）；`_dispatch_macro()`（load_macro → preflight → task → worker_registry → `wait_for(timeout=5s)` → push done/failed/cancelled + `skip_activity_log=True` + `skip_recording=True`）；`_push_macro_result()`；`_handle_builtin()`（`ack` no-op、`cancel` 取消 worker + TTS、`rename` 写 shared_state、`end`/`clarify` 走 TTS 确认）；`_push_local_result()` 保留 | ✅ |
| 9 | `project/event/subscribers.py` | `on_project_switched()` 新增 `rebuild_local_matcher()` 调用 | ✅ |
| 10 | `execution/macro/event/subscribers.py` | 新增 `MacroL0MatcherSubscriber`，监听 `MACRO_CREATED`/`MACRO_UPDATED`/`MACRO_DELETED`/`MACRO_OBSOLETED` → `invalidate_macro_cache(macro_id)` + `rebuild_local_matcher()` | ✅ |
| 11 | `routing/executor.py` | **新建**：`push_voice_result()`/`push_voice_token()`/`push_voice_tts_boundary()`（使用 `VOICE_TTS_BOUNDARY` 消息类型）；`get_thread_lock()` per-thread 锁；`cancel_voice_task()` via worker_registry；`mark_voice()`/`consume_voice()` 状态跟踪；全局变量 `manager`/`envelope_fn`/`message_type` 由 `voice_ws.py` 注入 | ✅ |
| 12 | `api/routes/voice_ws.py` | `_ensure_voice_input()` 中注入 `executor.manager`/`envelope_fn`/`message_type` | ✅ |
| 13 | `scripts/seed_preset_macros.py` | **新建**：23 条预置 Macro 种子数据脚本（幂等，重复运行跳过已存在的）；初始化 `db_resource_manager` | ✅ **已入库** |
| 14 | `frontend/src-tauri/src/voice/voice_session.rs` | WS audio_frame 写缓存（`~/.evoloop/tts_cache/`，key=hash(text)） | ✅ |
| 15 | `tests/routing/test_l0_macro_matching.py` | **新建**：30 条 L0 匹配测试（builtin 5 条 + Macro 15 条 + prefix/suffix 4 条 + no-match 4 条 + edge case 2 条） | ✅ 30/30 通过 |

#### 未实现（后续迭代）

| # | 内容 | 状态 | 说明 |
|---|------|------|------|
| 1 | §23.10 安全后置 | **有意推迟** | applescript 审查、VOICE_POLICY family 限制、用户 Macro 审查 |

| 3 | `end` 关闭语音会话 | **部分实现** | 当前只推 TTS 确认（"再见"），不主动关闭 WS。前端 React 监听 `voice:route_result` 中 `action:"end"` 可自行关闭 |
| 4 | `clarify` 重播 TTS | **部分实现** | 当前只推 TTS 确认，不重播上一次内容。需 Rust 侧新增 `voice.clarify` 消息处理 |

#### 已知限制

| 限制 | 影响 | 后续方案 |
|------|------|---------|
| barge-in 后子进程泄漏 | `osascript` 被 cancel 但子进程仍在后台运行，直到自身 timeout（30s）退出 | 改 `macos_driver.run_applescript` 用 `subprocess.Popen` + 手动 wait，cancel 时 kill |
| voice_ws.py 锁阻塞 barge-in | `_dispatch_macro` 持有 voice_ws.py 的锁，`voice.barge_in` 消息被阻塞到 Macro 执行完才处理。1-step 预置 Macro ~100ms 不受影响，多步用户 Macro 实际依赖 5 秒超时兜底 | `_dispatch_macro` 改为无锁异步执行，或 barge-in 消息走独立锁 |
| 5 秒超时对复杂多步 Macro 不够 | 超过 5 秒的 Macro 被截断 | 后续按 step 数动态调整 timeout |
| 预置 Macro `quit_app` 弹系统确认框 | `tell application "WeChat" to quit` 可能触发 macOS 确认对话框 | 用 `kill` 命令替代（但绕过安全审查） |
| `end` 不主动关闭 WS | 用户说"再见"后 WS 仍保持连接 | 前端 React 监听 `action:"end"` 关闭会话，或 Python 推 `voice.session_end` 消息 |

#### 不受影响的模块

| 模块 | 说明 |
|------|------|
| `routing/local_matcher.py` | 匹配引擎不变 |
| `routing/index.py` / `retriever.py` | L1 嵌入索引不变 |
| `routing/schemas.py` | 数据类型不变 |
| `frontend/src-tauri/src/voice/voice_session.rs` | **不改**。Macro 结果走 `status:"done"/"failed"/"cancelled"` + `summary`，复用 Rust 现有分支；内置命令走 `target.type:"local"`，复用现有 local 分支。TTS 缓存在 `tts_engine.rs` 内部，对 `voice_session.rs` 透明 |
| `environment/capabilities/registry.py` | 不改。`applescript` 已注册为 desktop action |
| `execution/macro/schemas.py` | 不改。直接用现有 `applescript` action type |
| `execution/macro/service.py` | 不改。`MacroService.run()` 仍由 web 路径调用 |
| `core/shared_state.py` | 不改。读取 `project_id`；`rename` 写入 `agent_name`（新 key，不覆盖已有） |
| Agent 图 / 路由 / 编排 | 不改。L0 不命中才走 Agent |
| Macro 录制 / 合成流程 | 不改 |

#### 跑通步骤

```bash
# 1. 插入预置 Macro 种子数据（首次运行，幂等）
cd evoloop/backend && uv run python scripts/seed_preset_macros.py

# 2. 运行测试验证匹配
uv run pytest tests/routing/test_l0_macro_matching.py -v

# 3. 启动后端（L0 matcher 自动预热）
bin/evo dev

# 4. 启动 Tauri 前端（TTS 缓存自动生效）
cd frontend && pnpm tauri dev

# 5. 语音测试：说"静音" → L0 命中 mute Macro → osascript 静音 → TTS 播"已静音"
```

### 23.12 实际实现的完整语音链路

#### 链路总览

```
用户说话
  │
  ▼
┌─────────────────────── Rust (Tauri) ───────────────────────┐
│ 麦克风 → VAD → ASR → 文本                                    │
│   ↓                                                          │
│ WS voice.route {thread_id, text, message_id}                 │
│   ↓                                                          │
│ State: Listening → Processing                                │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────── Python WS 入口 ──────────────────────┐
│ voice_ws.py /ws handler                                      │
│   ├── system.init 握手（首次连接，推送 configs + state）       │
│   ├── voice.route → asyncio.create_task(_handle_route)       │
│   ├── voice.barge_in → _handle_barge_in                      │
│   ├── voice.partial → _handle_partial (L1 preheat)           │
│   ├── voice.start / voice.stop (状态控制)                     │
│   ├── voice.dictation.finalize → LLM 润色                    │
│   └── voice.cancel → executor.cancel_voice_task              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────── _handle_route ───────────────────────┐
│ 1. executor.get_thread_lock(thread_id) — 串行化              │
│ 2. _ensure_voice_input() — 首次绑定 voice_input + executor   │
│ 3. shared_state.get("project_id") — 读当前项目                │
│ 4. EvoContext.set(thread_id, project_id) — 上下文绑定         │
│ 5. manager.bind_thread(thread_id, conn_id) — WS 绑定          │
│ 6. voice_state_machine.set(PROCESSING)                        │
│ 7. is_duplicate(message_id) — 幂等检查                        │
│ 8. voice_input.receive(body) → IncomingMessage | None        │
│    ├── None (L0 命中) → return                                │
│    └── IncomingMessage (L0 未命中) → 继续                      │
│ 9. voice_input.dispatch(msg) → dispatch_agent_run             │
│ 10. voice_input.post_dispatch(msg, result) → 注册 worker      │
│ 11. 锁释放                                                    │
│ 12. voice_input.await_and_finalize(thread_id, task)           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────── voice_input.receive() ───────────────────────┐
│                                                              │
│  matcher = await _get_local_matcher()                        │
│  l0_match = matcher.match(text)                              │
│                                                              │
│  ├── l0_match is not None:                                   │
│  │   ├── action.startswith("macro:")                         │
│  │   │   → _dispatch_macro(thread_id, macro_id, args)        │
│  │   │     ├── state → SPEAKING                               │
│  │   │     ├── load_macro(id) — 缓存命中 / DB 查询             │
│  │   │     ├── preflight(macro, args) — 缓存命中 / YAML parse │
│  │   │     ├── asyncio.create_task(run_deterministic)         │
│  │   │     ├── worker_registry.register_worker                │
│  │   │     ├── asyncio.wait_for(task, timeout=3.0)            │
│  │   │     │   ├── run_deterministic:                         │
│  │   │     │   │   ├── _collect_sources → 检查来源             │
│  │   │     │   │   ├── _scan_steps_risk → 检查风险（当前不限）  │
│  │   │     │   │   ├── 快路径: MacroEngine.execute(             │
│  │   │     │   │   │     skip_activity_log=True,               │
│  │   │     │   │   │     skip_recording=True)                  │
│  │   │     │   │   │   ├── _execute_steps_inner:               │
│  │   │     │   │   │   │   └── _execute_desktop_step(          │
│  │   │     │   │   │   │       skip_recording=True)            │
│  │   │     │   │   │   │       → DesktopController.execute(    │
│  │   │     │   │   │   │           skip_recording=True)        │
│  │   │     │   │   │   │         → macos_driver.run_applescript│
│  │   │     │   │   │   │         / open_app / key_press / ...  │
│  │   │     │   │   ├── 成功 → ExecutionOutcome(True, msg)       │
│  │   │     │   │   └── 失败 → _run_with_self_heal (Agent 自愈) │
│  │   │     │   ├── TimeoutError → push "failed" "执行超时"      │
│  │   │     │   ├── CancelledError → push "cancelled" "已取消"   │
│  │   │     │   └── 成功 → push "done" summary                  │
│  │   │     └── _push_macro_result → WS voice.route_result     │
│  │   │       {status:"done"/"failed"/"cancelled", summary}    │
│  │   │       → state → IDLE                                   │
│  │   │                                                        │
│  │   └── builtin (end/clarify/rename/ack/cancel)              │
│  │       ├── ack → no-op + _push_local_result                 │
│  │       ├── cancel → worker_registry.cancel_worker            │
│  │       │   ├── 有 worker → push "cancelled" "已取消"          │
│  │       │   └── 无 worker → push "done" "没有正在执行的任务"    │
│  │       ├── rename → shared_state.set("agent_name", name)    │
│  │       └── end/clarify → _push_local_result                 │
│  │         → WS voice.route_result                            │
│  │           {status:"routed", target:{type:"local",action}}  │
│  │         → state → IDLE                                     │
│  │                                                            │
│  └── l0_match is None (L0 未命中):                             │
│      → 构建 IncomingMessage(source="voice", ...)              │
│      → 检查 running_worker → 附带 metadata                     │
│      → return IncomingMessage                                 │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────── Agent 路径 (L0 未命中) ──────────────────────┐
│                                                              │
│ voice_input.dispatch(msg):                                   │
│   ├── state → SPEAKING                                       │
│   ├── executor._mark_voice(thread_id, "agent")               │
│   └── super().dispatch(msg) → dispatch_agent_run(            │
│         thread_id, message_content, project_id, ...)          │
│       → Agent 引擎启动 (Supervisor → Worker → Tool)           │
│       → 返回 DispatchResult                                   │
│                                                              │
│ voice_input.post_dispatch(msg, result):                      │
│   ├── result.status == "failed"                              │
│   │   → executor.consume_voice                               │
│   │   → executor.push_voice_result("failed", error)          │
│   │   → return None                                           │
│   └── result.status == "ok"                                  │
│       → asyncio.create_task(run_agent_background(inputs))    │
│       → worker_registry.register_worker(thread_id, task)     │
│       → return {task, old_worker_task}                        │
│                                                              │
│ (锁释放后)                                                    │
│ voice_input.await_and_finalize(thread_id, task):             │
│   ├── await task (Agent 在后台运行)                           │
│   │   ├── Agent 流式输出 token → VoiceChannel                 │
│   │   │   → executor.push_voice_token → WS voice.token       │
│   │   ├── Agent 句子边界 → VoiceChannel                       │
│   │   │   → executor.push_voice_tts_boundary                  │
│   │   │   → WS voice.tts_boundary                            │
│   │   ├── Agent ack (Supervisor "好的，我来处理")              │
│   │   │   → VoiceChannel → executor.push_voice_result         │
│   │   │   → WS voice.route_result {routed, summary}           │
│   │   ├── Agent 完成 → SessionCompletedEvent                  │
│   │   │   → VoiceChannel → executor.push_voice_result         │
│   │   │   → WS voice.route_result {done, summary}            │
│   │   └── Agent 失败 → AgentRunCompletedEvent                 │
│   │       → VoiceChannel → executor.push_voice_result         │
│   │       → WS voice.route_result {failed, summary}          │
│   │                                                          │
│   ├── CancelledError (barge-in)                              │
│   │   → handle_cancelled → push "cancelled"                  │
│   └── 正常完成 → 重新注册 old_worker（如存活）                  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────── Rust 接收 ───────────────────────────┐
│                                                              │
│ WS receive loop → VoiceEnvelope → handler:                   │
│                                                              │
│ voice.route_result:                                          │
│   ├── status="routed" + target.type="local"                  │
│   │   → resolve_confirmation(action) → TTS 播确认语           │
│   │     "好的"/"搞定了"/"收到" 等（TTS 缓存命中 < 50ms）      │
│   ├── status="routed" + 无 target                             │
│   │   → TTS 播 summary（Agent ack 文本）                      │
│   ├── status="done"                                          │
│   │   → TTS 播 summary（"已静音"/"完成" 等）                   │
│   │   → state → Listening（准备下一轮）                        │
│   ├── status="failed"                                        │
│   │   → TTS 播 "抱歉，处理出错了"                              │
│   │   → state → Listening                                    │
│   └── status="cancelled"                                     │
│       → state → Listening                                    │
│                                                              │
│ voice.token:                                                 │
│   → event_bus.emit("voice:token") — 前端显示流式文本           │
│                                                              │
│ voice.tts_boundary:                                          │
│   → state → Speaking                                         │
│   → TTS queue_sentence + speak_next（流式播放，TTS 缓存）      │
│   → event_bus.emit("voice:tts_boundary")                     │
│                                                              │
│ system.config_changed:                                       │
│   → 广播到所有连接                                             │
│                                                              │
│ system.state_changed:                                        │
│   → 广播到所有连接                                             │
└──────────────────────────────────────────────────────────────┘
```

#### 状态机流转

```
IDLE → voice.start → LISTENING
LISTENING → voice.route → PROCESSING
PROCESSING → L0 命中 → IDLE (内置) / SPEAKING (Macro 执行中)
PROCESSING → L0 未命中 → SPEAKING (Agent 开始)
SPEAKING → done/failed/cancelled → LISTENING
SPEAKING → barge-in → INTERRUPTED
INTERRUPTED → 下一轮 voice.route → PROCESSING
LISTENING → voice.stop → IDLE
```

#### Barge-in 链路

```
用户说话（TTS 播放中）
  │
  ▼
Rust VAD 检测到语音活动
  ├── tts.stop() — 杀死 afplay 子进程
  ├── state → INTERRUPTED
  └── ws.send_barge_in(thread_id)
      │
      ▼
Python voice_ws.py
  └── voice.barge_in → _handle_barge_in(thread_id)
      ├── executor.get_thread_lock(thread_id) — 获取锁
      │   ⚠️ 如果 _handle_route 持有锁（Macro 执行中），此处阻塞
      ├── executor.cancel_voice_task(thread_id)
      │   └── worker_registry.cancel_worker(thread_id)
      │       └── task.cancel() → CancelledError 传播
      │           ├── _dispatch_macro 捕获 → push "cancelled"
      │           └── await_and_finalize 捕获 → handle_cancelled
      └── state → INTERRUPTED
```

#### E2E 性能实测

| 指标 | 数值 | 说明 |
|------|------|------|
| 内置命令 | 1-2ms | regex 匹配 + WS push |
| Macro 匹配 | < 1ms | regex 锚定匹配 |
| Macro 执行端到端 | **85ms 平均** | 含 osascript 子进程 |
| 首次请求（预热后） | 169ms | 含首次 MacroScript parse |
| 后续请求 | 88-300ms | osascript 执行时间波动 |
| 超时回收 | 3s | `_MACRO_TIMEOUT` |
| TTS 缓存命中 | < 50ms | `afplay` 本地文件 |
| 48 条 E2E 测试 | 40 通过 / 8 预期失败 | open_app 类无对应应用 |

### 23.13 非目标（更新）

| 原始非目标 | 状态 | 说明 |
|-----------|------|------|
| 不引入端到端语音大模型 | ❌ **已过时** | Seeduplex 已上线 API，§24 设计接入方案 |
| 不替代现有文本路由逻辑 | ✅ 仍有效 | Seeduplex 替代 ASR+TTS，不替代 L0/Agent |
| 语音仍是 Agent 的一个通道 | ✅ 仍有效 | Seeduplex 的 ASRResponse 进入现有 L0/Agent 链路 |

---

## 24. 端到端语音大模型（Seeduplex）集成设计

### 24.1 动机

豆包端到端实时语音模型 3.0（Seeduplex）是火山引擎提供的原生全双工语音大模型。与传统 ASR+LLM+TTS 拼接路径相比：

| 维度 | 当前拼接路径 | Seeduplex 端到端 |
|------|------------|-----------------|
| 端到端延迟 | ASR ~500ms + LLM ~2s + TTS ~500ms = **~3s** | 首字 **~500ms** |
| 全双工 | Rust VAD 模拟打断 | 原生 ASRInfo 事件，模型理解语音状态 |
| 自然度 | 文本 LLM 回复偏书面 | 原生语音模型，语气/节奏更自然 |
| 语种 | 中文为主 | 中英双语原生支持 |

**Seeduplex 不废弃现有路径**——当前链路作为备用（fallback），Seeduplex 可用时走端到端，不可用时降级到 ASR+LLM+TTS。

### 24.2 架构：三层语音路径

```
用户说话
  │
  ├── L0 匹配（无模型，即时响应） ← 始终优先
  │     → 静音/截图/媒体控制等 85ms
  │     → 不经任何模型，纯 regex + Macro
  │
  ├── Seeduplex 端到端路径 ← 可用时为主路径
  │     → PCM 音频 → Seeduplex
  │     │
  │     ├── ASRResponse {text, is_interim=false}
  │     │     → voice.route → L0 匹配
  │     │       ├── 命中 → 执行 → ChatTTSText("已静音") → TTSResponse
  │     │       └── 未命中 → Agent → reply text → ChatTTSText → TTSResponse
  │     │
  │     ├── ASRInfo → 打断标记（当前 TTS 打断信号）
  │     └── TTSResponse {audio (PCM 24kHz)} → resample 44.1kHz → afplay
  │
  └── ASR+LLM+TTS 拼接路径 ← 备选降级
        → 当前完整链路，Seeduplex 不可用时
```

L0 始终优先，不经任何模型。

### 24.3 Seeduplex 协议要点

基于火山引擎 API 文档（`/docs/6561/1594356`）：

| 项目 | 值 |
|------|----|
| 连接 | `wss://openspeech.bytedance.com/api/v3/realtime/dialogue` |
| 鉴权 | `X-Api-App-ID` + `X-Api-Access-Key` + `X-Api-Resource-Id` |
| 音频输入 | PCM 16kHz 16bit mono |
| 音频输出 | OGG Opus（可配置 PCM 24kHz） |
| 模式 | server_vad |
| 全双工 | 支持边发边收 |

**关键事件**：

| 事件 | 方向 | 用途 |
|------|------|------|
| `StartSession` | → 模型 | 初始化对话（人设、系统角色、说话风格） |
| `StartSession.tts.audio_config` | → 模型 | 配置音频格式为 `pcm 24kHz`（避免 OGG 解码开销） |
| `TaskRequest` | → 模型 | 音频流 |
| `ASRResponse` | 模型 → | ASR 文本（`is_interim=true` 中间态 / `false` 终态） |
| `ASRInfo` | 模型 → | 检测到语音，可用于打断当前 TTS |
| `ASREnded` | 模型 → | 用户说话结束 |
| `ChatResponse` | 模型 → | 模型聊天文本 |
| `TTSResponse` | 模型 → | 音频流输出（PCM 24kHz Float32）→ 经 `resample_rubato` 降采样到 44.1kHz → `afplay` |
| `ChatTTSText` | → 模型 | **注入自定义文本合成音频**（关键接口） |
| `TTSEnded` | 模型 → | 音频合成结束 |

`ChatTTSText` 是集成核心：L0 执行结果、Agent 回复文本都通过它注入模型，模型合成自然语音返回。

### 24.4 Rust 侧新模块：SeeduplexClient

新增 `frontend/src-tauri/src/voice/seeduplex_client.rs`：

```rust
pub struct SeeduplexClient {
    ws: WebSocket,
    session_id: String,
    app_id: String,
    access_key: String,
    afplay_child: Arc<Mutex<Option<std::process::Child>>>,
}

impl SeeduplexClient {
    /// 连接火山引擎并 StartSession
    pub async fn connect(app_id: &str, access_key: &str) -> Result<Self>;

    /// 发送 PCM 音频帧（麦克风实时数据 16kHz 16bit mono）
    /// VAD 回调调用，持续流式发送
    pub async fn send_audio(&self, pcm: &[u8]);

    /// 注入文本让模型合成音频（L0/Agent 结果）
    pub async fn inject_tts(&self, text: &str);

    /// 接收事件循环（独立 tokio task），处理服务端响应：
    ///   ASRResponse → event_bus.emit("voice:asr_result", text)
    ///   TTSResponse → afplay（配置 PCM 格式，降采样到 44.1kHz）
    ///   ASRInfo     → barge-in
    pub async fn receive_loop(&self, event_bus: &dyn VoiceEventBus);
}
```

**并发模型**：`send_audio` 和 `receive_loop` 是两条独立的 tokio task：

```
VAD 回调 task（持续发送）:
  mic_pcm → send_audio() → Seeduplex WS（发送方向）

receive_loop task（常驻接收）:
  Seeduplex WS（接收方向）→ ASRResponse / TTSResponse / ASRInfo
                               → 事件分发 + afplay
```

`send_audio` 由 VoiceSession 的 VAD 回调调用（每次有音频帧就发）。`receive_loop` 在 `tokio::spawn` 中独立运行，不阻塞发送。

**音频格式**：`StartSession` 时配置 `tts.audio_config.format = "pcm"`（文档 §1 产品约束第 3 条），Seeduplex 返回 PCM 24kHz Float32（直接可用）；`afplay` 需要 44.1kHz，用已有 `resample_rubato` 降采样后播放。

**事件分发**：

| Seeduplex 事件 | Rust → Python | 处理 |
|---------------|---------------|------|
| `ASRResponse{text, is_interim=false}` | `voice.route{text}` | L0 匹配 / Agent |
| `ASRResponse{text, is_interim=true}` | `voice.partial{text}` | L1 preheat |
| `ASRInfo` | `voice.barge_in{thread_id}` | 打断当前 TTS |
| `TTSResponse{audio}` | — | `afplay` 直接播放 |
| `ChatResponse{content}` | `voice.route{content}` | 纯对话场景走 L0/Agent |
| 收到 `voice.tts_play` | **Python → Rust** | 调 `inject_tts(text)` |

### 24.5 Python 侧新增：VOICE_TTS_PLAY MessageType + voice.tts_play 信令

先加 `MessageType` 枚举值（`canonical.py`）：

```python
class MessageType(str, Enum):
    ...
    VOICE_TTS_PLAY = "voice.tts_play"  # Python → Rust：推文本给 Seeduplex ChatTTSText 合成
```

新增 WS 信令 `voice.tts_play`。Python 将 L0 执行结果 / Agent 回复文本推给 Rust 侧，Rust 通过 `ChatTTSText` 注入 Seeduplex 合成语音。

```json
{
  "type": "voice.tts_play",
  "body": { "thread_id": "...", "text": "已静音" }
}
```

`executor.py` 新增：

```python
async def push_tts_text(thread_id: str, text: str) -> None:
    """推文本给 Rust，通过 Seeduplex ChatTTSText 合成 TTS。"""
    if manager is None:
        return
    body = {"thread_id": thread_id, "text": text}
    env = envelope_fn("voice.tts_play", body)
    await manager.push(thread_id, env)
```

`voice_input.py` 中当 Seeduplex 模式启用时，`_push_macro_result` / `_handle_builtin` 除了推 `voice.route_result`，额外推 `voice.tts_play`。

### 24.6 两种交互模式

所有 ASRResponse 终态文本都送 Python L0 匹配一次（L0 1ms，延迟可忽略）。不设"纯对话不经 Python"路径——Rust 侧不需要做指令 vs 闲聊分类。

#### 模式 A：L0 快路径（默认）

```
用户 → PCM → Seeduplex → ASRResponse{text, full}
  │
  └── voice.route{text} → Python L0 匹配
        ├── 命中 → Macro 执行 → push_tts_text("已静音")
        │         → Rust inject_tts → TTSResponse → 播放
        └── 未命中 → 模式 B
```

所有 ASRResponse 先过 L0（1ms）。命中即执行，未命中走 Agent。

#### 模式 B：Agent 路由（L0 未命中 → 工具调用 / 知识查询）

```
用户 → PCM → Seeduplex → ASRResponse{text, full}
  → voice.route{text} → L0 未命中
  → dispatch_agent_run → Agent 工具调用 + LLM 生成
  → reply text → push_tts_text(reply)
  → Rust inject_tts(reply) → TTSResponse → 播放
```

**本地 VAD 行为变更**：Seeduplex 模式下关闭 Silero VAD 的断句功能（server_vad 由 Seeduplex 管理）。本地 VAD 仅用于音频静音裁剪（减少传输量），不用于断句。交互节奏由 Seeduplex 的 `ASRInfo→ASRResponse→ASREnded` 事件序列控制。

### 24.7 备用路径降级

当 Seeduplex 连接失败 / 超时时，自动降级：

```python
# voice_ws.py _handle_route
if not seeduplex_enabled:
    # 当前路径：Rust 本地 ASR 已完成，发 voice.route
    msg = await voice_input.receive(body)
```

Seeduplex 可用性在 `system.init` 握手时携带：

```json
{
  "type": "system.init",
  "body": {
    "client_id": "...",
    "configs": {...},
    "state": {...},
    "seeduplex_connected": true,
    "seeduplex_model": "doubao-seeduplex-3.0"
  }
}
```

### 24.8 实现计划

| 阶段 | 内容 | 涉及文件 |
|------|------|---------|
| P1 | Rust SeeduplexClient 核心：连接 + StartSession + 音频收发 | `seeduplex_client.rs` |
| P2 | Rust receive_loop 事件分发：ASRResponse→voice.route / TTSResponse→afplay | `seeduplex_client.rs`, `voice_session.rs` |
| P3 | Python `voice.tts_play` 信令 + executor.push_tts_text | `voice_ws.py`, `executor.py` |
| P4 | voice_input 适配：Seeduplex 模式下 push_macro_result 额外推 tts_play | `voice_input.py` |
| P5 | 降级逻辑：system.init seeduplex_connected → 自动选路径 | `voice_ws.py`, `voice_session.rs` |
| P6 | 配置管理：Seeduplex AppID/AccessKey 持久化 | `shared_state.py`, 前端 UI |

### 24.9 手机端集成（React Native）

#### 24.9.1 差异对比

手机端没有 Tauri Rust 层和本地 ASR/TTS 引擎，Seeduplex 是**唯一主路径**，不需要降级。

| | 桌面（Tauri Rust） | 手机（React Native） |
|---|---|---|
| Seeduplex 接入 | 自研 `SeeduplexClient` (Rust, WebSocket 裸协议) | 火山引擎官方 Android/iOS SDK |
| 音频采集 | macOS CoreAudio → 16kHz PCM | 系统麦克风 API → SDK 自动处理 |
| 音频播放 | `afplay` 子进程 | 系统 AudioTrack / AVAudioPlayer |
| ASR/TTS 主路径 | Seeduplex | Seeduplex（唯一路径） |
| 备用路径 | Seeduplex 断连 → Qwen3+Edge-TTS | **无**（断连时提示用户重试） |
| 后端 WS | 本地 IPC `127.0.0.1` | 远程 WebSocket |
| WS 信令格式 | 与手机完全相同 | 复用桌面 `voice.*` 信令 |

#### 24.9.2 手机端架构

手机端不直连 Python 后端。语音消息走三层路由：

```
手机麦克风
  │
  ▼
Seeduplex Android/iOS SDK（火山引擎官方）
  │
  ├── ASRResponse{text, full}
  │     │
  │     ▼
  │   HTTP POST /api/v1/message/send     ← 手机 → Gateway
  │   {target_device_key, envelope: {type:"voice.route", body:{text,thread_id}}}
  │     │
  │     ▼
  │   Gateway mobile/handler.go           ← 消息路由
  │     └── env.Type 不在 switch 列（line 152-174）
  │          → default: routeEnvelope()
  │          → deviceMgr.RouteCommandEnvelope(deviceKey, env)
  │          → WS 推送到桌面端
  │     │
  │     ▼
  │   桌面端 EvoCloud WS link 收到
  │     → 本地 WS → Python voice_ws.py → L0/Agent
  │       ├── L0 命中 → push_tts_play("已静音")
  │       └── L0 未命中 → Agent → reply text → push_tts_play(reply)
  │     │
  │     ▼
  │   桌面端收到 voice.tts_play
  │     → 不播放（手机端需要听）
  │     → 转发到 EvoCloud WS → Gateway
  │     → Gateway → HTTP 响应 → 手机
  │     → Seeduplex.injectTTS(text) → TTSResponse → 扬声器
  │
  └── TTSResponse{audio} → 扬声器（纯对话）
```

**关键路径**：`voice.route` 和 `voice.tts_play` 在 Gateway 中通过 `default→routeEnvelope` 自动转发，**不需改 Gateway 代码**。

**三条独立连接**：

```
手机 ── HTTP ──→ Gateway ── WS ──→ 桌面端 ── local WS ──→ Python
手机 ── WebSocket ──→ 火山引擎 Seeduplex（ASR/TTS 音频流）
桌面 ── WS ──→ Gateway（EvoCloud link，双向）
```

#### 24.9.3 与桌面共享的组件

信令格式和 Python 层完全共享，传输路径不同：

| 组件 | 桌面 | 手机 |
|------|------|------|
| `voice.route` 信令格式 | 相同 JSON | 相同 JSON，**封装在 Gateway envelope 中** |
| `voice.tts_play` 信令格式 | 相同 JSON | 相同 JSON，**由桌面端代转发** |
| `MessageType.VOICE_TTS_PLAY` | `canonical.py` | 同 |
| Python L0 匹配 | 同一 `LocalMatcher` | 同（桌面端 Python 执行） |
| Python Macro 执行 | 同一 `_dispatch_macro` | 同（桌面端执行） |
| Python Agent 路由 | 同一 `dispatch_agent_run` | 同 |
| `executor.push_tts_text` | 同一函数 | 同（桌面端调用） |
| Seeduplex AppID/AccessKey | 桌面配置 | 手机独立配置 |

#### 24.9.4 手机端 Voice 消息在 Gateway 的转发

Gateway `mobile/handler.go:152-174` 的 switch：

```go
switch env.Type {
case "command.relay":
    h.handleCommandRelay(...)    // 现有文本消息
case "command.stop":
    h.handleSimpleCommand(...)
    // ... 其他已知类型
default:
    h.routeEnvelope(...)         // ← voice.route / voice.tts_play 走这里
}
```

`routeEnvelope` 调用 `deviceMgr.RouteCommandEnvelope(deviceKey, env)`，将信封通过 WS 推送到桌面端。桌面端的 EvoCloud WebSocket link 收到后，通过 `channel_registry` 分发给 `voice_channel`（文本通道）或直接发出事件。**不需要改 Gateway 代码**。

#### 24.9.5 手机端与桌面端之间 voice.tts_play 的回传路径

Python `push_tts_text("已静音")` 走到桌面端本地 Python WS 后：

```
Python executor.push_tts_text("已静音")
  → manager.push() → local WS → 桌面端 Rust
    → Rust 判断：这不是给我听的（手机来的消息）
      → 转发到 EvoCloud WS → Gateway
        → Gateway 找到手机设备 → WS → HTTP 响应
          → 手机 App 收到
            → SeeduplexModule.injectTTS("已静音")
              → Seeduplex ChatTTSText → TTSResponse → 扬声器
```

桌面端 Rust `voice_session.rs` 中 `voice.tts_play` 的处理逻辑：

```rust
"voice.tts_play" => {
    if let Some(text) = body.get("text").and_then(|v| v.as_str()) {
        if seeduplex_client.is_connected() {
            // 桌面端自己使用 Seeduplex → 直接 inject
            seeduplex_client.inject_tts(text).await;
        } else if let Some(device_key) = body.get("target_device_key").and_then(|v| v.as_str()) {
            // 手机端的声音 → 转发到 Gateway → 手机
            evocloud_link.send_envelope(device_key, envelope).await;
        }
    }
}
```

`target_device_key` 字段在 Python 侧 `push_tts_text` 时由 `voice.route` 手机请求中携带的 `device_key` 回传。Python 侧在收到手机 ASRResponse 时存储 `device_key`，回复时带上。

#### 24.9.6 手机端原生模块封装

React Native 需要包装火山引擎 SDK，新增 `mobile/src/native-modules/SeeduplexModule/`：

```typescript
// mobile/src/native-modules/SeeduplexModule/index.ts
export interface SeeduplexModule {
  /** 初始化 SDK，建立 WebSocket 连接 */
  connect(appId: string, accessKey: string): Promise<void>;

  /** 开始录音 → 自动流式上传到 Seeduplex */
  startRecording(): Promise<void>;

  /** 停止录音 → 发送结束标记 */
  stopRecording(): Promise<void>;

  /** 注入文本合成音频（L0/Agent 结果） */
  injectTTS(text: string): Promise<void>;

  /** 断开连接 */
  disconnect(): Promise<void>;

  /** ASR 终态文本回调 */
  onASRResult(callback: (text: string) => void): void;

  /** 音频播放状态回调 */
  onTTSState(callback: (state: 'playing' | 'idle') => void): void;

  /** 连接状态回调 */
  onConnectionState(callback: (state: 'connected' | 'disconnected') => void): void;
}
```

Android 端：火山引擎 SDK 封装为 Native Module（Java/Kotlin）。
iOS 端：火山引擎 SDK 封装为 Native Module（Swift/Objective-C）。

React Native 业务层调用：

```typescript
// mobile/src/services/voiceService.ts
import { NativeModules } from 'react-native';
const { SeeduplexModule } = NativeModules;

class VoiceService {
  private deviceKey: string = '';  // 从登录信息获取

  async startSession() {
    await SeeduplexModule.connect(APP_ID, ACCESS_KEY);
    SeeduplexModule.onASRResult(async (text) => {
      // ASR 终态文本 → HTTP → Gateway → 桌面端 → Python L0/Agent
      const response = await fetch(`${GATEWAY_URL}/api/v1/message/send`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${TOKEN}` },
        body: JSON.stringify({
          target_device_key: this.deviceKey,
          envelope: {
            version: '2.0',
            type: 'voice.route',
            body: { thread_id: THREAD_ID, text },
          },
        }),
      });
      const { data: { command_id } } = await response.json();
      // 轮询或等待 push 通知获取 voice.tts_play 结果
    });
  }

  // 收到 Gateway 推送的 voice.tts_play → 注入 TTS
  // Gateway 通过 push 通知或命令状态回查返回结果
  private onTTSPlay(text: string) {
    SeeduplexModule.injectTTS(text);
  }
}
```
#### 24.9.6 手机端实现计划

| 阶段 | 内容 | 涉及 |
|------|------|------|
| M1 | Android Native Module：Seeduplex SDK 封装（连接 + 音频 + injectTTS） | `SeeduplexModule.java` |
| M2 | iOS Native Module：Seeduplex SDK 封装 | `SeeduplexModule.swift` |
| M3 | React Native 业务层：voiceService.ts（ASR→HTTP→Gateway / injectTTS←push） | `voiceService.ts` |
| M4 | 桌面端 Rust voice.tts_play handler 区分本地/手机来源 + 转发 | `voice_session.rs` |
| M5 | Python executor.push_tts_text 携带 target_device_key | `executor.py`, `voice_input.py` |
