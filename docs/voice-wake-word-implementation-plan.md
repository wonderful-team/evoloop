# 语音唤醒功能实现计划（v3 — 本地 KWS + Volcengine TTS 语音反馈）

## 架构

```
常驻 Rust 线程（WakeWordDetector 专用 OS 线程 + 独立 tokio runtime）
  ┌─────────────────────────────────────────────────────┐
  │  MicCapture (cpal, 16kHz mono)                      │
  │     │                                                │
  │     └──→ sherpa-onnx KeywordSpotter                  │
  │             │  模型: zipformer-wenetspeech 3.3M      │
  │             │  (~/.evoloop/models/kws/)              │
  │             │  关键词: "你好Evo" (动态可改)            │
  │             │                                        │
  │             └──→ 匹配 "你好Evo"                       │
  │                      │                               │
  │          ┌───────────┴───────────┐                   │
  │          ▼                       ▼                   │
  │  speak_direct("我在")      emit("wake-word-detected") │
  │   └→ TTS_CACHE hit/miss       └→ 前端收到             │
  │   └→ ffplay 播放                ├→ stop_wake_word    │
  │   (~300ms, 边播边唤醒)          └→ start_voice_session│
  │                                                       │
  │  对话中 10min 无语音 → auto stop                       │
  │      → 前端重启唤醒检测                                │
  └─────────────────────────────────────────────────────┘
```

## 阶段一：模型下载

```bash
cd ~/.evoloop/models/
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01.tar.bz2
tar xvf sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01.tar.bz2
rm sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01.tar.bz2
mv sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01 kws
```

```
~/.evoloop/models/kws/
  ├── encoder-epoch-12-avg-2-chunk-16-left-64.onnx   (~12MB)
  ├── decoder-epoch-12-avg-2-chunk-16-left-64.onnx   (~660K)
  ├── joiner-epoch-12-avg-2-chunk-16-left-64.onnx    (~247K)
  └── tokens.txt
```

## 阶段二：WakeWordDetector 重写

### 线程模型

`cpal::Stream` 是 `!Send`，需专用 OS 线程 + 独立 tokio runtime（同 `spawn_voice_manager`）。

```rust
pub struct WakeWordDetector {
    cmd_tx: Option<mpsc::Sender<WakeWordCmd>>,
    thread_handle: Option<std::thread::JoinHandle<()>>,
}

enum WakeWordCmd {
    Start { app_handle: tauri::AppHandle, word: String, voice: String },
    Stop,
    SetWord(String),
}
```

### KWS 主循环

```rust
async fn run_detector(app_handle: tauri::AppHandle, word: String, voice: String) {
    let kws_model_dir = find_kws_model_dir().expect("KWS model not found");

    let mut config = KeywordSpotterConfig::default();
    config.model_config.transducer.encoder =
        Some(format!("{}/encoder-epoch-12-avg-2-chunk-16-left-64.onnx", kws_model_dir));
    config.model_config.transducer.decoder =
        Some(format!("{}/decoder-epoch-12-avg-2-chunk-16-left-64.onnx", kws_model_dir));
    config.model_config.transducer.joiner =
        Some(format!("{}/joiner-epoch-12-avg-2-chunk-16-left-64.onnx", kws_model_dir));
    config.model_config.tokens =
        Some(format!("{}/tokens.txt", kws_model_dir));
    config.keywords_threshold = 0.25;

    let kws = KeywordSpotter::create(&config).expect("KWS create");
    let stream = kws.create_stream_with_keywords(&word);

    let mut mic = MicCapture::new();
    let WAKE_REPLIES: &[&str] = &["我在", "嗯哼", "请说", "你说"];

    mic.start(move |samples: &[f32]| {
        stream.accept_waveform(16000, samples);
        while kws.is_ready(&stream) { kws.decode(&stream); }

        if let Some(result) = kws.get_result(&stream) {
            stream.reset();

            // 1. 随机选一个回复，用 Volcengine TTS 播放（走缓存 + ffplay）
            let reply = WAKE_REPLIES[fastrand::usize(..WAKE_REPLIES.len())];
            let voice = voice.clone();
            let app = app_handle.clone();
            tokio::spawn(async move {
                let _ = speak_direct(reply, "volcengine", &voice).await;
            });

            // 2. 通知前端
            let _ = app_handle.emit("wake-word-detected",
                serde_json::json!({"word": result.keyword}));
        }
    });
}
```

