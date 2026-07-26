use std::collections::HashMap;
use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tokio::sync::RwLock;
use tokio::sync::mpsc;
use log::{info, warn, error};
use uuid::Uuid;

use super::offline_asr::OfflineAsrEngine;
use super::vad_engine::VadEngine;
use super::tts_engine::{TtsEngine, TtsEngineKind};
use super::aec_engine::AecMicCapture;
use super::event::VoiceEventBus;
use super::state_machine::{VoiceState, VoiceStateMachine};
use super::ws_client::{VoiceEnvelope, VoiceWsClient};
use super::seeduplex_client::SeeduplexClient;

use crate::sidecar::BACKEND_PORT;

/// Copy text to clipboard and simulate Cmd+V to paste into the frontmost app.
#[cfg(target_os = "macos")]
pub fn dictation_paste(text: &str) {
    // 1. Set clipboard
    if let Ok(mut clipboard) = arboard::Clipboard::new() {
        let _ = clipboard.set_text(text);
    } else {
        warn!("[dictation] failed to open clipboard");
        return;
    }

    // 2. Simulate Cmd+V via CGEventPost
    use core_graphics::event::{CGEvent, CGEventTapLocation, CGKeyCode};
    use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};

    let source = match CGEventSource::new(CGEventSourceStateID::Private) {
        Ok(s) => s,
        Err(_) => {
            warn!("[dictation] failed to create event source");
            return;
        }
    };
    let cmd: CGKeyCode = 0x37;
    let v: CGKeyCode = 0x09;

    let post = |key: CGKeyCode, down: bool, cmd_flag: bool| {
        if let Ok(event) = CGEvent::new_keyboard_event(source.clone(), key, down) {
            if cmd_flag {
                event.set_flags(core_graphics::event::CGEventFlags::CGEventFlagCommand);
            }
            event.post(CGEventTapLocation::HID);
        }
    };

    post(cmd, true, false);
    post(v, true, true);
    post(v, false, true);
    post(cmd, false, false);

    info!("[dictation] pasted: {}", text);
}

#[cfg(not(target_os = "macos"))]
pub fn dictation_paste(_text: &str) {
    warn!("[dictation] paste not supported on this platform");
}

pub struct VoiceSession {
    offline_asr: Arc<RwLock<Option<OfflineAsrEngine>>>,
    vad: Arc<RwLock<Option<VadEngine>>>,
    tts: Arc<TtsEngine>,
    mic: Arc<RwLock<AecMicCapture>>,
    state_machine: Arc<VoiceStateMachine>,
    ws_client: Arc<RwLock<Option<Arc<VoiceWsClient>>>>,
    seeduplex: Arc<RwLock<Option<SeeduplexClient>>>,
    thread_id: Arc<RwLock<String>>,
    running: Arc<AtomicBool>,
    lang: Arc<RwLock<String>>,
    mode: Arc<RwLock<String>>,
    dialogue_active: Arc<AtomicBool>,
    audio_queue: Arc<Mutex<VecDeque<f32>>>,
    event_bus: Arc<Mutex<Option<Arc<dyn VoiceEventBus>>>>,
    model_search_paths: Vec<PathBuf>,
    llm_polish_enabled: Arc<AtomicBool>,
    shared_state: Arc<RwLock<HashMap<String, String>>>,
    seeduplex_connected: Arc<AtomicBool>,
}

