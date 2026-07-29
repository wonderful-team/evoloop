use std::collections::{VecDeque, HashMap};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::RwLock;
use log::{info, warn, error};
use std::path::PathBuf;
use std::io::Write;
use std::process::{Command, Stdio, Child, ChildStdin};

use crate::voice::ws_client::{VoiceWsClient, VoiceEnvelope};
use crate::voice::aec_engine::AecMicCapture;
use crate::voice::event::VoiceEventBus;

#[cfg(target_os = "macos")]
pub fn dictation_paste(text: &str) {
    use cocoa::base::nil;
    use cocoa::foundation::NSString;
    use objc::{msg_send, sel, sel_impl};

    unsafe {
        let pasteboard: *mut objc::runtime::Object = msg_send![objc::class!(NSPasteboard), generalPasteboard];
        let _: () = msg_send![pasteboard, clearContents];
        let str_obj = NSString::alloc(nil).init_str(text);
        let type_string = NSString::alloc(nil).init_str("public.utf8-plain-text");

        // Declare types on pasteboard
        let types_array: *mut objc::runtime::Object = msg_send![objc::class!(NSArray), arrayWithObject:type_string];
        let _: () = msg_send![pasteboard, declareTypes:types_array owner:nil];
        let _: bool = msg_send![pasteboard, setString:str_obj forType:type_string];

    }

    use core_graphics::event::{CGEvent, CGEventTapLocation, CGKeyCode};
    let source = core_graphics::event_source::CGEventSource::new(core_graphics::event_source::CGEventSourceStateID::CombinedSessionState).unwrap();
    let cmd: CGKeyCode = 55;
    let v: CGKeyCode = 9;

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
    mic: Arc<RwLock<AecMicCapture>>,
    ws_client: Arc<RwLock<Option<Arc<VoiceWsClient>>>>,
    thread_id: Arc<RwLock<String>>,
    running: Arc<AtomicBool>,
    lang: Arc<RwLock<String>>,
    mode: Arc<RwLock<String>>,
    audio_queue: Arc<Mutex<VecDeque<f32>>>,
    event_bus: Arc<Mutex<Option<Arc<dyn VoiceEventBus>>>>,
    shared_state: Arc<RwLock<HashMap<String, String>>>,
    tts_voice: Arc<RwLock<String>>,
    tts_speed: Arc<RwLock<f32>>,
    // TTS playback state — ffplay streaming
    ffplay_stdin: Arc<Mutex<Option<ChildStdin>>>,
    ffplay_child: Arc<Mutex<Option<Child>>>,
    last_activity: Arc<AtomicU64>,
}

