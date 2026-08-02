# 语音全链路

## 总览

```
麦克风 → VAD → Qwen3-ASR → WS voice.route → Python 路由
  ├── L0 本地命中 → voice.route_result → Rust TTS
  └── Agent 链路 → Supervisor → Worker → Finish
        ├── voice.token → 前端显示
        ├── voice.tts_boundary → Rust TTS → 逐句播报
        └── voice.route_result {done} → Rust 状态管理
```

---

## 阶段 1：Rust 音频采集 → ASR

**文件：** `frontend/src-tauri/src/voice/voice_session.rs:330-476`

1. `start()` → `ensure_initialized()` 懒加载 VAD + Qwen3-ASR + 连接 WS
2. `mic.start()` → cpal 采集麦克风音频，重采样到 16kHz mono
3. 每帧回调 (~30ms)：
   - `vad.process(samples)` → Silero VAD 断句
   - `vad.is_speech_active()` → 抢话检测
   - 如有 TTS 播放中 + 检测到人声 → `tts.stop()` + `ws.send_barge_in()`
4. VAD 断句结束 → 拼接音频段 → `offline_asr.recognize(full_audio)` → Qwen3-ASR 识别
5. 模式分支：
   - **对话：** `ws.send_route(tid, text, msg_id)` → 状态 `Processing`
   - **听写：** 短文本直接 paste / 长文本 `ws.send_dictation_finalize()` / 走 LLM 润色

---

## 阶段 2：WS 传输（Rust → Python）

**文件：** `frontend/src-tauri/src/voice/ws_client.rs:117-131`

```json
{
  "version": "2.0",
  "type": "voice.route",
  "message_id": "uuid",
  "body": {"thread_id": "xxx", "text": "xxx", "message_id": "uuid"}
}
```

---

## 阶段 3：Python WS 接收 + 路由

**文件：** `backend/app/api/routes/voice_ws.py:364-456`

初始握手：
- 接受 WS，检查 loopback
- `manager.register(conn_id, ws)`
- 发送 `system.init` + configs 快照

消息循环：
- `"voice.route"` → `asyncio.create_task(_handle_route(body, conn_id))`
- `"voice.barge_in"` → 取消当前 task
- `"voice.dictation.finalize"` → LLM 润色 → 推回

### `_handle_route()` 核心路由

**文件：** `backend/app/api/routes/voice_ws.py:86-181`

1. 获取 per-thread 锁，自动抢话
2. 幂等检查：重复 `message_id` → 返回缓存结果
3. **L0 快速路径：** `_get_local_matcher().match(text)`
   - 命中 → 直接推 `voice.route_result {routed, local, action}`
4. **L0 未命中 → 走 Agent 链路：**
   - `dispatch_agent_run()` 准备输入
   - `run_agent_background(thread_id, inputs)` → 后台执行

---

## 阶段 4：L0 本地命中 → 即时回复

**文件：** `backend/app/core/routing/router.py:17-33`（匹配）
**文件：** `backend/app/core/routing/connection.py:78-93`（推送）

```
voice.route_result
  → WS → Rust voice_session.rs:184-189
  → handle_route_result()
  → speak(confirmation) 如 "已静音"、"已截图"
```

---

## 阶段 5：Agent 链路（L0 未命中）

**文件：** `backend/app/core/engine/background_agent/runner.py:22-227`

```
run_agent_background()
  → 加载 context，设置 next_node = "supervisor"
  → run_node_loop(state, config, thread_id)
```

### Node Loop

**文件：** `backend/app/core/engine/loop.py:23-86`

```
Supervisor → Worker → Finish → END
```

### Supervisor

**文件：** `backend/app/core/engine/nodes/supervisor.py:24-302`

LLM 决定路由：Worker（工具调用）或 Finish（结束回复）

### Worker

执行工具，结果回到 Supervisor 或 Finish

### Finish

**文件：** `backend/app/core/engine/nodes/finish.py:133-323`

- 质量审计
- 构建 `SessionCompletedData`
- 发布 `SessionCompletedEvent`

---

## 阶段 6：LLM 流式输出 → voice.token + voice.tts_boundary

### LLM 推理 → TokenEvent