impl VoiceSession {
    pub fn new(model_search_paths: Vec<PathBuf>) -> Self {
        let audio_queue = Arc::new(Mutex::new(VecDeque::new()));
        let tts = Arc::new(TtsEngine::new_with_queue(audio_queue.clone()).unwrap_or_else(|e| {
            error!("[voice-session] TTS init failed: {}", e);
            panic!("TTS engine required but failed to initialize");
        }));

        Self {
            offline_asr: Arc::new(RwLock::new(None)),
            vad: Arc::new(RwLock::new(None)),
            tts,
            mic: Arc::new(RwLock::new(AecMicCapture::new())),
            state_machine: Arc::new(VoiceStateMachine::new()),
            ws_client: Arc::new(RwLock::new(None)),
            seeduplex: Arc::new(RwLock::new(None)),
            thread_id: Arc::new(RwLock::new(String::new())),
            running: Arc::new(AtomicBool::new(false)),
            lang: Arc::new(RwLock::new("zh-CN".to_string())),
            mode: Arc::new(RwLock::new("dialogue".to_string())),
            dialogue_active: Arc::new(AtomicBool::new(false)),
            audio_queue,
            event_bus: Arc::new(Mutex::new(None)),
            model_search_paths,
            llm_polish_enabled: Arc::new(AtomicBool::new(
                std::env::var("EVOLOOP_DICTATION_LLM_POLISH").as_deref() == Ok("true")
                    || std::env::var("DICTATION_LLM_POLISH").as_deref() == Ok("true")
            )),
            shared_state: Arc::new(RwLock::new(HashMap::new())),
            seeduplex_connected: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn set_event_bus(&self, bus: Arc<dyn VoiceEventBus>) {
        if let Ok(mut lock) = self.event_bus.lock() {
            *lock = Some(bus);
        }
    }

    fn emit_event(&self, event: &str, payload: serde_json::Value) {
        if let Ok(lock) = self.event_bus.lock() {
            if let Some(bus) = lock.as_ref() {
                bus.emit(event, payload);
            }
        }
    }

    fn emit_log(&self, message: &str) {
        info!("[voice-log] {}", message);
        self.emit_event("voice:log", serde_json::json!({"message": message}));
    }

    /// Initialize VAD and Qwen3-ASR engines with model paths.
    pub async fn init_engines(
        &self,
        vad_model_path: &str,
        vad_silence_ms: f32,
        qwen3_model_dir: Option<&str>,
    ) -> Result<(), String> {
        let vad = VadEngine::new(vad_model_path, vad_silence_ms)?;
        *self.vad.write().await = Some(vad);

        if let Some(dir) = qwen3_model_dir {
            match OfflineAsrEngine::new(dir) {
                Ok(engine) => {
                    *self.offline_asr.write().await = Some(engine);
                    info!("[voice-session] Qwen3 ASR loaded");
                }
                Err(e) => {
                    let err = format!("Qwen3 ASR init failed: {}", e);
                    error!("[voice-session] {}", err);
                    return Err(err);
                }
            }
        } else {
            info!("[voice-session] Qwen3 ASR not initialized (optional)");
        }

        info!("[voice-session] engines initialized");
        Ok(())
    }

    /// Connect to Python backend WebSocket.
    pub async fn connect_backend(&self, ws_url: &str) -> Result<(), String> {
        let event_bus = {
            let lock = self.event_bus.lock().unwrap();
            lock.as_ref().cloned().ok_or("Event bus not set")?
        };
        let session_state = self.state_machine.clone();
        let session_tts = self.tts.clone();
        let session_lang = self.lang.clone();
        let session_shared_state = self.shared_state.clone();
        let session_seeduplex = self.seeduplex.clone();
        let session_ws_client = self.ws_client.clone();
        let session_seeduplex_connected = self.seeduplex_connected.clone();
        let _session_thread_id = self.thread_id.clone();

        let handler = Arc::new(move |envelope: VoiceEnvelope| {
            let session_state = session_state.clone();
            let session_tts = session_tts.clone();
            let session_lang = session_lang.clone();
            let session_shared_state = session_shared_state.clone();
            let session_seeduplex = session_seeduplex.clone();
            let session_ws_client = session_ws_client.clone();
            let session_seeduplex_connected = session_seeduplex_connected.clone();
            let _session_thread_id = _session_thread_id.clone();
            let event_bus = event_bus.clone();

            // Do not block the WebSocket read loop; dispatch to async task.
            tokio::spawn(async move {
                let msg_type = envelope.msg_type.as_str();
                let body = envelope.body.unwrap_or(serde_json::Value::Null);

                match msg_type {
                    "voice.route_result" => {
                        let status = body.get("status").and_then(|v| v.as_str()).unwrap_or("?");
                        let summary_len = body.get("summary").and_then(|v| v.as_str()).map(|s| s.chars().count()).unwrap_or(0);
                        info!("[voice-session] received voice.route_result: status={}, summary_chars={}", status, summary_len);
                        event_bus.emit("voice:route_result", body.clone());
                        let sp = session_seeduplex.clone();
                        handle_route_result(
                            &body, &session_tts, &session_state, &session_lang, &event_bus, &sp
                        ).await;
                    }

                    "voice.token" => {
                        if let Some(token) = body.get("token").and_then(|v| v.as_str()) {
                            log::debug!("[voice-session] token: {}", token);
                            event_bus.emit("voice:token", serde_json::json!({"token": token}));
                        }
                    }

                    "voice.tts_boundary" => {
                        let sentence = body.get("sentence")
                            .or_else(|| body.get("text"))
                            .and_then(|v| v.as_str())
                            .unwrap_or("");

                        if !sentence.is_empty() {
                            info!("[voice-session] tts_boundary: {}...", &sentence[..sentence.len().min(40)]);
                            let _ = session_state.set(VoiceState::Speaking).await;
                            event_bus.emit("voice:state", serde_json::json!({"state": "speaking"}));

                            let lang = session_lang.read().await.clone();
                            session_tts.queue_sentence(sentence.to_string());
                            session_tts.speak_next(&lang);

                            event_bus.emit("voice:tts_boundary", body.clone());
                        }
                    }

                    "voice.dictation.polished" => {
                        // Check for CLARIFY: don't paste, just emit
                        let is_clarify = body.get("changes")
                            .and_then(|c| c.as_array())
                            .and_then(|arr| arr.first())
                            .and_then(|c| c.get("clarify"))
                            .and_then(|v| v.as_str());
                        if is_clarify.is_none() {
                            if let Some(text) = body.get("polished_text").and_then(|v| v.as_str()) {
                                info!("[dictation] received polished text: {}", text);
                                dictation_paste(text);
                            }
                        }
                        event_bus.emit("voice:dictation_polished", body.clone());
                    }

                    "system.init" => {
                        info!("[voice-session] backend handshake received");
                        if let Some(configs) = body.get("configs").and_then(|v| v.as_object()) {
                            info!("[voice-session] received {} synced config keys from backend", configs.len());
                            event_bus.emit("system:config_snapshot", serde_json::to_value(configs).unwrap_or_default());

                            // Seeduplex: if AppID + AccessKey configured, connect
                            let app_id = configs.get("SEEDUPLEX_APP_ID").and_then(|v| v.as_str()).unwrap_or("");
                            let access_key = configs.get("SEEDUPLEX_ACCESS_KEY").and_then(|v| v.as_str()).unwrap_or("");
                            if !app_id.is_empty() && !access_key.is_empty() {
                                let eb = event_bus.clone();
                                let sp = session_seeduplex.clone();
                                let sd_conn = session_seeduplex_connected.clone();
                                let aid = app_id.to_string();
                                let akey = access_key.to_string();
                                let (asr_tx, mut asr_rx) = mpsc::unbounded_channel::<String>();
                                let ws_for_asr = session_ws_client.clone();
                                let sm_for_asr = session_state.clone();
                                let tid_for_asr = _session_thread_id.clone();
                                let bus_for_asr = event_bus.clone();
                                // ASR forwarder: Seeduplex ASR text → Python via WS
                                tokio::spawn(async move {
                                    while let Some(text) = asr_rx.recv().await {
                                        let ws = ws_for_asr.read().await;
                                        if let Some(ref ws) = *ws {
                                            let tid = tid_for_asr.read().await.clone();
                                            let msg_id = uuid::Uuid::new_v4().to_string();
                                            if tid.is_empty() {
                                                warn!("[seeduplex] ASR text dropped (no thread_id): {}", text);
                                                continue;
                                            }
                                            info!("[seeduplex] ASR → Python: {}", text);
                                            let _ = sm_for_asr.set(VoiceState::Processing).await;
                                            bus_for_asr.emit("voice:state", serde_json::json!({"state": "processing"}));
                                            bus_for_asr.emit("voice:log", serde_json::json!({"message": format!("Seeduplex ASR: {}", text)}));
                                            let _ = ws.send_route(&tid, &text, &msg_id, None).await;
                                        }
                                    }
                                });
                                tokio::spawn(async move {
                                    match SeeduplexClient::connect(&aid, &akey, eb, asr_tx).await {
                                        Ok(client) => {
                                            info!("[seeduplex] connected successfully");
                                            sd_conn.store(true, Ordering::SeqCst);
                                            *sp.write().await = Some(client);
                                        }
                                        Err(e) => {
                                            warn!("[seeduplex] connect failed: {}", e);
                                            sd_conn.store(false, Ordering::SeqCst);
                                        }
                                    }
                                });
                            }
                        }
                        // Store and forward shared state snapshot
                        if let Some(state) = body.get("state").and_then(|v| v.as_object()) {
                            let mut cache = session_shared_state.write().await;
                            for (k, v) in state {
                                if let Some(val) = v.as_str() {
                                    cache.insert(k.clone(), val.to_string());
                                }
                            }
                            info!("[voice-session] received {} shared state keys", cache.len());
                            // Forward to React
                            event_bus.emit("system:state_snapshot", serde_json::to_value(state).unwrap_or_default());
                        }
                    }

                    "system.state_changed" => {
                        if let (Some(key), Some(value)) = (
                            body.get("key").and_then(|v| v.as_str()),
                            body.get("value").and_then(|v| v.as_str()),
                        ) {
                            session_shared_state.write().await.insert(key.to_string(), value.to_string());
                            info!("[voice-session] state changed: {} -> {}", key, value);
                        }
                    }

                    "system.config_changed" => {
                        let key = body.get("key").and_then(|v| v.as_str()).unwrap_or("");
                        let new_val = body.get("new_value").and_then(|v| v.as_str()).unwrap_or("");
                        info!("[voice-session] config changed: {} -> {}", key, new_val);
                        event_bus.emit("system:config_changed", body.clone());

                        // Track seeduplex config changes for reconnect
                        if key == "SEEDUPLEX_APP_ID" || key == "SEEDUPLEX_ACCESS_KEY" {
                            let mut shared = session_shared_state.write().await;
                            shared.insert(key.to_string(), new_val.to_string());
                            let app_id = shared.get("SEEDUPLEX_APP_ID").cloned().unwrap_or_default();
                            let access_key = shared.get("SEEDUPLEX_ACCESS_KEY").cloned().unwrap_or_default();
                            if !app_id.is_empty() && !access_key.is_empty() {
                                // Disconnect old client if any
                                *session_seeduplex.write().await = None;
                                session_seeduplex_connected.store(false, Ordering::SeqCst);
                                let eb = event_bus.clone();
                                let sp = session_seeduplex.clone();
                                let sd_conn = session_seeduplex_connected.clone();
                                let ws_for_asr = session_ws_client.clone();
                                let sm_for_asr = session_state.clone();
                                let tid_for_asr = _session_thread_id.clone();
                                let bus_for_asr = event_bus.clone();
                                let (asr_tx, mut asr_rx) = mpsc::unbounded_channel::<String>();
                                // ASR forwarder
                                tokio::spawn(async move {
                                    while let Some(text) = asr_rx.recv().await {
                                        let ws = ws_for_asr.read().await;
                                        if let Some(ref ws) = *ws {
                                            let tid = tid_for_asr.read().await.clone();
                                            let msg_id = uuid::Uuid::new_v4().to_string();
                                            if tid.is_empty() { continue; }
                                            info!("[seeduplex] ASR → Python: {}", text);
                                            let _ = sm_for_asr.set(VoiceState::Processing).await;
                                            let _ = ws.send_route(&tid, &text, &msg_id, None).await;
                                        }
                                    }
                                });
                                tokio::spawn(async move {
                                    match SeeduplexClient::connect(&app_id, &access_key, eb, asr_tx).await {
                                        Ok(client) => {
                                            info!("[seeduplex] reconnected");
                                            sd_conn.store(true, Ordering::SeqCst);
                                            *sp.write().await = Some(client);
                                        }
                                        Err(e) => warn!("[seeduplex] reconnect failed: {}", e),
                                    }
                                });
                            }
                        }
                    }

                    "system.error" => {
                        let code = body.get("code").and_then(|v| v.as_str()).unwrap_or("unknown");
                        let message = body.get("message").and_then(|v| v.as_str()).unwrap_or("");
                        warn!("[voice-session] backend error: {} {}", code, message);
                    }

                    "voice.tts_play" => {
                        if let Some(text) = body.get("text").and_then(|v| v.as_str()) {
                            let t = text.trim();
                            if !t.is_empty() {
                                let lang = session_lang.read().await.clone();
                                session_tts.stop();
                                session_tts.resume();
                                info!("[tts] voice.tts_play: {}...", &t[..t.len().min(50)]);
                                session_tts.queue_sentence(t.to_string());
                                session_tts.speak_next(&lang);
                            }
                        }
                    }

                    _ => {
                        log::debug!("[voice-session] unhandled: {}", msg_type);
                    }
                }
            });
        });

        let client = Arc::new(VoiceWsClient::new(ws_url.to_string(), handler));
        client.connect().await?;

        *self.ws_client.write().await = Some(client);
        info!("[voice-session] backend connected at {}", ws_url);
        Ok(())
    }

async fn download_vad_model(dest_path: &std::path::Path) -> Result<(), String> {
    info!("[voice-session] Downloading VAD model to {}...", dest_path.display());
    if let Some(parent) = dest_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("Failed to create parent dir: {}", e))?;
    }

    let urls = [
        "https://hf-mirror.com/csukuangfj/sherpa-onnx-silero-vad-model/resolve/main/silero_vad.onnx",
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
    ];

    let mut last_err = String::new();
    for url in &urls {
        match reqwest::get(*url).await {
            Ok(response) => {
                if !response.status().is_success() {
                    last_err = format!("HTTP error: {}", response.status());
                    continue;
                }
                match response.bytes().await {
                    Ok(bytes) => {
                        if let Err(e) = std::fs::write(dest_path, &bytes) {
                            return Err(format!("Failed to write VAD file: {}", e));
                        }
                        info!("[voice-session] VAD model downloaded successfully");
                        return Ok(());
                    }
                    Err(e) => {
                        last_err = format!("Failed to read body bytes: {}", e);
                    }
                }
            }
            Err(e) => {
                last_err = format!("Failed to connect: {}", e);
            }
        }
    }

    Err(format!("VAD download failed: {}", last_err))
}

