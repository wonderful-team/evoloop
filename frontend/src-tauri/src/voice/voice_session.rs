#![allow(unexpected_cfgs)]

use std::collections::HashMap;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::RwLock;
use log::{info, warn};
use std::path::PathBuf;

use std::io::Write;
use std::process::{Command, Stdio, Child, ChildStdin};

#[cfg(target_os = "macos")]
use ringbuf::{HeapRb, HeapProd};
#[cfg(target_os = "macos")]
use ringbuf::traits::{Split, producer::Producer};

use crate::voice::ws_client::{VoiceWsClient, VoiceEnvelope};
use crate::voice::aec_engine::AecMicCapture;
#[cfg(target_os = "macos")]
use crate::voice::aec_engine::TtsAudioSource;
use crate::voice::event::VoiceEventBus;
use tauri::{AppHandle, Manager};

#[cfg(target_os = "macos")]
#[allow(unexpected_cfgs)]
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
    event_bus: Arc<Mutex<Option<Arc<dyn VoiceEventBus>>>>,
    app_handle: Arc<std::sync::Mutex<Option<AppHandle>>>,
    shared_state: Arc<RwLock<HashMap<String, String>>>,
    tts_voice: Arc<RwLock<String>>,
    tts_speed: Arc<RwLock<f32>>,
    tts_active: Arc<AtomicBool>,
    last_activity: Arc<AtomicU64>,
    state: Arc<Mutex<VoiceState>>,
    #[cfg(target_os = "macos")]
    tts_audio_producer: Arc<Mutex<Option<HeapProd<f32>>>>,
    #[cfg(target_os = "macos")]
    tts_clear_flag: Arc<Mutex<Option<Arc<AtomicBool>>>>,
    ffplay_stdin: Arc<Mutex<Option<ChildStdin>>>,
    ffplay_child: Arc<Mutex<Option<Child>>>,
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
            event_bus: Arc::new(Mutex::new(None)),
            app_handle: Arc::new(std::sync::Mutex::new(None)),
            shared_state: Arc::new(RwLock::new(HashMap::new())),
            tts_voice: Arc::new(RwLock::new(String::new())),
            tts_speed: Arc::new(RwLock::new(1.0)),
            tts_active: Arc::new(AtomicBool::new(false)),
            last_activity: Arc::new(AtomicU64::new(0)),
            state: Arc::new(Mutex::new(VoiceState::Idle)),
            #[cfg(target_os = "macos")]
            tts_audio_producer: Arc::new(Mutex::new(None)),
            #[cfg(target_os = "macos")]
            tts_clear_flag: Arc::new(Mutex::new(None)),
            ffplay_stdin: Arc::new(Mutex::new(None)),
            ffplay_child: Arc::new(Mutex::new(None)),
        }
    }

    pub fn set_event_bus(&self, bus: Arc<dyn VoiceEventBus>) {
        if let Ok(mut lock) = self.event_bus.lock() {
            *lock = Some(bus);
        }
    }

    pub fn set_app_handle(&self, handle: AppHandle) {
        if let Ok(mut lock) = self.app_handle.lock() {
            *lock = Some(handle);
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

    pub fn get_thread_id(&self) -> Arc<RwLock<String>> {
        self.thread_id.clone()
    }

    pub fn get_lang(&self) -> Arc<RwLock<String>> {
        self.lang.clone()
    }

    fn set_state(&self, state: VoiceState) {
        if let Ok(mut lock) = self.state.lock() {
            *lock = state;
        }
    }

    /// Shared TTS cleanup: on macOS drain the VoiceProcessingIO output queue,
    /// on other platforms kill ffplay.
    fn _stop_tts_playback(
        #[cfg(target_os = "macos")]
        tts_clear_flag: &Mutex<Option<Arc<AtomicBool>>>,
        ffplay_stdin: &Mutex<Option<ChildStdin>>,
        ffplay_child: &Mutex<Option<Child>>,
    ) {
        #[cfg(target_os = "macos")]
        {
            if let Ok(flag_opt) = tts_clear_flag.lock() {
                if let Some(flag) = flag_opt.as_ref() {
                    flag.store(true, Ordering::SeqCst);
                }
            }
        }
        let _ = std::process::Command::new("pkill")
            .arg("-x").arg("ffplay")
            .output();
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
    }

    fn _play_via_ffplay(
        bytes: Vec<u8>,
        ffplay_stdin: &Mutex<Option<ChildStdin>>,
        ffplay_child: &Mutex<Option<Child>>,
        session_tts_active: &AtomicBool,
    ) {
        let mut stdin_guard = ffplay_stdin.lock().unwrap();
        if stdin_guard.is_none() {
            if !session_tts_active.load(Ordering::SeqCst) {
                return;
            }
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
                    if let Ok(mut child_guard) = ffplay_child.lock() {
                        if let Some(ref mut old) = *child_guard {
                            let _ = old.wait();
                        }
                        *child_guard = Some(c);
                    }
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
                if let Ok(mut child_guard) = ffplay_child.lock() {
                    if let Some(ref mut c) = *child_guard {
                        let _ = c.kill();
                        let _ = c.wait();
                    }
                    *child_guard = None;
                }
                *stdin_guard = None;
                return;
            }
        }
        let dump_path = std::env::temp_dir().join("tts_debug_raw.pcm");
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&dump_path) {
            let _ = f.write_all(&bytes);
        }
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
        let session_shared_state = self.shared_state.clone();
        let session_tts_active = self.tts_active.clone();
        let session_state = self.state.clone();
        let app_handle = self.app_handle.clone();
        #[cfg(target_os = "macos")]
        let session_tts_producer = self.tts_audio_producer.clone();
        #[cfg(target_os = "macos")]
        let session_tts_clear_flag = self.tts_clear_flag.clone();
        let ffplay_stdin = self.ffplay_stdin.clone();
        let ffplay_child = self.ffplay_child.clone();
        let session_mic = self.mic.clone();

        let handler = Arc::new(move |envelope: VoiceEnvelope| {
            let msg_type = envelope.msg_type.clone();
            let body = envelope.body.clone().unwrap_or(serde_json::Value::Null);
            #[cfg(target_os = "macos")]
            let session_tts_producer = session_tts_producer.clone();
            #[cfg(target_os = "macos")]
            let session_tts_clear_flag = session_tts_clear_flag.clone();
            let ffplay_stdin = ffplay_stdin.clone();
            let ffplay_child = ffplay_child.clone();
            let session_mic = session_mic.clone();
            let session_shared_state = session_shared_state.clone();
            let session_tts_active = session_tts_active.clone();
            let session_state = session_state.clone();
            let event_bus = event_bus.clone();
            let app_handle = app_handle.clone();

            if msg_type == "voice.audio_frame" {
                #[cfg(target_os = "macos")]
                {
                    let session_mic = session_mic.clone();
                    let session_tts_producer = session_tts_producer.clone();
                    let ffplay_stdin = ffplay_stdin.clone();
                    let ffplay_child = ffplay_child.clone();
                    let session_tts_active = session_tts_active.clone();

                    tokio::task::spawn_blocking(move || {
                        if !session_tts_active.load(Ordering::SeqCst) {
                            return;
                        }
                        if let Some(bytes) = envelope.raw_bytes {
                            let is_aec_active = if let Ok(guard) = session_mic.try_read() {
                                guard.is_aec_active()
                            } else {
                                false
                            };

                            if is_aec_active {
                                // Backend sends f32le PCM at 24kHz; VoiceProcessingIO
                                // output runs at 16kHz, so resample before pushing.
                                let samples_24k: Vec<f32> = bytes
                                    .chunks_exact(4)
                                    .map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]))
                                    .collect();
                                let samples_16k = crate::voice::audio_utils::resample_rubato(&samples_24k, 24000, 16000);

                                if let Ok(mut prod_opt) = session_tts_producer.lock() {
                                    if let Some(producer) = prod_opt.as_mut() {
                                        // Push as many resampled samples as fit; drop the
                                        // rest to keep latency low. The consumer runs at the
                                        // hardware render rate, so overflow only occurs under
                                        // heavy back-pressure.
                                        producer.push_slice(&samples_16k);
                                    }
                                }
                            } else {
                                // Fallback to ffplay playback
                                Self::_play_via_ffplay(bytes, &ffplay_stdin, &ffplay_child, &session_tts_active);
                            }
                        }
                    });
                }
                #[cfg(not(target_os = "macos"))]
                {
                    let ffplay_stdin = ffplay_stdin.clone();
                    let ffplay_child = ffplay_child.clone();
                    let session_tts_active = session_tts_active.clone();

                    tokio::task::spawn_blocking(move || {
                        if !session_tts_active.load(Ordering::SeqCst) {
                            return;
                        }
                        if let Some(bytes) = envelope.raw_bytes {
                            Self::_play_via_ffplay(bytes, &ffplay_stdin, &ffplay_child, &session_tts_active);
                        }
                    });
                }
                return;
            }

            tokio::spawn(async move {
                let mt = msg_type.as_str();
                match mt {
                    "voice.barge_in" | "voice.cancel" => {
                        #[cfg(target_os = "macos")]
                        {
                            info!("[tts-play] barge_in/cancel — clearing TTS queue");
                            Self::_stop_tts_playback(session_tts_clear_flag.as_ref(), ffplay_stdin.as_ref(), ffplay_child.as_ref());
                        }
                        #[cfg(not(target_os = "macos"))]
                        {
                            info!("[tts-play] barge_in/cancel — killing ffplay");
                            Self::_stop_tts_playback(ffplay_stdin.as_ref(), ffplay_child.as_ref());
                        }
                        if let Ok(mut lock) = session_state.lock() {
                            *lock = VoiceState::Interrupted;
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
                        let is_listening = body.get("state").and_then(|v| v.as_str()) == Some("listening");
                        if let Some(state_str) = body.get("state").and_then(|v| v.as_str()) {
                            if let Ok(mut lock) = session_state.lock() {
                                if let Some(parsed) = VoiceState::parse(state_str) {
                                    *lock = parsed;
                                }
                            }
                        }
                        let event_name = msg_type.replace(".", ":");
                        event_bus.emit(&event_name, body);
                        if is_listening {
                            #[cfg(target_os = "macos")]
                            if let Ok(flag_opt) = session_tts_clear_flag.lock() {
                                if let Some(flag) = flag_opt.as_ref() {
                                    flag.store(true, Ordering::SeqCst);
                                }
                            }
                            if let Ok(mut stdin_guard) = ffplay_stdin.lock() {
                                if stdin_guard.is_some() {
                                    drop(stdin_guard.take());
                                }
                            }
                        }
                    }
                    "voice.navigate" => {
                        log::info!("[voice-session] received voice.navigate: {:?}", body);
                        if let Some(route) = body.get("route").and_then(|v| v.as_str()) {
                            if let Ok(guard) = app_handle.lock() {
                                if let Some(app) = guard.as_ref() {
                                    if route == "__HIDE_WINDOW__" {
                                        log::info!("[voice-session] hiding main window");
                                        if let Some(window) = app.get_webview_window("main") {
                                            let _ = window.hide();
                                        }
                                    } else {
                                        log::info!("[voice-session] showing/focusing main window for route {}", route);
                                        #[cfg(target_os = "macos")]
                                        app.set_activation_policy(tauri::ActivationPolicy::Regular).ok();
                                        if let Some(window) = app.get_webview_window("main") {
                                            let _ = window.show();
                                            let _ = window.set_focus();
                                        }
                                    }
                                } else {
                                    log::warn!("[voice-session] app_handle not set, cannot control main window");
                                }
                            }
                        }
                        let event_name = msg_type.replace(".", ":");
                        event_bus.emit(&event_name, body);
                    }
                    _ => {
                        let event_name = msg_type.replace(".", ":");
                        event_bus.emit(&event_name, body);
                    }
                }
            });
        });

        let ws = Arc::new(VoiceWsClient::new(ws_url.to_string(), handler));
        ws.connect().await?;
        if let Some(old) = self.ws_client.write().await.take() {
            old.disconnect().await;
        }
        *self.ws_client.write().await = Some(ws);
        Ok(())
    }

    async fn _start_mic_capture(&self, ws: Arc<VoiceWsClient>) -> Result<(), String> {
        let running = self.running.clone();
        let rt_handle = tokio::runtime::Handle::current();

        let send_audio = move |samples: &[f32]| {
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
            let running_clone = running.clone();
            rt_handle.spawn(async move {
                if let Err(e) = ws_clone.send_binary(pcm).await {
                    warn!("[voice-session] failed to send audio: {} — stopping session", e);
                    running_clone.store(false, Ordering::SeqCst);
                }
            });
        };

        let mut mic = self.mic.write().await;

        #[cfg(target_os = "macos")]
        {
            // 2 seconds of 16kHz mono buffer for TTS jitter + AEC reference.
            let rb = HeapRb::<f32>::new(32000);
            let (producer, consumer) = rb.split();
            let clear_flag = Arc::new(AtomicBool::new(false));
            *self.tts_audio_producer.lock().unwrap() = Some(producer);
            *self.tts_clear_flag.lock().unwrap() = Some(clear_flag.clone());

            mic.start(TtsAudioSource { consumer, clear_flag }, send_audio)
        }

        #[cfg(not(target_os = "macos"))]
        {
            mic.start(send_audio)
        }
    }

    /// Restart microphone capture (e.g. after a Bluetooth reconnect) without
    /// tearing down the voice session or WebSocket.
    pub async fn restart_mic(&self) -> Result<(), String> {
        if !self.running.load(Ordering::SeqCst) {
            return Ok(());
        }
        let ws_client = {
            let read_lock = self.ws_client.read().await;
            match read_lock.as_ref() {
                Some(ws) if ws.is_connected().await => ws.clone(),
                _ => return Err("WebSocket not connected, cannot restart mic".to_string()),
            }
        };

        {
            let mut mic = self.mic.write().await;
            mic.stop();
        }
        info!("[voice-session] restarting microphone after device change");
        self._start_mic_capture(ws_client).await
    }

    /// Monitor the microphone stream and try to recover if it dies unexpectedly.
    /// Called once per active session.
    pub async fn mic_watchdog(&self) {
        const CHECK_INTERVAL: Duration = Duration::from_millis(1000);
        const MAX_RETRIES: usize = 3;
        let mut retries = 0;

        while self.running.load(Ordering::SeqCst) {
            tokio::time::sleep(CHECK_INTERVAL).await;
            if !self.running.load(Ordering::SeqCst) {
                break;
            }

            if self.mic.read().await.is_live() {
                retries = 0;
                continue;
            }

            warn!("[voice-session] microphone stream not live");
            self.emit_event(
                "voice:error",
                serde_json::json!({
                    "code": "mic_stream_error",
                    "message": "麦克风流中断，正在尝试恢复",
                }),
            );

            if retries >= MAX_RETRIES {
                self.emit_event(
                    "voice:error",
                    serde_json::json!({
                        "code": "mic_recovery_failed",
                        "message": "麦克风恢复失败，请检查设备",
                    }),
                );
                self.stop().await;
                break;
            }

            retries += 1;
            if let Err(e) = self.restart_mic().await {
                warn!("[voice-session] mic restart attempt {} failed: {}", retries, e);
            } else {
                info!("[voice-session] microphone restarted after stream error");
                retries = 0;
            }
        }
    }

    /// Re-send voice.start after a WebSocket reconnect so a restarted backend
    /// resumes the same session without the user having to re-trigger.
    async fn reconnect_handshake(&self) -> Result<(), String> {
        let ws = {
            let read_lock = self.ws_client.read().await;
            match read_lock.as_ref() {
                Some(ws) if ws.is_connected().await => ws.clone(),
                _ => return Err("WebSocket not connected".to_string()),
            }
        };

        let tid = self.thread_id.read().await.clone();
        let mode = self.mode.read().await.clone();
        if tid.is_empty() {
            return Err("no active thread_id".to_string());
        }

        ws.send_voice_start(&tid, &mode)
            .await
            .map_err(|e| format!("failed to re-send voice.start: {}", e))?;

        self.set_state(VoiceState::Listening);
        self.emit_log(&format!("session resumed after reconnect, mode={}", mode));
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        self.last_activity.store(now, Ordering::SeqCst);
        Ok(())
    }

    /// Monitor WebSocket health: re-handshake after reconnect and stop the
    /// session if the backend stays unreachable.
    async fn reconnect_monitor(&self) {
        const CHECK_INTERVAL: Duration = Duration::from_secs(5);
        const DISCONNECT_TIMEOUT: u32 = 60;
        let mut was_connected = true;
        let mut disconnect_seconds: u32 = 0;

        while self.running.load(Ordering::SeqCst) {
            tokio::time::sleep(CHECK_INTERVAL).await;
            if !self.running.load(Ordering::SeqCst) {
                break;
            }

            let connected = match self.ws_client.read().await.as_ref() {
                Some(ws) => ws.is_connected().await,
                None => false,
            };

            if connected {
                if !was_connected {
                    info!("[voice-session] WebSocket reconnected, re-handshaking");
                    if let Err(e) = self.reconnect_handshake().await {
                        warn!("[voice-session] re-handshake failed: {}", e);
                    }
                }
                disconnect_seconds = 0;
            } else {
                disconnect_seconds += CHECK_INTERVAL.as_secs() as u32;
                if disconnect_seconds >= DISCONNECT_TIMEOUT {
                    warn!(
                        "[voice-session] WebSocket disconnected for {}s, stopping session",
                        disconnect_seconds
                    );
                    self.stop().await;
                    break;
                }
            }
            was_connected = connected;

            // 10min inactivity timeout
            let last = self.last_activity.load(Ordering::SeqCst);
            if last != 0 {
                let elapsed = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_secs()
                    - last;
                if elapsed > 600 {
                    info!("[voice-session] 10min inactivity timeout");
                    self.stop().await;
                    break;
                }
            }
        }
    }

    /// Spawn background monitors for an active session.
    pub async fn spawn_monitors(self: Arc<Self>) {
        let mic_session = self.clone();
        tokio::spawn(async move { mic_session.mic_watchdog().await });
        let reconnect_session = self.clone();
        tokio::spawn(async move { reconnect_session.reconnect_monitor().await });
    }

    pub async fn start(&self, thread_id: String, lang: String, mode: String) -> Result<(), String> {
        let ws_client = {
            let read_lock = self.ws_client.read().await;
            let should_reconnect = match read_lock.as_ref() {
                Some(ws) => !ws.is_connected().await,
                None => true,
            };
            drop(read_lock);
            if should_reconnect {
                let port = crate::sidecar::BACKEND_PORT;
                let ws_url = format!("ws://127.0.0.1:{}/api/v1/voice/ws", port);
                info!("[voice-session] WS not connected, attempting auto-connection to {}", ws_url);
                self.connect_backend(&ws_url).await?;
                self.ws_client.read().await.as_ref().cloned().ok_or("WS connection failed")?
            } else {
                self.ws_client.read().await.as_ref().cloned().ok_or("WS not connected")?
            }
        };

        *self.thread_id.write().await = thread_id.clone();
        *self.lang.write().await = lang.clone();
        *self.mode.write().await = mode.clone();
        self.tts_active.store(mode == "dialogue", Ordering::SeqCst);
        self.running.store(true, Ordering::SeqCst);

        // Start microphone capture BEFORE notifying the backend.
        // CoreAudio initialization can take tens of milliseconds; if we send
        // voice.start first, that audio is lost. Starting the mic first means
        // a few frames may arrive before the backend is ready, but the Python
        // handler simply drops them with a warning.
        if let Err(e) = self._start_mic_capture(ws_client.clone()).await {
            self.running.store(false, Ordering::SeqCst);
            self.tts_active.store(false, Ordering::SeqCst);
            self.set_state(VoiceState::Idle);
            #[cfg(target_os = "macos")]
            {
                *self.tts_audio_producer.lock().unwrap() = None;
                *self.tts_clear_flag.lock().unwrap() = None;
            }
            return Err(e);
        }

        // Notify Python backend to start session
        if let Err(e) = ws_client.send_voice_start(&thread_id, &mode).await {
            warn!("[voice-session] failed to notify backend (connection dead), resetting: {}", e);
            drop(ws_client);
            *self.ws_client.write().await = None;
            self.running.store(false, Ordering::SeqCst);
            self.tts_active.store(false, Ordering::SeqCst);
            self.set_state(VoiceState::Idle);
            self.mic.write().await.stop();
            return Err(format!("backend not reachable: {}", e));
        }
        self.set_state(VoiceState::Listening);
        self.emit_log(&format!("voice session started, mode={}", mode));

        Ok(())
    }

    pub async fn stop(&self) {
        self.running.store(false, Ordering::SeqCst);
        self.tts_active.store(false, Ordering::SeqCst);
        self.set_state(VoiceState::Idle);
        self.mic.write().await.stop();

        #[cfg(target_os = "macos")]
        Self::_stop_tts_playback(self.tts_clear_flag.as_ref(), &self.ffplay_stdin, &self.ffplay_child);
        #[cfg(not(target_os = "macos"))]
        Self::_stop_tts_playback(&self.ffplay_stdin, &self.ffplay_child);

        let tid = self.thread_id.read().await.clone();
        if let Some(ws) = self.ws_client.read().await.as_ref() {
            let _ = ws.send_voice_stop(&tid).await;
        }
        self.emit_event("voice:state", serde_json::json!({"state": "idle", "thread_id": tid}));
        self.emit_log("voice session stopped");
    }

    pub async fn barge_in(&self) {
        #[cfg(target_os = "macos")]
        Self::_stop_tts_playback(self.tts_clear_flag.as_ref(), &self.ffplay_stdin, &self.ffplay_child);
        #[cfg(not(target_os = "macos"))]
        Self::_stop_tts_playback(&self.ffplay_stdin, &self.ffplay_child);

        self.set_state(VoiceState::Interrupted);

        let tid = self.thread_id.read().await.clone();
        if let Some(ws) = self.ws_client.read().await.as_ref() {
            let _ = ws.send_barge_in(&tid).await;
        }
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        self.last_activity.store(now, Ordering::SeqCst);
    }

    pub async fn get_state(&self) -> VoiceState {
        self.state.lock().map(|v| *v).unwrap_or(VoiceState::Idle)
    }

    pub async fn switch_mode(&self, mode: String) -> Result<(), String> {
        let old_mode = self.mode.read().await.clone();
        *self.mode.write().await = mode.clone();
        let tid = self.thread_id.read().await.clone();
        if tid.is_empty() {
            return Ok(());
        }

        // Stop TTS playback when leaving dialogue mode
        if old_mode == "dialogue" && mode != "dialogue" {
            self.tts_active.store(false, Ordering::SeqCst);
            #[cfg(target_os = "macos")]
            Self::_stop_tts_playback(self.tts_clear_flag.as_ref(), &self.ffplay_stdin, &self.ffplay_child);
            #[cfg(not(target_os = "macos"))]
            Self::_stop_tts_playback(&self.ffplay_stdin, &self.ffplay_child);
        }
        // Enable TTS when entering dialogue (both fresh start and dictation→dialogue)
        if mode == "dialogue" {
            self.tts_active.store(true, Ordering::SeqCst);
        }

        let ws = match self.ws_client.read().await.as_ref().cloned() {
            Some(ws) if ws.is_connected().await => ws,
            _ => {
                return Err("WebSocket not connected, need restart".to_string());
            }
        };
        ws.send_voice_start(&tid, &mode).await
            .map_err(|e| format!("switch_mode failed: {}", e))?;

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

    pub fn is_alive(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}

#[allow(dead_code)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoiceState {
    Idle,
    Listening,
    Processing,
    Speaking,
    Interrupted,
}