### 线程管理

```rust
pub fn start(&mut self, app_handle: tauri::AppHandle, word: String, voice: String) {
    if self.cmd_tx.is_some() { return; }
    let (tx, mut rx) = mpsc::channel(16);
    self.cmd_tx = Some(tx);

    let handle = std::thread::spawn(move || {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all().build().unwrap();
        rt.block_on(run_detector(app_handle, word, voice));
    });
    self.thread_handle = Some(handle);
}

pub fn stop(&mut self) {
    self.cmd_tx.take();
    if let Some(h) = self.thread_handle.take() {
        let _ = h.join();
    }
}
```

## 阶段三：前端编排

### 互斥切换

```typescript
// useWakeWord.ts
listen("wake-word-detected", async (event) => {
    await invoke("stop_wake_word_listener");
    await invoke("start_voice_session", {
        threadId: crypto.randomUUID(),
        lang: "zh-CN",
        mode: "dialogue",
    });
});
```

```typescript
// useVoiceEvents.ts
listen("voice:state", (event) => {
    if (event.payload.state === "idle" && wasWakeActivated) {
        invoke("start_wake_word_listener", {
            word: localStorage.getItem("evoloop_wake_word") || "你好Evo",
        });
    }
});
```

## 阶段四：10min 超时

在 `voice_session.rs` 的 `start()` 中 spawn：

```rust
if mode == "dialogue" {
    let running = self.running.clone();
    let ws = ws_client.clone();
    let tid = thread_id.clone();
    tokio::spawn(async move {
        let mut last_activity = Instant::now();
        loop {
            tokio::time::sleep(Duration::from_secs(30)).await;
            if !running.load(Ordering::SeqCst) { break; }
            if last_activity.elapsed() > Duration::from_secs(600) {
                let _ = ws.send("voice.cancel",
                    json!({"thread_id": tid})).await;
                break;
            }
        }
    });
}
```

## 阶段五：唤醒词修改

### L0 模板

```python
{
    "action": "change_wake_word",
    "patterns": [
        "以后用{word}唤醒",
        "唤醒词改成{word}",
        "用{word}唤醒我",
    ],
    "slots": {"word": "str"},
}
```

### Builtin

```python
elif action == "change_wake_word":
    word = args.get("word", "")
    if word:
        await SystemConfigService.set_value_async("VOICE_WAKE_WORD", word)
    await self._maybe_push_tts(thread_id, f"好的，以后用{word}唤醒" if word else "好的")
```

### 配置同步

Rust 侧 `start_wake_word_listener` 启动时读本地配置 + 监听 WS `system.config_changed` 实时更新。

## 边界情况

| 场景 | 处理 |
|------|------|
| KWS 模型不存在 | `start()` 返回 Err → 前端弹提示引导下载 |
| 麦克风被占用 | `MicCapture::start()` Err → 降级，不启动唤醒 |
| 唤醒回复首次无缓存 | `speak_direct` cache miss → HTTP Volcengine TTS → 后续 cache hit |
| 用户连续说唤醒词 | KWS 匹配后 `stream.reset()`，不会重复触发 |
| F12 与唤醒冲突 | F12 按下时前端先 `stop_wake_word_listener` |
| 10min 超时时正在 TTS 播放 | 先 `voice.barge_in` 打断 → 再 stop |

## 实现顺序

| # | 内容 | 文件 | 行数 |
|---|------|------|------|
| 0 | 下载 KWS 模型 | — | 5 分钟 |
| 1 | Rust `wake_word.rs` 重写 | `wake_word.rs`, `lib.rs` | ~250 |
| 2 | 前端互斥编排 | `useWakeWord.ts`, `useVoiceEvents.ts` | ~40 |
| 3 | 10min 超时 | `voice_session.rs` | ~30 |
| 4 | L0 + builtin | `init_spec.py`, `voice_input.py` | ~20 |

**合计**：~340 行，无新增依赖