    pub async fn ensure_initialized(&self) -> Result<(), String> {
        let home = dirs::home_dir();
        let evoloop_models = home.as_ref().map(|p| p.join(".evoloop/models"));
        let model_dirs: Vec<_> = self.model_search_paths.iter().cloned().map(Some)
            .chain([evoloop_models.clone()])
            .collect();

        if self.vad.read().await.is_some()
            && self.ws_client.read().await.is_some()
        {
            // If offline ASR is not loaded yet, check if the model dir exists now.
            // If it does, we should proceed to initialize/load it.
            let mut qwen3_exists = false;
            for dir in model_dirs.iter().flatten() {
                if find_qwen3_model_dir(dir).is_some() {
                    qwen3_exists = true;
                    break;
                }
            }
            if !qwen3_exists || self.offline_asr.read().await.is_some() {
                return Ok(());
            }
        }

        // 1. Resolve VAD path first. If missing, auto-download VAD to ~/.evoloop/models/silero_vad.onnx
        let mut vad_path = None;
        for dir in model_dirs.iter().flatten() {
            let vad_candidates = [
                Some(dir.join("silero_vad.onnx")),
                dir.parent().map(|p| p.join("silero_vad.onnx")),
            ];
            if let Some(path) = vad_candidates.iter().find_map(|p| {
                let p = p.as_ref()?;
                if p.exists() { Some(p.clone()) } else { None }
            }) {
                vad_path = Some(path);
                break;
            }
        }

        let vad_path = match vad_path {
            Some(path) => path,
            None => {
                if let Some(ref dir) = evoloop_models {
                    let target_vad_path = dir.join("silero_vad.onnx");
                    self.emit_log("VAD model missing. Downloading automatically...");
                    Self::download_vad_model(&target_vad_path).await?;
                    target_vad_path
                } else {
                    return Err("无法确定 VAD 模型存放路径，且未找到模型。".to_string());
                }
            }
        };

        // 2. Resolve Qwen3-ASR path (optional)
        let mut qwen3_dir = None;
        for dir in model_dirs.iter().flatten() {
            if let Some(dir) = find_qwen3_model_dir(dir) {
                qwen3_dir = Some(dir);
                break;
            }
        }

        let qwen3_path_str = qwen3_dir.as_ref().map(|p| p.to_string_lossy().into_owned());
        self.init_engines(
            &vad_path.to_string_lossy(),
            800.0,
            qwen3_path_str.as_deref(),
        ).await?;

        if self.ws_client.read().await.is_none() {
            let ws_url = format!("ws://127.0.0.1:{}/api/v1/voice/ws", BACKEND_PORT);
            self.connect_backend(&ws_url).await?;
        }

        Ok(())
    }