impl VoiceState {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "idle" => Some(VoiceState::Idle),
            "listening" => Some(VoiceState::Listening),
            "processing" => Some(VoiceState::Processing),
            "speaking" => Some(VoiceState::Speaking),
            "interrupted" => Some(VoiceState::Interrupted),
            _ => None,
        }
    }

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn voice_state_parse_round_trip() {
        let states = [
            VoiceState::Idle,
            VoiceState::Listening,
            VoiceState::Processing,
            VoiceState::Speaking,
            VoiceState::Interrupted,
        ];
        for state in states {
            assert_eq!(VoiceState::parse(state.as_str()), Some(state));
        }
        assert_eq!(VoiceState::parse("unknown"), None);
    }

    #[tokio::test]
    async fn voice_session_state_transitions() {
        let session = VoiceSession::new(vec![]);
        assert_eq!(session.get_state().await, VoiceState::Idle);

        session.set_state(VoiceState::Listening);
        assert_eq!(session.get_state().await, VoiceState::Listening);

        // Simulate backend pushing a state update
        session.set_state(VoiceState::Processing);
        assert_eq!(session.get_state().await, VoiceState::Processing);

        session.set_state(VoiceState::Speaking);
        assert_eq!(session.get_state().await, VoiceState::Speaking);

        session.set_state(VoiceState::Interrupted);
        assert_eq!(session.get_state().await, VoiceState::Interrupted);

        session.set_state(VoiceState::Idle);
        assert_eq!(session.get_state().await, VoiceState::Idle);
    }
}
