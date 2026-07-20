use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tokio::sync::RwLock;
use log::{info, warn, error};
use uuid::Uuid;

use super::offline_asr::OfflineAsrEngine;
use super::vad_engine::VadEngine;
use super::tts_engine::{TtsEngine, TtsEngineKind};
use super::aec_engine::AecMicCapture;
use super::event::VoiceEventBus;
use super::state_machine::{VoiceState, VoiceStateMachine};
use super::ws_client::{VoiceEnvelope, VoiceWsClient};

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
    thread_id: Arc<RwLock<String>>,
    running: Arc<AtomicBool>,
    lang: Arc<RwLock<String>>,
    mode: Arc<RwLock<String>>,
    dialogue_active: Arc<AtomicBool>,
    audio_queue: Arc<Mutex<VecDeque<f32>>>,
    event_bus: Arc<Mutex<Option<Arc<dyn VoiceEventBus>>>>,
    model_search_paths: Vec<PathBuf>,
    llm_polish_enabled: Arc<AtomicBool>,
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
        qwen3_model_dir: &str,
    ) -> Result<(), String> {
        let vad = VadEngine::new(vad_model_path, vad_silence_ms)?;
        *self.vad.write().await = Some(vad);

        match OfflineAsrEngine::new(qwen3_model_dir) {
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
        let _session_thread_id = self.thread_id.clone();

        let handler = Arc::new(move |envelope: VoiceEnvelope| {
            let session_state = session_state.clone();
            let session_tts = session_tts.clone();
            let session_lang = session_lang.clone();
            let _session_thread_id = _session_thread_id.clone();
            let event_bus = event_bus.clone();

            // Do not block the WebSocket read loop; dispatch to async task.
            tokio::spawn(async move {
                let msg_type = envelope.msg_type.as_str();
                let body = envelope.body.unwrap_or(serde_json::Value::Null);

                match msg_type {
                    "voice.route_result" => {
                        event_bus.emit("voice:route_result", body.clone());
                        handle_route_result(
                            &body, &session_tts, &session_state, &session_lang
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
                                dictation_paste(text);
                            }
                        }
                        event_bus.emit("voice:dictation_polished", body.clone());
                    }

                    "system.init" => {
                        info!("[voice-session] backend handshake received");
                    }

                    "system.error" => {
                        let code = body.get("code").and_then(|v| v.as_str()).unwrap_or("unknown");
                        let message = body.get("message").and_then(|v| v.as_str()).unwrap_or("");
                        warn!("[voice-session] backend error: {} {}", code, message);
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

    pub async fn ensure_initialized(&self) -> Result<(), String> {
        if self.offline_asr.read().await.is_some()
            && self.vad.read().await.is_some()
            && self.ws_client.read().await.is_some()
        {
            return Ok(());
        }

        // Search: configured paths + hardcoded fallbacks
        let home = dirs::home_dir();
        let evoloop_models = home.as_ref().map(|p| p.join(".evoloop/models"));
        let model_dirs: Vec<_> = self.model_search_paths.iter().cloned().map(Some)
            .chain([evoloop_models.clone()])
            .collect();

        let mut found = false;

        for dir in model_dirs.iter().flatten() {
            let qwen3_dir = find_qwen3_model_dir(dir);
            if qwen3_dir.is_none() {
                self.emit_log(&format!("no Qwen3 model at {}", dir.display()));
                continue;
            }
            let qwen3_dir = qwen3_dir.unwrap();

            // Try VAD in same dir, then in parent dir (prototype layout)
            let vad_candidates = [
                Some(dir.join("silero_vad.onnx")),
                dir.parent().map(|p| p.join("silero_vad.onnx")),
            ];
            let vad_path = vad_candidates.iter().find_map(|p| {
                let p = p.as_ref()?;
                if p.exists() { Some(p.clone()) } else { None }
            });

            if let Some(vad_path) = vad_path {
                self.emit_log(&format!("models found at {}, VAD at {}", qwen3_dir.display(), vad_path.display()));
                self.init_engines(
                    &vad_path.to_string_lossy(),
                    800.0,
                    &qwen3_dir.to_string_lossy(),
                ).await?;

                let ws_url = format!("ws://127.0.0.1:{}/api/v1/voice/ws", BACKEND_PORT);
                self.connect_backend(&ws_url).await?;

                found = true;
                break;
            }
        }

        if !found {
            return Err(
                "语音模型文件未找到。请运行 deploy/download_models.sh --all 下载模型。"
                    .to_string(),
            );
        }

        Ok(())
    }

    /// Start a voice session.
    /// Begins microphone capture, VAD detection, and Qwen3-ASR recognition.
    pub async fn start(&self, thread_id: String, lang: String, mode: String) -> Result<(), String> {
        // Auto-initialize if not ready
        self.ensure_initialized().await?;

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

        self.state_machine.set(VoiceState::Listening).await;
        self.emit_event("voice:state", serde_json::json!({"state": "listening"}));

        // Start microphone capture
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
        let rt_handle = tokio::runtime::Handle::current();

        mic.start(audio_queue, move |samples: &[f32]| {
            let rt = rt_handle.clone();
                if !running.load(Ordering::SeqCst) {
                    return;
                }
                if !dialogue_active.load(Ordering::SeqCst) {
                    return;
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
                    rt.spawn(async move {
                        // Run Qwen3 offline ASR on the VAD segment audio
                        let recognized = if let Some(ref engine) = *offline.read().await {
                            let mut full_audio: Vec<f32> = Vec::new();
                            for seg in &audio_segments {
                                full_audio.extend_from_slice(seg);
                            }
                            if !full_audio.is_empty() {
                                match engine.recognize(&full_audio) {
                                    Ok(text) => {
                                        let t = text.trim().to_string();
                                        bus.emit("voice:log", serde_json::json!({"message": format!("Qwen3 ASR: {}", t)}));
                                        t
                                    }
                                    Err(e) => {
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
                                ws.send_dictation_finalize(&tid, &recognized, &target_locale).await.ok();
                            } else {
                                bus.emit("voice:log", serde_json::json!({"message": format!("LLM 润色已关闭，直接粘贴: {}", recognized)}));
                                dictation_paste(&recognized);
                            }
                        } else {
                            let msg_id = Uuid::new_v4().to_string();
                            ws.send_route(&tid, &recognized, &msg_id).await.ok();
                            let _ = sm.set(VoiceState::Processing).await;
                            bus.emit("voice:state", serde_json::json!({"state": "processing"}));
                        }
                    });
                }
            }).map_err(|e| e)?;

        info!("[voice-session] started for thread {}", thread_id);
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
pub(crate) fn resolve_confirmation(action: &str) -> &'static str {
    match action {
        "mute" => "已静音",
        "unmute" => "已恢复",
        "lock_screen" => "已锁屏",
        "screenshot" => "已截图",
        "end" => "再见",
        _ => "好的",
    }
}

/// Handle a `voice.route_result` message: decide what to speak via TTS.
pub(crate) async fn handle_route_result(
    body: &serde_json::Value,
    session_tts: &TtsEngine,
    session_state: &VoiceStateMachine,
    session_lang: &RwLock<String>,
) {
    let status = body.get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    if status == "routed" {
        let target_type = body.get("target")
            .and_then(|t| t.get("type"))
            .and_then(|v| v.as_str());
        let lang = session_lang.read().await.clone();
        match target_type {
            Some("local") => {
                // L0 hit: speak action-specific confirmation
                let confirmation = body.get("target")
                    .and_then(|t| t.get("action"))
                    .and_then(|v| v.as_str())
                    .map(resolve_confirmation)
                    .unwrap_or("好的");
                session_tts.queue_sentence(confirmation.to_string());
                session_tts.speak_next(&lang);
            }
            _ => {
                // Agent ack from VoiceChannel or old-style agent routed:
                // speak the summary content directly (Supervisor's natural language)
                if let Some(text) = body.get("summary").and_then(|v| v.as_str()) {
                    let s = text.trim();
                    if !s.is_empty() {
                        session_tts.queue_sentence(s.to_string());
                        session_tts.speak_next(&lang);
                    }
                }
            }
        }
    } else if status == "done" || status == "failed" || status == "cancelled" {
        let lang = session_lang.read().await.clone();
        if status == "failed" {
            session_tts.queue_sentence("抱歉，处理出错了".to_string());
            session_tts.speak_next(&lang);
        }
        // "done" TTS is handled by voice.tts_boundary, not here

        if !session_tts.has_queued() && !session_tts.is_speaking() {
            let _ = session_state.set(VoiceState::Idle).await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_confirmation_mute() {
        assert_eq!(resolve_confirmation("mute"), "已静音");
    }

    #[test]
    fn test_resolve_confirmation_unmute() {
        assert_eq!(resolve_confirmation("unmute"), "已恢复");
    }

    #[test]
    fn test_resolve_confirmation_screenshot() {
        assert_eq!(resolve_confirmation("screenshot"), "已截图");
    }

    #[test]
    fn test_resolve_confirmation_lock_screen() {
        assert_eq!(resolve_confirmation("lock_screen"), "已锁屏");
    }

    #[test]
    fn test_resolve_confirmation_end() {
        assert_eq!(resolve_confirmation("end"), "再见");
    }

    #[test]
    fn test_resolve_confirmation_default() {
        assert_eq!(resolve_confirmation("open_app"), "好的");
        assert_eq!(resolve_confirmation("play_pause"), "好的");
        assert_eq!(resolve_confirmation("unknown_action"), "好的");
    }

    mod handler {
        use super::*;
        use std::collections::VecDeque;
        use std::sync::{Arc, Mutex};
        use tokio::sync::RwLock;

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
            handle_route_result(&body, &tts, &sm, &lang).await;

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
            handle_route_result(&body, &tts, &sm, &lang).await;

            assert!(tts.is_speaking(), "agent routed should trigger TTS");
        }

        #[tokio::test]
        async fn test_done_speaks_summary() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = make_done_body("已为你完成操作");
            handle_route_result(&body, &tts, &sm, &lang).await;

            assert!(tts.is_speaking());
        }

        #[tokio::test]
        async fn test_done_empty_summary_no_speak() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = make_done_body("");
            handle_route_result(&body, &tts, &sm, &lang).await;

            assert!(!tts.is_speaking(), "empty summary should not speak");
        }

        #[tokio::test]
        async fn test_empty_summary_transitions_idle() {
            let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
            let sm = VoiceStateMachine::new();
            let lang = RwLock::new("zh-CN".to_string());

            let body = make_done_body("");
            handle_route_result(&body, &tts, &sm, &lang).await;

            assert_eq!(sm.get().await, VoiceState::Idle);
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
            handle_route_result(&body, &tts, &sm, &lang).await;

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
            handle_route_result(&body, &tts, &sm, &lang).await;

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
            handle_route_result(&body, &tts, &sm, &lang).await;

            assert_eq!(sm.get().await, VoiceState::Idle);
        }
    }
}