    /// Start a voice session.
    /// Begins microphone capture, VAD detection, and Qwen3-ASR recognition.
    pub async fn start(&self, thread_id: String, lang: String, mode: String) -> Result<(), String> {
        // Auto-initialize if not ready
        self.ensure_initialized().await?;

        if mode == "dictation" && self.offline_asr.read().await.is_none() {
            return Err("本地语音识别模型 (Qwen3-ASR) 未下载，无法使用听写模式。请在设置中下载模型。".to_string());
        }

        let vad = self.vad.read().await.as_ref().cloned().ok_or("VAD not initialized".to_string())?;
        let ws_client = self.ws_client.read().await.as_ref().cloned().ok_or("WS not connected".to_string())?;

        *self.thread_id.write().await = thread_id.clone();
        *self.lang.write().await = lang.clone();
        *self.mode.write().await = mode.clone();
        self.running.store(true, Ordering::SeqCst);
        self.dialogue_active.store(true, Ordering::SeqCst);

        // Notify backend
        ws_client.send_voice_start(&thread_id).await.ok();
        self.emit_log(&format!("voice session started, mode={}", mode));

        // Start microphone capture (must succeed before we emit listening)
        let audio_queue = self.audio_queue.clone();
        let sm = self.state_machine.clone();
        let tts = self.tts.clone();
        let tid = thread_id.clone();
        let running = self.running.clone();
        let dialogue_active = self.dialogue_active.clone();
        let event_bus = {
            let lock = self.event_bus.lock().unwrap();
            match lock.as_ref() {
                Some(b) => b.clone(),
                None => panic!("Event bus not set"),
            }
        };

        let mut mic = self.mic.write().await;
        let tid_clone = tid.clone();
        let ws_clone = ws_client.clone();
        let vad_clone = vad.clone();
        let sm_clone = sm.clone();
        let tts_clone = tts.clone();
        let event_bus_clone = event_bus.clone();
        let mode_clone = self.mode.clone();
        let lang_clone = self.lang.clone();
        let offline_asr_clone = self.offline_asr.clone();
        let llm_polish_clone = self.llm_polish_enabled.clone();
        let shared_state_clone = self.shared_state.clone();
        let seeduplex_clone = self.seeduplex.clone();
        let sd_connected = self.seeduplex_connected.clone();
        let rt_handle = tokio::runtime::Handle::current();

        mic.start(audio_queue, move |samples: &[f32]| {
            let rt = rt_handle.clone();
                if !running.load(Ordering::SeqCst) {
                    return;
                }
                if !dialogue_active.load(Ordering::SeqCst) {
                    return;
                }

                // Hybrid: send audio to Seeduplex for ASR + TTS
                if sd_connected.load(Ordering::SeqCst) {
                    let sd_client = seeduplex_clone.clone();
                    let mode_lock = mode_clone.clone();
                    let samples_vec = samples.to_vec();
                    rt.spawn(async move {
                        if *mode_lock.read().await == "dialogue" {
                            let sd = sd_client.read().await;
                            if let Some(ref client) = *sd {
                                let mut pcm = Vec::with_capacity(samples_vec.len() * 2);
                                for s in &samples_vec {
                                    let clamped = s.clamp(-1.0, 1.0);
                                    let sample = (clamped * i16::MAX as f32) as i16;
                                    pcm.extend_from_slice(&sample.to_le_bytes());
                                }
                                let _ = client.send_audio(&pcm);
                            }
                        }
                    });
                }

                // Feed to VAD first (used for both endpoint and barge-in detection).
                let segments = vad_clone.process(samples);
                let speech_active = vad_clone.is_speech_active();

                // Barge-in detection: if VAD sees speech while TTS is playing,
                // stop TTS and notify the backend.
                if tts_clone.is_speaking() || tts_clone.has_queued() || tts_clone.has_audio() {
                    if speech_active {
                        info!("[voice-session] barge-in detected by VAD");
                        tts_clone.stop();
                        tts_clone.resume();

                        let sm = sm_clone.clone();
                        let ws = ws_clone.clone();
                        let tid = tid_clone.clone();
                        let bus = event_bus_clone.clone();
                        rt.spawn(async move {
                            let _ = sm.force_set(VoiceState::Interrupted).await;
                            let _ = ws.send_barge_in(&tid).await;
                            bus.emit("voice:state", serde_json::json!({"state": "interrupted"}));
                        });
                    }
                }

                // Endpoint: finalize the utterance when VAD detects a speech segment end.
                if !segments.is_empty() {
                    let ws = ws_clone.clone();
                    let tid = tid_clone.clone();
                    let sm = sm_clone.clone();
                    let bus = event_bus_clone.clone();
                    let mode_for_task = mode_clone.clone();
                    let lang_for_task = lang_clone.clone();
                    let offline = offline_asr_clone.clone();
                    let audio_segments = segments.clone();
                    let llm_flag = llm_polish_clone.clone();
                    let shared_state = shared_state_clone.clone();
                    let sd_active = sd_connected.clone();
                    rt.spawn(async move {
                        // Hybrid: when Seeduplex is connected, skip Qwen3 ASR
                        if sd_active.load(Ordering::SeqCst) {
                            bus.emit("voice:log", serde_json::json!({"message": "Seeduplex ASR active"}));
                            return;
                        }

                        // Fallback: run Qwen3 offline ASR on the VAD segment audio
                        let recognized = if let Some(ref engine) = *offline.read().await {
                            let mut full_audio: Vec<f32> = Vec::new();
                            for seg in &audio_segments {
                                full_audio.extend_from_slice(seg);
                            }
                            if !full_audio.is_empty() {
                                match engine.recognize(&full_audio) {
                                    Ok(text) => {
                                        let t = text.trim().to_string();
                                        info!("[Qwen3-ASR] recognized: {}", t);
                                        bus.emit("voice:log", serde_json::json!({"message": format!("Qwen3 ASR: {}", t)}));
                                        t
                                    }
                                    Err(e) => {
                                        error!("[Qwen3-ASR] failed: {}", e);
                                        bus.emit("voice:log", serde_json::json!({"message": format!("Qwen3 ASR failed: {}", e)}));
                                        String::new()
                                    }
                                }
                            } else {
                                String::new()
                            }
                        } else {
                            info!("[voice-session] VAD endpoint detected but no ASR engine available (Seeduplex disconnected, Qwen3 not loaded)");
                            return;
                        };

                        if recognized.is_empty() {
                            return;
                        }

                        let mode = mode_for_task.read().await.clone();
                        if mode == "dictation" {
                            if recognized.chars().count() <= 5 {
                                bus.emit("voice:log", serde_json::json!({"message": format!("短文本跳过 LLM: {}", recognized)}));
                                dictation_paste(&recognized);
                            } else if llm_flag.load(std::sync::atomic::Ordering::Relaxed) {
                                let target_locale = lang_for_task.read().await.clone();
                                let pid = shared_state.read().await.get("project_id").cloned();
                                ws.send_dictation_finalize(&tid, &recognized, &target_locale, pid.as_deref()).await.ok();
                            } else {
                                bus.emit("voice:log", serde_json::json!({"message": format!("LLM 润色已关闭，直接粘贴: {}", recognized)}));
                                dictation_paste(&recognized);
                            }
                        } else {
                            let msg_id = Uuid::new_v4().to_string();
                            let pid = shared_state.read().await.get("project_id").cloned();
                            ws.send_route(&tid, &recognized, &msg_id, pid.as_deref()).await.ok();
                            let _ = sm.set(VoiceState::Processing).await;
                            bus.emit("voice:state", serde_json::json!({"state": "processing"}));
                        }
                    });
                }
            }).map_err(|e| {
                let msg = format!("麦克风启动失败: {}", e);
                error!("[voice-session] {}", msg);
                event_bus.emit("voice:error", serde_json::json!({"message": msg, "code": "MIC_FAILED"}));
                e
            })?;

        info!("[voice-session] microphone capture started");

        self.state_machine.set(VoiceState::Listening).await;
        self.emit_event("voice:state", serde_json::json!({"state": "listening"}));

        // Spawn a background task to monitor audio input device changes (e.g. plugging/unplugging Bluetooth mics)
        // and automatically hot-swap the capture stream.
        let running = self.running.clone();
        let mic_lock = self.mic.clone();
        let audio_queue = self.audio_queue.clone();
        let ws_client_lock = self.ws_client.clone();
        let vad_lock = self.vad.clone();
        let sm = self.state_machine.clone();
        let tts = self.tts.clone();
        let thread_id_lock = self.thread_id.clone();
        let mode_lock = self.mode.clone();
        let lang_lock = self.lang.clone();
        let offline_asr_lock = self.offline_asr.clone();
        let llm_polish_lock = self.llm_polish_enabled.clone();
        let shared_state_lock = self.shared_state.clone();
        let seeduplex_lock = self.seeduplex.clone();
        let dialogue_active = self.dialogue_active.clone();
        let event_bus_lock = self.event_bus.clone();

        tokio::spawn(async move {
            use cpal::traits::{DeviceTrait, HostTrait};
            let mut last_device = None;
            if let Some(device) = cpal::default_host().default_input_device() {
                if let Ok(name) = device.name() {
                    last_device = Some(name);
                }
            }

            while running.load(Ordering::SeqCst) {
                tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                if !running.load(Ordering::SeqCst) {
                    break;
                }

                let current_device = cpal::default_host().default_input_device().and_then(|d| d.name().ok());
                if current_device != last_device {
                    info!(
                        "[voice-session] default input device changed from {:?} to {:?}. Re-initializing stream...",
                        last_device, current_device
                    );
                    last_device = current_device;

                    // Stop current capture stream
                    {
                        let mut mic = mic_lock.write().await;
                        mic.stop();
                    }

                    let event_bus = {
                        let lock = event_bus_lock.lock().unwrap();
                        match lock.as_ref() {
                            Some(b) => b.clone(),
                            None => continue,
                        }
                    };

                    let ws_client = match ws_client_lock.read().await.as_ref() {
                        Some(ws) => ws.clone(),
                        None => continue,
                    };

                    let vad = match vad_lock.read().await.as_ref() {
                        Some(v) => v.clone(),
                        None => continue,
                    };

                    let tid = thread_id_lock.read().await.clone();
                    let mode = mode_lock.clone();
                    let lang = lang_lock.clone();
                    let offline_asr = offline_asr_lock.clone();
                    let llm_polish = llm_polish_lock.clone();
                    let shared_state = shared_state_lock.clone();
                    let seeduplex = seeduplex_lock.clone();

                    let tid_clone = tid.clone();
                    let ws_clone = ws_client.clone();
                    let vad_clone = vad.clone();
                    let sm_clone = sm.clone();
                    let tts_clone = tts.clone();
                    let event_bus_clone = event_bus.clone();
                    let mode_clone = mode.clone();
                    let lang_clone = lang.clone();
                    let offline_asr_clone = offline_asr.clone();
                    let llm_polish_clone = llm_polish.clone();
                    let shared_state_clone = shared_state.clone();
                    let seeduplex_clone = seeduplex.clone();
                    let rt_handle = tokio::runtime::Handle::current();
                    let running_clone = running.clone();
                    let dialogue_active_clone = dialogue_active.clone();

                    let start_res = {
                        let mut mic = mic_lock.write().await;
                        mic.start(audio_queue.clone(), move |samples: &[f32]| {
                            let rt = rt_handle.clone();
                            if !running_clone.load(Ordering::SeqCst) {
                                return;
                            }
                            if !dialogue_active_clone.load(Ordering::SeqCst) {
                                return;
                            }

                            // Seeduplex audio send
                            {
                                let sd_client = seeduplex_clone.clone();
                                let mode_lock = mode_clone.clone();
                                let samples_vec = samples.to_vec();
                                rt.spawn(async move {
                                    if *mode_lock.read().await == "dialogue" {
                                        let sd = sd_client.read().await;
                                        // Seeduplex is TTS-only; audio goes to Qwen3-ASR below.
                                    }
                                });
                            }

                            // VAD
                            let segments = vad_clone.process(samples);
                            let speech_active = vad_clone.is_speech_active();

                            if tts_clone.is_speaking() || tts_clone.has_queued() || tts_clone.has_audio() {
                                if speech_active {
                                    info!("[voice-session] barge-in detected by VAD during restart");
                                    tts_clone.stop();
                                    tts_clone.resume();

                                    let sm = sm_clone.clone();
                                    let ws = ws_clone.clone();
                                    let tid = tid_clone.clone();
                                    let bus = event_bus_clone.clone();
                                    rt.spawn(async move {
                                        let _ = sm.force_set(VoiceState::Interrupted).await;
                                        let _ = ws.send_barge_in(&tid).await;
                                        bus.emit("voice:state", serde_json::json!({"state": "interrupted"}));
                                    });
                                }
                            }

                            if !segments.is_empty() {
                                let ws = ws_clone.clone();
                                let tid = tid_clone.clone();
                                let sm = sm_clone.clone();
                                let bus = event_bus_clone.clone();
                                let mode_for_task = mode_clone.clone();
                                let lang_for_task = lang_clone.clone();
                                let offline = offline_asr_clone.clone();
                                let audio_segments = segments.clone();
                                let llm_flag = llm_polish_clone.clone();
                                let shared_state = shared_state_clone.clone();
                                rt.spawn(async move {
                                    let recognized = if let Some(ref engine) = *offline.read().await {
                                        let mut full_audio: Vec<f32> = Vec::new();
                                        for seg in &audio_segments {
                                            full_audio.extend_from_slice(seg);
                                        }
                                        if !full_audio.is_empty() {
                                            match engine.recognize(&full_audio) {
                                                Ok(text) => {
                                                    let t = text.trim().to_string();
                                                    info!("[Qwen3-ASR] (restarted) recognized: {}", t);
                                                    bus.emit("voice:log", serde_json::json!({"message": format!("Qwen3 ASR: {}", t)}));
                                                    t
                                                }
                                                Err(e) => {
                                                    error!("[Qwen3-ASR] (restarted) failed: {}", e);
                                                    bus.emit("voice:log", serde_json::json!({"message": format!("Qwen3 ASR failed: {}", e)}));
                                                    String::new()
                                                }
                                            }
                                        } else {
                                            String::new()
                                        }
                                    } else {
                                        String::new()
                                    };

                                    if recognized.is_empty() {
                                        return;
                                    }

                                    let mode = mode_for_task.read().await.clone();
                                    if mode == "dictation" {
                                        if recognized.chars().count() <= 5 {
                                            bus.emit("voice:log", serde_json::json!({"message": format!("短文本跳过 LLM: {}", recognized)}));
                                            dictation_paste(&recognized);
                                        } else if llm_flag.load(std::sync::atomic::Ordering::Relaxed) {
                                            let target_locale = lang_for_task.read().await.clone();
                                            let pid = shared_state.read().await.get("project_id").cloned();
                                            ws.send_dictation_finalize(&tid, &recognized, &target_locale, pid.as_deref()).await.ok();
                                        } else {
                                            let _ = bus.emit("voice:log", serde_json::json!({"message": format!("LLM 润色已关闭，直接粘贴: {}", recognized)}));
                                            dictation_paste(&recognized);
                                        }
                                    } else {
                                        let msg_id = Uuid::new_v4().to_string();
                                        let pid = shared_state.read().await.get("project_id").cloned();
                                        ws.send_route(&tid, &recognized, &msg_id, pid.as_deref()).await.ok();
                                        let _ = sm.set(VoiceState::Processing).await;
                                        bus.emit("voice:state", serde_json::json!({"state": "processing"}));
                                    }
                                });
                            }
                        })
                    };

                    match start_res {
                        Ok(_) => info!("[voice-session] stream restarted successfully on {:?}", last_device),
                        Err(err) => error!("[voice-session] failed to restart stream: {}", err),
                    }
                }
            }
        });

        info!("[voice-session] started for thread {}", thread_id);
        Ok(())
    }