**文件：** `backend/app/core/engine/message/handler/_stream_mixin.py:13-21`

LLM stream tokens → `TransparentCallbackHandler.stream_token()` → 发布 `TokenEvent`

### MessagePublisher → VoiceChannel

**文件：** `backend/app/core/engine/message/publisher.py:37-74`

- 检查 `_voice_registry` → 添加 `"voice"` 到目标 channel
- 调用 `VoiceChannel.send(payload, ctx)`

### VoiceChannel.send(TokenEvent)

**文件：** `backend/app/core/channel/voice_channel.py:66-96`

```
TokenEvent 到达
  → 累加到 _token_buffers[tid]
  → voice_executor.push_voice_token(tid, token)
    → WS voice.token → Rust → 前端显示
  → 如遇句尾（。！？.!?\n）
    → voice_executor.push_voice_tts_boundary(tid, sentence)
      → WS voice.tts_boundary → Rust TTS 播放
```

### 流式 LLM 备选路径（executor 路径）

**文件：** `backend/app/core/routing/executor.py:121-178`

```
astream() 逐 chunk
  → push_voice_token() 逐 token
  → push_voice_tts_boundary() 逐句
```

---

## 阶段 7：Rust 接收流式消息

**文件：** `frontend/src-tauri/src/voice/voice_session.rs:171-257`

- `"voice.token"` → `event_bus.emit("voice:token")` → 前端显示
- `"voice.tts_boundary"` → `tts.queue_sentence()` + `tts.speak_next()`

### TTS Engine

**文件：** `frontend/src-tauri/src/voice/tts_engine.rs`

TTS 统一由火山引擎实时对话 API 合成，通过 WS binary 帧回 Rust 端 ffplay 播放。

---

## 阶段 8：Finish → SessionCompletedEvent → voice.route_result

### Finish Node

**文件：** `backend/app/core/engine/nodes/finish.py:133-323`

→ 发布 `SessionCompletedEvent`

### UniversalBridgeSubscriber

**文件：** `backend/app/core/events/subscribers/bridge.py:28-54`

→ 转发到 `VoiceChannel`

### VoiceChannel.send(SessionCompletedEvent)

**文件：** `backend/app/core/channel/voice_channel.py:123-160`

```
Flush 剩余 token 缓冲区
  → push_voice_tts_boundary()  flush 尾部
去重检查（summary 是否已被 stream 覆盖）
  → voice_executor.push_voice_result(tid, "done", summary)
    → WS voice.route_result {done, summary}
```

### Rust 处理

**文件：** `frontend/src-tauri/src/voice/voice_session.rs:604-654`

- `"done"` → 不播 TTS（已由 `tts_boundary` 覆盖），状态 → `Idle`
- `"failed"` → `speak("抱歉，处理出错了")`，状态 → `Idle`
- `"cancelled"` → 不播 TTS，状态 → `Idle`

---

## 阶段 9：失败路径

- Agent 异常 → `handle_task_exception()` → `AgentRunCompletedEvent`
- `VoiceChannel.send(AgentRunCompletedEvent)` → `push_voice_result(tid, "failed", summary)`

---

## 消息汇总

### Rust → Python

| 类型 | 触发时机 | 文件 |
|------|---------|------|
| `voice.start` | 开始会话 | `voice_session.rs:344` |
| `voice.route` | ASR 识别完成 | `voice_session.rs:466` |
| `voice.barge_in` | 用户抢话 | `voice_session.rs:399` |
| `voice.dictation.finalize` | 听写完成 | `voice_session.rs:459` |
| `voice.stop` | 结束会话 | `voice_session.rs:486` |

### Python → Rust

| 类型 | 触发时机 | 文件 |
|------|---------|------|
| `system.init` | WS 握手 | `voice_ws.py:373` |
| `voice.route_result` | 路由结果/完成/失败 | `executor.py:43` |
| `voice.token` | LLM 流式 token | `executor.py:108` |
| `voice.tts_boundary` | LLM 流式句子 | `executor.py:114` |
| `voice.dictation.polished` | 听写润色结果 | `voice_ws.py:298` |
| `system.config_changed` | 配置变更广播 | `voice_ws.py:326` |