impl VoiceSession {
    pub fn new(_model_search_paths: Vec<PathBuf>) -> Self {
        Self {
            mic: Arc::new(RwLock::new(AecMicCapture::new())),
            ws_client: Arc::new(RwLock::new(None)),
            thread_id: Arc::new(RwLock::new(String::new())),
            running: Arc::new(AtomicBool::new(false)),
            lang: Arc::new(RwLock::new("zh-CN".to_string())),
            mode: Arc::new(RwLock::new("dialogue".to_string())),
            audio_queue: Arc::new(Mutex::new(VecDeque::new())),
            event_bus: Arc::new(Mutex::new(None)),
            shared_state: Arc::new(RwLock::new(HashMap::new())),
            tts_voice: Arc::new(RwLock::new(String::new())),
            tts_speed: Arc::new(RwLock::new(1.0)),
            ffplay_stdin: Arc::new(Mutex::new(None)),
            ffplay_child: Arc::new(Mutex::new(None)),
            last_activity: Arc::new(AtomicU64::new(0)),
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

    pub async fn init_engines(
        &self,
        _vad_model_path: &str,
        _vad_silence_ms: f32,
        _qwen3_model_dir: Option<&str>,
    ) -> Result<(), String> {
        info!("[voice-session] init_engines (no-op, engines run in Python)");
        Ok(())
    }

    pub async fn connect_backend(&self, ws_url: &str) -> Result<(), String> {
        let event_bus = {
            let lock = self.event_bus.lock().unwrap();
            lock.as_ref().cloned().ok_or("Event bus not set")?
        };
        let session_audio_queue = self.audio_queue.clone();
        let session_shared_state = self.shared_state.clone();
        let ffplay_stdin = self.ffplay_stdin.clone();
        let ffplay_child = self.ffplay_child.clone();

        let handler = Arc::new(move |envelope: VoiceEnvelope| {
            let msg_type = envelope.msg_type.clone();
            let body = envelope.body.clone().unwrap_or(serde_json::Value::Null);
            let session_audio_queue = session_audio_queue.clone();
            let session_shared_state = session_shared_state.clone();
            let event_bus = event_bus.clone();
            let ffplay_stdin = ffplay_stdin.clone();
            let ffplay_child = ffplay_child.clone();

            if msg_type == "voice.audio_frame" {
                tokio::task::spawn_blocking(move || {
                    use std::io::Write as IoWrite;
                    if let Some(bytes) = envelope.raw_bytes {
                        let mut stdin_guard = ffplay_stdin.lock().unwrap();
                        if stdin_guard.is_none() {
                            info!("[tts-play] spawning ffplay (first audio frame, {}b)", bytes.len());
                            let child = Command::new("ffplay")
                                .args(["-f", "f32le", "-ar", "24000", "-nodisp", "-autoexit", "-"])
                                .stdin(Stdio::piped())
                                .stderr(Stdio::null())
                                .spawn();
                            match child {
                                Ok(mut c) => {
                                    let stdin = c.stdin.take()
                                        .expect("failed to capture ffplay stdin");
                                    *stdin_guard = Some(stdin);
                                    *ffplay_child.lock().unwrap() = Some(c);
                                    info!("[tts-play] ffplay spawned OK");
                                }
                                Err(e) => {
                                    warn!("[tts-play] ffplay spawn failed: {}", e);
                                    drop(stdin_guard);
                                    return;
                                }
                            }
                        }
                        if let Some(stdin) = stdin_guard.as_mut() {
                            if let Err(e) = stdin.write_all(&bytes) {
                                warn!("[tts-play] ffplay write failed ({}b): {} — resetting", bytes.len(), e);
                                *stdin_guard = None;
                                *ffplay_child.lock().unwrap() = None;
                            }
                        }
                        let dump_path = std::env::temp_dir().join("tts_debug_raw.pcm");
                        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&dump_path) {
                            let _ = f.write_all(&bytes);
                        }
                    }
                });
                return;
            }

            tokio::spawn(async move {
                let mt = msg_type.as_str();
                match mt {
                    "voice.barge_in" | "voice.cancel" => {
                        info!("[tts-play] barge_in/cancel — killing ffplay");
                        session_audio_queue.lock().unwrap().clear();
                        // Kill ffplay and close stdin
                        if let Ok(mut stdin_guard) = ffplay_stdin.lock() {
                            drop(stdin_guard.take());
                        }
                        if let Ok(mut child) = ffplay_child.lock() {
                            if let Some(ref mut c) = *child {
                                let _ = c.kill();
                                let _ = c.wait();
                            }
                            *child = None;
                        }
                        event_bus.emit("voice:state", serde_json::json!({"state": "interrupted"}));
                    }
                    "dictation.paste" => {
                        if let Some(text) = body.get("text").and_then(|v| v.as_str()) {
                            dictation_paste(text);
                        }
                    }
                    "system.init" => {
                        if let Some(state) = body.get("state").and_then(|v| v.as_object()) {
                            let mut cache = session_shared_state.write().await;
                            for (k, v) in state {
                                if let Some(val) = v.as_str() {
                                    cache.insert(k.clone(), val.to_string());
                                }
                            }
                            event_bus.emit("system:state_snapshot", serde_json::to_value(state).unwrap_or_default());
                        }
                        if let Some(configs) = body.get("configs").and_then(|v| v.as_object()) {
                            event_bus.emit("system:config_snapshot", serde_json::to_value(configs).unwrap_or_default());
                        }
                    }
                    "system.error" => {
                        event_bus.emit("voice:error", body.clone());
                        event_bus.emit("system:error", body.clone());
                    }
                    "system.state_changed" => {
                        if let (Some(key), Some(value)) = (
                            body.get("key").and_then(|v| v.as_str()),
                            body.get("value").and_then(|v| v.as_str()),
                        ) {
                            session_shared_state.write().await.insert(key.to_string(), value.to_string());
                        }
                        event_bus.emit("system:state_changed", body.clone());
                    }
                    "system.config_changed" => {
                        if let (Some(key), Some(value)) = (
                            body.get("key").and_then(|v| v.as_str()),
                            body.get("new_value").and_then(|v| v.as_str()),
                        ) {
                            session_shared_state.write().await.insert(key.to_string(), value.to_string());
                        }
                        event_bus.emit("system:config_changed", body.clone());
                    }
                    "voice:state" => {
                        info!("[tts-play] received msg_type=voice:state (non-audio event)");
                        let is_listening = body.get("state").and_then(|v| v.as_str()) == Some("listening");
                        let event_name = msg_type.replace(".", ":");
                        event_bus.emit(&event_name, body);
                        if is_listening {
                            if let Ok(mut stdin_guard) = ffplay_stdin.lock() {
                                if stdin_guard.is_some() {
                                    info!("[tts-play] state=listening — closing ffplay stdin");
                                    drop(stdin_guard.take());
                                }
                            }
                        }
                    }
                    _ => {
                        info!("[tts-play] received msg_type={} (non-audio event)", msg_type);
                        let event_name = msg_type.replace(".", ":");
                        event_bus.emit(&event_name, body);
                    }
                }
            });
        });

        let ws = Arc::new(VoiceWsClient::new(ws_url.to_string(), handler));
        ws.connect().await?;
        *self.ws_client.write().await = Some(ws);
        Ok(())
    }

    pub async fn start(&self, thread_id: String, lang: String, mode: String) -> Result<(), String> {
        let ws_client = {
            let read_lock = self.ws_client.read().await;
            if read_lock.is_none() {
                drop(read_lock);
                let port = crate::sidecar::BACKEND_PORT;
                let ws_url = format!("ws://127.0.0.1:{}/api/v1/voice/ws", port);
                info!("[voice-session] WS not connected, attempting auto-connection to {}", ws_url);
                self.connect_backend(&ws_url).await?;
                self.ws_client.read().await.as_ref().cloned().ok_or("WS connection failed")?
            } else {
                read_lock.as_ref().cloned().ok_or("WS not connected")?
            }
        };

        *self.thread_id.write().await = thread_id.clone();
        *self.lang.write().await = lang.clone();
        *self.mode.write().await = mode.clone();
        self.running.store(true, Ordering::SeqCst);

        // Notify Python backend to start session
        if let Err(e) = ws_client.send_voice_start(&thread_id, &mode).await {
            warn!("[voice-session] failed to notify backend (connection dead), resetting: {}", e);
            drop(ws_client);
            *self.ws_client.write().await = None;
            return Err(format!("backend not reachable: {}", e));
        }
        self.emit_log(&format!("voice session started, mode={}", mode));

        // Start microphone capture and stream to backend
        let audio_queue = self.audio_queue.clone();
        let running = self.running.clone();
        let ws = ws_client.clone();
        let rt_handle = tokio::runtime::Handle::current();

        // 10min inactivity timeout (dialogue only)
        if mode == "dialogue" {
            let running = self.running.clone();
            let ws = ws_client.clone();
            let tid = thread_id.clone();
            let activity = self.last_activity.clone();
            let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
            activity.store(now, Ordering::SeqCst);
            tokio::spawn(async move {
                loop {
                    tokio::time::sleep(Duration::from_secs(30)).await;
                    if !running.load(Ordering::SeqCst) { break; }
                    let last = activity.load(Ordering::SeqCst);
                    if last == 0 { continue; }
                    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() - last;
                    if elapsed > 600 {
                        info!("[voice-session] 10min inactivity timeout for {}", tid);
                        let _ = ws.send("voice.cancel",
                            serde_json::json!({"thread_id": tid})).await;
                        break;
                    }
                }
            });
        }

        let mut mic = self.mic.write().await;
        mic.start(audio_queue, move |samples: &[f32]| {
            if !running.load(Ordering::SeqCst) {
                return;
            }

            let sample_count = samples.len();
            if sample_count == 0 {
                return;
            }

            // Convert f32 samples to 16kHz i16 PCM bytes
            let mut pcm = Vec::with_capacity(sample_count * 2);
            for s in samples {
                let clamped = s.clamp(-1.0, 1.0);
                let sample = (clamped * i16::MAX as f32) as i16;
                pcm.extend_from_slice(&sample.to_le_bytes());
            }

            let ws_clone = ws.clone();
            rt_handle.spawn(async move {
                if let Err(e) = ws_clone.send_binary(pcm).await {
                    warn!("[voice-session] failed to send audio: {}", e);
                }
            });
        })?;

        Ok(())
    }

    pub async fn stop(&self) {
        self.running.store(false, Ordering::SeqCst);
        self.audio_queue.lock().unwrap().clear();
        self.mic.write().await.stop();

        let tid = self.thread_id.read().await.clone();
        if let Some(ws) = self.ws_client.read().await.as_ref() {
            let _ = ws.send_voice_stop(&tid).await;
        }
        self.emit_event("voice:state", serde_json::json!({"state": "idle", "thread_id": tid}));
        self.emit_log("voice session stopped");
    }

    pub async fn barge_in(&self) {
        self.audio_queue.lock().unwrap().clear();
        let tid = self.thread_id.read().await.clone();
        if let Some(ws) = self.ws_client.read().await.as_ref() {
            let _ = ws.send_barge_in(&tid).await;
        }
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        self.last_activity.store(now, Ordering::SeqCst);
    }

    pub async fn get_state(&self) -> VoiceState {
        VoiceState::Idle
    }

    pub async fn switch_mode(&self, mode: String) -> Result<(), String> {
        *self.mode.write().await = mode.clone();
        let tid = self.thread_id.read().await.clone();
        if !tid.is_empty() {
            if let Some(ws) = self.ws_client.read().await.as_ref() {
                let _ = ws.send_voice_start(&tid, &mode).await;
            }
        }
        Ok(())
    }

    pub fn set_tts_engine(&self, _engine: crate::voice::tts_engine::TtsEngineKind) {}

    pub fn set_tts_voice(&self, voice: String) {
        if let Ok(mut lock) = self.tts_voice.try_write() {
            *lock = voice;
        }
    }

    pub fn set_tts_speed(&self, speed: f32) {
        if let Ok(mut lock) = self.tts_speed.try_write() {
            *lock = speed;
        }
    }

    pub fn get_tts_engine(&self) -> crate::voice::tts_engine::TtsEngineKind {
        crate::voice::tts_engine::TtsEngineKind::EdgeTts
    }

    pub fn get_tts_voice(&self) -> String {
        self.tts_voice.try_read().map(|v| v.clone()).unwrap_or_default()
    }

    pub fn get_tts_speed(&self) -> f32 {
        self.tts_speed.try_read().map(|g| *g).unwrap_or(1.0)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoiceState {
    Idle,
    Listening,
    Processing,
    Speaking,
    Interrupted,
}

impl VoiceState {
    pub fn as_str(&self) -> &'static str {
        match self {
            VoiceState::Idle => "idle",
            VoiceState::Listening => "listening",
            VoiceState::Processing => "processing",
            VoiceState::Speaking => "speaking",
            VoiceState::Interrupted => "interrupted",
        }
    }
}