    /// Switch voice mode without restarting mic/capture.
    pub async fn switch_mode(&self, mode: String) -> Result<(), String> {
        if !self.running.load(Ordering::SeqCst) {
            return Err("Voice session not running".to_string());
        }

        *self.mode.write().await = mode.clone();
        self.state_machine.set(VoiceState::Listening).await;
        self.emit_event("voice:state", serde_json::json!({"state": "listening"}));

        info!("[voice-session] switched mode to {}", mode);
        Ok(())
    }

    /// Stop the voice dialogue session.
    pub async fn stop(&self) {
        self.dialogue_active.store(false, Ordering::SeqCst);
        self.running.store(false, Ordering::SeqCst);

        let thread_id = self.thread_id.read().await.clone();
        if !thread_id.is_empty() {
            if let Some(ws) = self.ws_client.read().await.as_ref() {
                ws.send_voice_stop(&thread_id).await.ok();
            }
        }

        self.mic.write().await.stop();
        // Let CoreAudio settle after VoiceProcessingIO shutdown,
        // so the next mic.start() doesn't hit a stale audio route.
        tokio::time::sleep(std::time::Duration::from_millis(300)).await;
        self.tts.stop();
        self.tts.resume();
        self.state_machine.force_set(VoiceState::Idle).await;
        self.emit_event("voice:state", serde_json::json!({"state": "idle"}));

        info!("[voice-session] stopped");
    }

