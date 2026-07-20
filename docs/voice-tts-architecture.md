# TTS 架构分析与统一方案

## 现状

当前 TTS 引擎分布在 Rust 和 Python 两侧：

| 引擎 | 位置 | 实现方式 |
|------|------|---------|
| Edge-TTS | Rust 侧 | `msedge-tts` crate 直接调微软云 |
| Qwen-TTS | Rust 侧 | reqwest 调 DashScope API |
| System (say) | Rust 侧 | macOS `say` 命令 |
| Kokoro | Python 侧 | Rust → HTTP POST → Python `KPipeline` → WAV → Rust `afplay` |
| CosyVoice | Python 侧 | Rust → HTTP POST → Python `CosyVoice` → WAV → Rust `afplay` |

## 问题

### 1. 配置两套
Rust `voice_manager` 缓存一份 engine/voice/speed，Python DB 也存一份，需要 WS `system.config_changed` 事件同步。多了一步，容易不同步。

### 2. 引擎归属分裂
`speak_direct` 函数需要判断每个引擎走哪条路径：
```
edge-tts → Rust 直接调
qwen-tts → Rust 直接调
kokoro → HTTP POST 到 Python
cosyvoice → HTTP POST 到 Python
system → Rust 直接调
```
新增引擎时必须同时改 Rust 和 Python。

### 3. 错误处理不一致
- Rust 侧失败：在 `tts_engine.rs` 的 tokio task 里 log
- Python 侧失败：HTTP 返回非 200，Rust 再判断
- 用户难以统一感知

## 为什么 Kokoro/CosyVoice 不能在 Rust

Kokoro 和 CosyVoice 是 **PyTorch 模型**。Rust 生态没有能加载 PyTorch 模型的推理库。

替代方案：
- ONNX 导出模型 + `ort` crate 推理 → 可行但需要额外导出工作，且模型可能退化
- sherpa-onnx TTS 支持 → 有限，不支持 Kokoro/CosyVoice 架构
- **结论：必须留在 Python**

## 统一方案

### 目标
单一 TTS 入口，Rust 只负责播放音频。

### 方案：全部统一到 Python

```
Rust TTS 调用
  → HTTP POST /api/v1/voice/tts  {engine, text, voice}
  → Python BaseTTSProvider.dispatch(engine)
      ├── EdgeTTSProvider    → msedge-tts Python 库
      ├── QwenTTSProvider    → httpx 调 DashScope API
      ├── KokoroProvider     → KPipeline (已实现)
      ├── CosyVoiceProvider  → CosyVoice (已实现)
      └── SystemProvider     → subprocess say
  → WAV bytes 返回 Rust
  → afplay / TtsEngine 播放
```

### 收益
- 单一入口，`speak_direct` 不再需要引擎分支判断
- 新增引擎只需 Python 侧加 Provider，Rust 侧加一行 `TtsEngineKind`
- 配置直接读 Python DB，无需跨进程同步
- 错误处理统一

### 代价
- Edge-TTS / Qwen-TTS Python 端需要加 HTTP 实现（简单，`httpx` 调云 API）
- 多一次 HTTP 本地往返（对本机延迟可忽略）

## 决策
待定。