    /// Trigger barge-in manually (e.g. from UI button).
    pub async fn barge_in(&self) {
        let thread_id = self.thread_id.read().await.clone();
        if let Some(ws) = self.ws_client.read().await.as_ref() {
            ws.send_barge_in(&thread_id).await.ok();
        }
        self.tts.stop();
        self.tts.resume();
        self.state_machine
            .force_set(VoiceState::Interrupted)
            .await;
        self.emit_event("voice:state", serde_json::json!({"state": "interrupted"}));
        info!("[voice-session] barge-in triggered");
    }

    pub async fn get_state(&self) -> VoiceState {
        self.state_machine.get().await
    }

    pub fn set_tts_engine(&self, kind: TtsEngineKind) {
        self.tts.set_engine(kind);
    }

    pub fn get_tts_engine(&self) -> TtsEngineKind {
        self.tts.get_engine()
    }

    pub fn set_tts_voice(&self, voice: String) {
        self.tts.set_voice(voice);
    }

    pub fn get_tts_voice(&self) -> String {
        self.tts.get_voice()
    }

    pub fn set_tts_speed(&self, speed: f32) {
        self.tts.set_speed(speed);
    }

    pub fn get_tts_speed(&self) -> f32 {
        self.tts.get_speed()
    }

    /// Speak a single sentence through the TTS engine (queued, non-blocking).
    pub fn speak_sentence(&self, text: &str) {
        self.tts.queue_sentence(text.to_string());
        self.tts.speak_next("zh-CN");
    }

    pub async fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    pub async fn disconnect_backend(&self) {
        if let Some(ws) = self.ws_client.write().await.take() {
            ws.disconnect().await;
        }
    }
}

/// Find Qwen3 model directory inside parent_dir (direct match or dynamic scan).
fn find_qwen3_model_dir(parent_dir: &std::path::Path) -> Option<PathBuf> {
    // 1. Direct match: parent_dir / "qwen3-asr"
    let direct = parent_dir.join("qwen3-asr");
    if direct.join("encoder.int8.onnx").exists() || direct.join("encoder.onnx").exists() {
        return Some(direct);
    }

    // 2. Direct match: parent_dir / "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25"
    let direct_named = parent_dir.join("sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25");
    if direct_named.join("encoder.int8.onnx").exists() || direct_named.join("encoder.onnx").exists() {
        return Some(direct_named);
    }

    // 3. Dynamic scan: read_dir for any subdirectory containing "qwen3" and encoder model
    if let Ok(entries) = std::fs::read_dir(parent_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("").to_lowercase();
                if name.contains("qwen3") {
                    if path.join("encoder.int8.onnx").exists() || path.join("encoder.onnx").exists() {
                        return Some(path);
                    }
                }
            }
        }
    }

    None
}

/// Resolve the spoken confirmation text for a L0 local action.
pub(crate) fn resolve_confirmation(action: &str, lang: &str) -> &'static str {
    let confirmations: &[&str] = if lang.starts_with("zh") {
        &["好的", "搞定了", "嗯哼", "没问题", "好嘞", "收到", "可以了", "行", "OK", "没问题了"]
    } else {
        &["OK", "Got it", "Done", "Sure", "Alright", "No problem", "Gotcha", "All set", "Done deal", "Easy"]
    };
    let idx = action.bytes().fold(0u64, |acc, b| acc.wrapping_mul(31).wrapping_add(b as u64));
    confirmations[(idx % confirmations.len() as u64) as usize]
}

/// Handle a `voice.route_result` message: decide what to speak via TTS.
pub(crate) async fn handle_route_result(
    body: &serde_json::Value,
    session_tts: &TtsEngine,
    session_state: &VoiceStateMachine,
    session_lang: &RwLock<String>,
    event_bus: &Arc<dyn VoiceEventBus>,
    session_seeduplex: &RwLock<Option<SeeduplexClient>>,
) {
    let status = body.get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    // When Seeduplex is connected, TTS audio comes via inject_tts().
    // The route_result still needs to drive state transitions but
    // should skip the traditional TTS path.
    let seeduplex_active = session_seeduplex.read().await.is_some();

    if status == "routed" {
        let target_type = body.get("target")
            .and_then(|t| t.get("type"))
            .and_then(|v| v.as_str());
        let lang = session_lang.read().await.clone();
        match target_type {
            Some("local") => {
                // L0 hit: speak action confirmation
                let confirmation = resolve_confirmation(
                    body.get("target")
                        .and_then(|t| t.get("action"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("ok"),
                    &lang,
                );
                session_tts.stop();
                session_tts.resume();
                session_tts.queue_sentence(confirmation.to_string());
                session_tts.speak_next(&lang);
            }
            _ => {
                // Agent early ack: speak summary immediately so the user
                // hears a response while the agent finalises.
                // Duplicate routed events (same text) are deduplicated by
                // checking whether the text is already queued/speaking.
                if let Some(text) = body.get("summary").and_then(|v| v.as_str()) {
                    let s = text.trim();
                    if !s.is_empty() && !session_tts.has_queued_text(s) {
                        let preview: String = s.chars().take(40).collect();
                        info!("[tts] route_result routed → early ack: {}...", preview);
                        session_tts.queue_sentence(s.to_string());
                        session_tts.speak_next(&lang);
                    } else {
                        info!("[tts] route_result routed — duplicate, skipped");
                    }
                }
            }
        }
    } else if status == "done" || status == "failed" || status == "cancelled" {
        let lang = session_lang.read().await.clone();
        if status == "failed" {
            session_tts.stop();
            session_tts.resume();
            session_tts.queue_sentence("抱歉，处理出错了".to_string());
            info!("[tts] route_result failed → error message");
            session_tts.speak_next(&lang);
        } else if status == "done" {
            if let Some(text) = body.get("summary").and_then(|v| v.as_str()) {
                let s = text.trim();
                if !s.is_empty() {
                    // If done's text is already queued/spoken by a prior routed event,
                    // skip to avoid duplicate speech. Otherwise force-stop and speak.
                    if session_tts.has_queued_text(s) || session_tts.is_speaking() {
                        // Already being spoken by the routed early-ack — nothing to do.
                        info!("[tts] route_result done — text already queued by routed, skipping duplicate");
                    } else {
                        let preview: String = s.chars().take(40).collect();
                        info!("[tts] route_result done → speaking: {}...", preview);
                        session_tts.stop();
                        session_tts.resume();
                            session_tts.queue_sentence(s.to_string());
                            session_tts.speak_next(&lang);
                        }
                }
            }
        }
        session_state.force_set(VoiceState::Listening).await;
        event_bus.emit("voice:state", serde_json::json!({"state": "listening"}));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_confirmation_returns_valid_phrase() {
        let result = resolve_confirmation("mute", "zh-CN");
        let valid = ["好的", "搞定了", "嗯哼", "没问题", "好嘞", "收到", "可以了", "行", "OK", "没问题了"];
        assert!(valid.contains(&result), "unexpected: {}", result);
    }

    #[test]
    fn test_resolve_confirmation_english() {
        let result = resolve_confirmation("mute", "en-US");
        let valid = ["OK", "Got it", "Done", "Sure", "Alright", "No problem", "Gotcha", "All set", "Done deal", "Easy"];
        assert!(valid.contains(&result), "unexpected: {}", result);
    }

    #[test]
    fn test_resolve_confirmation_consistent_per_action() {
        assert_eq!(resolve_confirmation("mute", "zh"), resolve_confirmation("mute", "zh"));
        assert_eq!(resolve_confirmation("screenshot", "en"), resolve_confirmation("screenshot", "en"));
    }

    mod handler {
        use super::*;
        use std::collections::VecDeque;
        use std::sync::{Arc, Mutex};
use tokio::sync::RwLock;
use tokio::sync::mpsc;

        struct NoopEventBus;
        impl VoiceEventBus for NoopEventBus {
            fn emit(&self, _event: &str, _payload: serde_json::Value) {}
        }
        fn noop_bus() -> Arc<dyn VoiceEventBus> { Arc::new(NoopEventBus) }

        fn make_body(status: &str, target_type: &str, action: &str) -> serde_json::Value {
            serde_json::json!({
                "thread_id": "test-tid",
                "status": status,
                "target": {"type": target_type, "action": action},
                "params": {},
                "candidates": [],
            })
        }

        fn make_done_body(summary: &str) -> serde_json::Value {
            serde_json::json!({
                "thread_id": "test-tid",
                "status": "done",
                "summary": summary,
            })
        }

        #[tokio::test]
        async fn test_l0_local_hit_triggers_speak() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = make_body("routed", "local", "mute");
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert!(tts.is_speaking(), "L0 local hit should trigger TTS");
        }

        #[tokio::test]
        async fn test_agent_routed_triggers_speak() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = serde_json::json!({
                "thread_id": "test-tid",
                "status": "routed",
                "summary": "正在为你查询，请稍候",
            });
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert!(tts.is_speaking(), "agent routed should trigger TTS");
        }

        #[tokio::test]
        async fn test_done_speaks_summary() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = make_done_body("已为你完成操作");
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert!(tts.is_speaking(), "done should speak summary");
        }

        #[tokio::test]
        async fn test_done_empty_summary_no_speak() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = make_done_body("");
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert!(!tts.is_speaking(), "empty summary should not speak");
        }

        #[tokio::test]
        async fn test_empty_summary_transitions_idle() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = make_done_body("");
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert_eq!(sm.get().await, VoiceState::Listening);
        }

        #[tokio::test]
        async fn test_failed_speaks_error() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = serde_json::json!({
                "thread_id": "test-tid",
                "status": "failed",
                "summary": "something broke",
            });
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert!(tts.is_speaking(), "failed should speak error");
        }

        #[tokio::test]
        async fn test_cancelled_no_speak() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = serde_json::json!({
                "thread_id": "test-tid",
                "status": "cancelled",
            });
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert!(!tts.is_speaking(), "cancelled should not speak");
        }

        #[tokio::test]
        async fn test_cancelled_transitions_idle() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = serde_json::json!({
                "thread_id": "test-tid",
                "status": "cancelled",
            });
            let bus = noop_bus();
            handle_route_result(&body, &tts, &sm, &lang, &bus, &RwLock::new(None)).await;

            assert_eq!(sm.get().await, VoiceState::Listening);
        }
    }
}
