use tauri::Emitter;
use tauri::Manager;
use tauri::menu::MenuItem;
use tauri::tray::TrayIcon;
use tauri::WindowEvent;
#[cfg(desktop)]
use std::sync::atomic::{AtomicBool, AtomicUsize, AtomicI32};
#[cfg(desktop)]
use std::sync::{Arc, Mutex};
#[cfg(desktop)]
use tauri_plugin_shell::process::CommandChild;
// ShellExt removed - no longer needed for sidecar management

use crate::sidecar::SidecarClient;
use crate::voice::event::VoiceEventBus;
use crate::voice::wake_word::WakeWordDetector;

// Marker overlay window management
#[cfg(desktop)]
use tauri::WebviewWindowBuilder;
#[cfg(desktop)]
static MARKER_OVERLAY_OPEN: AtomicBool = AtomicBool::new(false);
#[cfg(desktop)]
static ANDROID_MARKER_OVERLAY_OPEN: AtomicBool = AtomicBool::new(false);

#[cfg(desktop)]
mod global_observer;
#[cfg(desktop)]
use global_observer::GlobalObserver;

mod commands;
mod screen_recorder;
mod sidecar;
mod tray;
mod version;
mod voice;
#[cfg(desktop)]
mod global_shortcut;

#[cfg(desktop)]
use global_shortcut::GLOBAL_SHORTCUT_MANAGER;

#[cfg(desktop)]
use std::sync::LazyLock;
#[cfg(desktop)]
static WAK_WORD_DETECTOR: LazyLock<Mutex<WakeWordDetector>> = LazyLock::new(|| {
    // LazyLock requires the closure to be Send. WakeWordDetector::new() is Send.
    Mutex::new(WakeWordDetector::new())
});

// ===== App State =====

#[cfg(desktop)]
pub struct AppServiceState {
    pub children: Arc<Mutex<Vec<CommandChild>>>,
    pub tray: Arc<Mutex<Option<TrayIcon>>>,
    pub record_item: Arc<Mutex<Option<MenuItem<tauri::Wry>>>>,
    pub show_item: Arc<Mutex<Option<MenuItem<tauri::Wry>>>>,
    pub quit_item: Arc<Mutex<Option<MenuItem<tauri::Wry>>>>,
    pub global_observer: Arc<GlobalObserver>,
    // Screen recording (Two-Track Architecture)
    pub recording_process: Arc<Mutex<Option<std::process::Child>>>,
    pub recording_path: Arc<Mutex<Option<String>>>,
    pub is_blinking: Arc<AtomicBool>,
    // Timer: stores the Instant when recording started (None when not recording)
    pub recording_start_time: Arc<Mutex<Option<std::time::Instant>>>,
    pub is_preparing: Arc<AtomicBool>,
    pub countdown: Arc<AtomicI32>,
    // Voice session active (for tray icon indicator)
    pub voice_active: Arc<AtomicBool>,
    // Event count from frontend (DOM + Global events)
    pub event_count: Arc<AtomicUsize>,
    // Sidecar Client (Backend HTTP process)
    pub sidecar_client: Arc<Mutex<Option<SidecarClient>>>,
    // Full-duplex voice manager
    pub voice_manager: VoiceManagerHandle,
}

/// Find the voice models directory by searching common paths.
#[cfg(desktop)]
fn find_models_dir() -> Option<std::path::PathBuf> {
    let home = dirs::home_dir()?;
    let candidates = [
        home.join(".evoloop/models"),
        home.join(".config/models/sherpa-onnx/model"),
    ];
    for dir in &candidates {
        if dir.join("encoder.int8.onnx").exists() && dir.join("silero_vad.onnx").exists() {
            return Some(dir.clone());
        }
        // also check parent for VAD
        if dir.join("encoder.int8.onnx").exists() && dir.parent().map(|p| p.join("silero_vad.onnx")).as_ref().map(|p| p.exists()).unwrap_or(false) {
            return Some(dir.clone());
        }
    }
    None
}

// ===== Global Recording Commands =====

#[tauri::command]
#[cfg(desktop)]
async fn start_global_recording(
    state: tauri::State<'_, AppServiceState>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    println!("Start global recording requested");
    state.global_observer.start(app);
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn start_global_recording() -> Result<(), String> {
    Err("Global recording is not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(desktop)]
async fn stop_global_recording(
    state: tauri::State<'_, AppServiceState>,
) -> Result<(), String> {
    println!("Stop global recording requested");
    state.global_observer.stop();
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn stop_global_recording() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
fn is_global_recording(state: tauri::State<'_, AppServiceState>) -> bool {
    state.global_observer.is_recording()
}

#[tauri::command]
#[cfg(desktop)]
async fn show_main_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(target_os = "macos")]
        let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
        let _ = window.show();
        let _ = window.set_focus();
    }
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn show_main_window() -> Result<(), String> {
    Ok(())
}

use crate::voice::tts_engine::TtsEngineKind;
use crate::voice::{VoiceSession, VoiceState};
use tokio::sync::{mpsc, oneshot};

#[derive(Clone)]
pub struct VoiceManagerHandle {
    tx: mpsc::Sender<VoiceCommand>,
}

impl VoiceManagerHandle {
    pub async fn send(&self, cmd: VoiceCommand) -> Result<(), String> {
        self.tx.send(cmd).await.map_err(|e| e.to_string())
    }

    pub async fn set_tts_engine(&self, kind: TtsEngineKind) -> Result<(), String> {
        let (tx, rx) = oneshot::channel();
        self.send(VoiceCommand::SetTtsEngine { kind, respond: tx }).await?;
        rx.await.map_err(|e| e.to_string())?
    }

    pub async fn get_tts_engine(&self) -> String {
        let (tx, rx) = oneshot::channel();
        let _ = self.send(VoiceCommand::GetTtsEngine { respond: tx }).await;
        rx.await.unwrap_or("system".to_string())
    }

    pub async fn set_tts_voice(&self, voice: String) -> Result<(), String> {
        let (tx, rx) = oneshot::channel();
        self.send(VoiceCommand::SetTtsVoice { voice, respond: tx }).await?;
        rx.await.map_err(|e| e.to_string())?
    }

    pub async fn set_tts_speed(&self, speed: f32) -> Result<(), String> {
        let (tx, rx) = oneshot::channel();
        self.send(VoiceCommand::SetTtsSpeed { speed, respond: tx }).await?;
        rx.await.map_err(|e| e.to_string())?
    }
}

enum VoiceCommand {
    InitEngines {
        asr_model_dir: String,
        vad_model_path: String,
        vad_silence_ms: f32,
        respond: oneshot::Sender<Result<(), String>>,
    },
    ConnectBackend {
        ws_url: String,
        respond: oneshot::Sender<Result<(), String>>,
    },
    Start {
        app_handle: tauri::AppHandle,
        thread_id: String,
        lang: String,
        mode: String,
        respond: oneshot::Sender<Result<(), String>>,
    },
    Stop,
    BargeIn,
    GetState {
        respond: oneshot::Sender<VoiceState>,
    },
    SetTtsEngine {
        kind: crate::voice::tts_engine::TtsEngineKind,
        respond: oneshot::Sender<Result<(), String>>,
    },
    GetTtsEngine {
        respond: oneshot::Sender<String>,
    },
    SetTtsVoice {
        voice: String,
        respond: oneshot::Sender<Result<(), String>>,
    },
    SetTtsSpeed {
        speed: f32,
        respond: oneshot::Sender<Result<(), String>>,
    },
}

// ===== Tauri Event Bus =====

struct TauriEventBus {
    handle: tauri::AppHandle,
}

impl VoiceEventBus for TauriEventBus {
    fn emit(&self, event: &str, payload: serde_json::Value) {
        use tauri::Emitter;
        let _ = self.handle.emit(event, payload);
    }
}

// ===== Voice Manager =====

fn spawn_voice_manager(model_search_paths: Vec<std::path::PathBuf>) -> VoiceManagerHandle {
    let (tx, mut rx) = mpsc::channel::<VoiceCommand>(32);

    // VoiceSession owns cpal::Stream which is not Send, so it cannot live in
    // Tauri's managed state or in a tokio task that may move between threads.
    // Run it on a dedicated OS thread with its own tokio runtime instead.
    std::thread::spawn(move || {
        let rt = match tokio::runtime::Runtime::new() {
            Ok(rt) => rt,
            Err(e) => {
                log::error!("[voice-manager] failed to create runtime: {}", e);
                return;
            }
        };
        rt.block_on(async {
            let session = VoiceSession::new(model_search_paths);
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    VoiceCommand::InitEngines { asr_model_dir, vad_model_path, vad_silence_ms, respond } => {
                        let res = session.init_engines(&asr_model_dir, &vad_model_path, vad_silence_ms).await;
                        let _ = respond.send(res);
                    }
                    VoiceCommand::ConnectBackend { ws_url, respond } => {
                        let res = session.connect_backend(&ws_url).await;
                        let _ = respond.send(res);
                    }
                    VoiceCommand::Start { app_handle, thread_id, lang, mode, respond } => {
                        let bus = Arc::new(TauriEventBus { handle: app_handle }) as Arc<dyn VoiceEventBus>;
                        session.set_event_bus(bus);
                        let res = session.start(thread_id, lang, mode).await;
                        let _ = respond.send(res);
                    }
                    VoiceCommand::Stop => {
                        session.stop().await;
                    }
                    VoiceCommand::BargeIn => {
                        session.barge_in().await;
                    }
                    VoiceCommand::GetState { respond } => {
                        let state = session.get_state().await;
                        let _ = respond.send(state);
                    }
                    VoiceCommand::SetTtsEngine { kind, respond } => {
                        session.set_tts_engine(kind);
                        let _ = respond.send(Ok(()));
                    }
                    VoiceCommand::GetTtsEngine { respond } => {
                        let engine = session.get_tts_engine();
                        let _ = respond.send(engine.as_str().to_string());
                    }
                    VoiceCommand::SetTtsVoice { voice, respond } => {
                        session.set_tts_voice(voice);
                        let _ = respond.send(Ok(()));
                    }
                    VoiceCommand::SetTtsSpeed { speed, respond } => {
                        session.set_tts_speed(speed);
                        let _ = respond.send(Ok(()));
                    }
                }
            }
        });
    });

    VoiceManagerHandle { tx }
}

// ===== Voice Session Commands =====

#[tauri::command]
#[cfg(desktop)]
async fn init_voice_engines(
    state: tauri::State<'_, AppServiceState>,
    asr_model_dir: String,
    vad_model_path: String,
    vad_silence_ms: f32,
) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    state.voice_manager.send(VoiceCommand::InitEngines {
        asr_model_dir,
        vad_model_path,
        vad_silence_ms,
        respond: tx,
    }).await?;
    rx.await.map_err(|e| e.to_string())?
}

#[tauri::command]
#[cfg(desktop)]
async fn connect_voice_backend(
    state: tauri::State<'_, AppServiceState>,
    ws_url: String,
) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    state.voice_manager.send(VoiceCommand::ConnectBackend {
        ws_url,
        respond: tx,
    }).await?;
    rx.await.map_err(|e| e.to_string())?
}

#[tauri::command]
#[cfg(desktop)]
async fn start_voice_session(
    state: tauri::State<'_, AppServiceState>,
    app: tauri::AppHandle,
    thread_id: String,
    lang: String,
    mode: String,
) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    state.voice_manager.send(VoiceCommand::Start {
        app_handle: app,
        thread_id,
        lang,
        mode,
        respond: tx,
    }).await?;
    rx.await.map_err(|e| e.to_string())?
}

#[tauri::command]
#[cfg(desktop)]
async fn stop_voice_session(
    state: tauri::State<'_, AppServiceState>,
) -> Result<(), String> {
    state.voice_manager.send(VoiceCommand::Stop).await?;
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn trigger_voice_barge_in(
    state: tauri::State<'_, AppServiceState>,
) -> Result<(), String> {
    state.voice_manager.send(VoiceCommand::BargeIn).await?;
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn get_voice_state(
    state: tauri::State<'_, AppServiceState>,
) -> Result<String, String> {
    let (tx, rx) = oneshot::channel();
    state.voice_manager.send(VoiceCommand::GetState { respond: tx }).await?;
    let state = rx.await.map_err(|e| e.to_string())?;
    Ok(state.as_str().to_string())
}

#[tauri::command]
#[cfg(desktop)]
async fn start_dictation(
    app: tauri::AppHandle,
    raw_text: String,
    target_locale: String,
) -> Result<String, String> {
    use crate::voice::DictationEngine;

    let lm_url = "http://127.0.0.1:1234".to_string();
    let model = "Qwen3-4B-Instruct-2507".to_string();
    let engine = DictationEngine::new(lm_url, model);

    let polished_ref = Arc::new(Mutex::new(String::new()));
    let polished_clone = polished_ref.clone();
    let app_clone = app.clone();

    engine.polish_stream(&raw_text, &target_locale, move |token: &str| {
        let mut buf = polished_clone.lock().unwrap();
        buf.push_str(token);
        let _ = app_clone.emit("voice:dictation_token", serde_json::json!({"token": token}));
    }).await?;

    let polished = polished_ref.lock().unwrap().clone();
    let _ = app.emit("voice:dictation_polished", serde_json::json!({"polished_text": &polished}));
    Ok(polished)
}

#[tauri::command]
#[cfg(mobile)]
async fn init_voice_engines(_: String, _: String, _: f32) -> Result<(), String> {
    Err("Voice engines not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(mobile)]
async fn connect_voice_backend(_: String) -> Result<(), String> {
    Err("Voice backend not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(mobile)]
async fn start_voice_session(_: String, _: String) -> Result<(), String> {
    Err("Voice session not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(mobile)]
async fn stop_voice_session() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn trigger_voice_barge_in() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn get_voice_state() -> Result<String, String> {
    Ok("idle".to_string())
}

#[tauri::command]
#[cfg(mobile)]
async fn start_dictation(_: String, _: String) -> Result<String, String> {
    Err("Dictation not supported on mobile".to_string())
}

// ===== Safe Process Kill Helpers =====

/// Send SIGINT to a process safely (wraps unsafe libc::kill).
pub fn safe_kill(pid: i32) {
    unsafe { libc::kill(pid, libc::SIGINT); }
}

/// Send SIGTERM to a process group safely (wraps unsafe libc::killpg).
pub fn safe_killpg(pgid: i32) {
    unsafe { libc::killpg(pgid, libc::SIGTERM); }
}

// ===== TTS Commands =====

#[tauri::command]
#[cfg(desktop)]
async fn speak_text(
    state: tauri::State<'_, AppServiceState>,
    text: String,
    voice: String,
    rate: i32,
    engine: Option<String>,
    api_key: Option<String>,
) -> Result<(), String> {
    if let Some(ref key) = api_key {
        if !key.is_empty() {
            unsafe {
                std::env::set_var("EVOLOOP_QWEN_TTS_KEY", key);
            }
        }
    }
    let engine_kind = match engine {
        Some(e) => e,
        None => state.voice_manager.get_tts_engine().await,
    };
    match engine_kind.as_str() {
        "edge-tts" => {
            let voice_name = if voice.is_empty() { "zh-CN-XiaoxiaoNeural".to_string() } else { voice };
            let text_clone = text.clone();
            let res = tokio::task::spawn_blocking(move || {
                let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
                rt.block_on(async {
                    crate::voice::tts_engine::speak_edge_tts_for_preview(&text_clone, &voice_name).await
                })
            }).await.map_err(|e| format!("Edge TTS task join error: {}", e))?;
            res?;
            Ok(())
        }
        "qwen-tts" => {
            let voice_name = if voice.is_empty() { "standard_voice".to_string() } else { voice };
            let text_clone = text.clone();
            let res = tokio::task::spawn_blocking(move || {
                let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
                rt.block_on(async {
                    crate::voice::tts_engine::speak_qwen_tts_for_preview(&text_clone, &voice_name).await
                })
            }).await.map_err(|e| format!("Qwen TTS task join error: {}", e))?;
            res?;
            Ok(())
        }
        _ => {
            use std::process::Command;
            let sys_voice = if voice.starts_with("zh") { "Ting-Ting".to_string() }
                else if voice.starts_with("en") { "Samantha".to_string() }
                else if voice.is_empty() { "Ting-Ting".to_string() }
                else { voice.clone() };
            eprintln!("[tts] speak_text: engine=system voice={} sys_voice={} rate={} text=\"{}\"", voice, sys_voice, rate, text);
            // Spawn say in a background thread and wait for completion
            let text_clone = text.clone();
            std::thread::spawn(move || {
                let status = Command::new("say")
                    .arg("-v").arg(&sys_voice)
                    .arg("-r").arg(rate.to_string())
                    .arg(&text_clone)
                    .status();
                match status {
                    Ok(s) => eprintln!("[tts] say exited: {:?}", s.code()),
                    Err(e) => eprintln!("[tts] say failed: {}", e),
                }
            });
            Ok(())
        }
    }
}

#[tauri::command]
#[cfg(desktop)]
async fn set_qwen_api_key(key: String) -> Result<(), String> {
    unsafe {
        std::env::set_var("EVOLOOP_QWEN_TTS_KEY", &key);
    }
    log::info!("[tts] Qwen-TTS API Key synchronized in process");
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn set_qwen_api_key(_key: String) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn stop_speaking() -> Result<(), String> {
    use std::process::Command;
    Command::new("pkill")
        .arg("-x")
        .arg("say")
        .output()
        .map_err(|e| format!("Failed to stop TTS: {}", e))?;
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn list_system_voices() -> Result<Vec<serde_json::Value>, String> {
    use std::process::Command;
    let output = Command::new("say")
        .arg("-v")
        .arg("?")
        .output()
        .map_err(|e| format!("Failed to list voices: {}", e))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut voices = Vec::new();
    for line in stdout.lines() {
        let parts: Vec<&str> = line.splitn(2, "  ").collect();
        if parts.len() >= 1 {
            let name = parts[0].trim();
            if !name.is_empty() {
                voices.push(serde_json::json!({
                    "id": name,
                    "name": name,
                    "gender": "unknown",
                    "description": parts.get(1).unwrap_or(&"").trim(),
                }));
            }
        }
    }
    Ok(voices)
}

#[tauri::command]
#[cfg(mobile)]
async fn speak_text(_text: String, _voice: String, _rate: i32, _engine: Option<String>) -> Result<(), String> {
    Err("TTS not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(mobile)]
async fn stop_speaking() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn list_system_voices() -> Result<Vec<serde_json::Value>, String> {
    Err("TTS not supported on mobile".to_string())
}

// ===== Wake Word Commands =====

#[tauri::command]
#[cfg(desktop)]
async fn start_wake_word_listener(app: tauri::AppHandle, word: String) -> Result<(), String> {
    use crate::voice::asr_engine::AsrEngine;

    let models_dir = find_models_dir().ok_or("Voice models not found. Run deploy/download_models.sh --all")?;
    let asr = Arc::new(AsrEngine::new(models_dir.to_str().ok_or("Invalid path")?)?);

    let mut detector = WAK_WORD_DETECTOR.lock().map_err(|e| format!("Lock error: {}", e))?;
    detector.start(app, word, asr)
}

#[tauri::command]
#[cfg(desktop)]
async fn stop_wake_word_listener() -> Result<(), String> {
    let mut detector = WAK_WORD_DETECTOR.lock().map_err(|e| format!("Lock error: {}", e))?;
    detector.stop();
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn start_wake_word_listener(_app: tauri::AppHandle, _word: String) -> Result<(), String> {
    Err("Wake word not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(mobile)]
async fn stop_wake_word_listener() -> Result<(), String> {
    Ok(())
}

// ===== TTS Engine Selection =====

#[tauri::command]
#[cfg(desktop)]
async fn set_tts_engine(state: tauri::State<'_, AppServiceState>, engine: String) -> Result<(), String> {
    use crate::voice::tts_engine::TtsEngineKind;
    let kind = TtsEngineKind::from_str(&engine);
    state.voice_manager.set_tts_engine(kind).await
}

#[tauri::command]
#[cfg(desktop)]
async fn get_tts_engine(state: tauri::State<'_, AppServiceState>) -> Result<String, String> {
    Ok(state.voice_manager.get_tts_engine().await)
}

#[tauri::command]
#[cfg(mobile)]
async fn set_tts_engine(_engine: String) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn get_tts_engine() -> Result<String, String> {
    Ok("system".to_string())
}

// ===== TTS Voice & Speed Settings =====

#[tauri::command]
#[cfg(desktop)]
async fn set_tts_voice(state: tauri::State<'_, AppServiceState>, voice: String) -> Result<(), String> {
    state.voice_manager.set_tts_voice(voice).await
}

#[tauri::command]
#[cfg(desktop)]
async fn set_tts_speed(state: tauri::State<'_, AppServiceState>, speed: f32) -> Result<(), String> {
    state.voice_manager.set_tts_speed(speed).await
}

#[tauri::command]
#[cfg(mobile)]
async fn set_tts_voice(_voice: String) -> Result<(), String> { Ok(()) }

#[tauri::command]
#[cfg(mobile)]
async fn set_tts_speed(_speed: f32) -> Result<(), String> { Ok(()) }

// ===== Global Voice Shortcut Commands =====

#[tauri::command]
#[cfg(desktop)]
async fn start_voice_shortcut_listener(app: tauri::AppHandle) -> Result<(), String> {
    GLOBAL_SHORTCUT_MANAGER.set_app_handle(app);
    GLOBAL_SHORTCUT_MANAGER.start_listening();
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn stop_voice_shortcut_listener() -> Result<(), String> {
    GLOBAL_SHORTCUT_MANAGER.stop_listening();
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn set_voice_shortcut_key(key: String) -> Result<(), String> {
    GLOBAL_SHORTCUT_MANAGER.set_target_key(key);
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn set_voice_shortcut_duration(duration_ms: u64) -> Result<(), String> {
    GLOBAL_SHORTCUT_MANAGER.set_long_press_threshold(duration_ms);
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn start_voice_shortcut_listener() -> Result<(), String> {
    Err("Voice shortcut is not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(mobile)]
async fn stop_voice_shortcut_listener() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn set_voice_shortcut_key(_key: String) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn set_voice_shortcut_duration(_duration_ms: u64) -> Result<(), String> {
    Ok(())
}

// ===== Marker Overlay Window Commands =====

/// Create a small floating overlay window. Used for both regular and Android markers.
#[cfg(desktop)]
fn create_overlay_window(
    app: &tauri::AppHandle,
    label: &str,
    url_path: &str,
    title: &str,
    flag: &std::sync::atomic::AtomicBool,
) -> Result<String, String> {
    use std::sync::atomic::Ordering;

    if flag.load(Ordering::SeqCst) {
        if let Some(window) = app.get_webview_window(label) {
            let _ = window.show();
            let _ = window.set_focus();
            return Ok(format!("{}-already-exists", label));
        }
    }

    flag.store(true, Ordering::SeqCst);

    let _window = tauri::WebviewWindowBuilder::new(
        app,
        label,
        tauri::WebviewUrl::App(url_path.into())
    )
    .title(title)
    .inner_size(64.0, 64.0)
    .max_inner_size(64.0, 64.0)
    .min_inner_size(64.0, 64.0)
    .always_on_top(true)
    .decorations(false)
    .skip_taskbar(true)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .closable(true)
    .visible(false)
    .transparent(true)
    .shadow(false)
    .position(100.0, 100.0)
    .build()
    .map_err(|e| format!("Failed to create {}: {}", label, e))?;

    Ok(format!("{}-created", label))
}

#[tauri::command]
#[cfg(desktop)]
async fn create_marker_overlay(app: tauri::AppHandle) -> Result<String, String> {
    create_overlay_window(&app, "marker-overlay", "/marker-overlay", "EvoLoop Marker Overlay", &MARKER_OVERLAY_OPEN)
}



#[tauri::command]
#[cfg(desktop)]
async fn close_marker_overlay(app: tauri::AppHandle) -> Result<String, String> {
    use std::sync::atomic::Ordering;

    if let Some(window) = app.get_webview_window("marker-overlay") {
        let _ = window.close();
    }

    MARKER_OVERLAY_OPEN.store(false, Ordering::SeqCst);
    Ok("marker-overlay-closed".to_string())
}

#[tauri::command]
#[cfg(desktop)]
async fn update_marker_overlay_position(
    app: tauri::AppHandle,
    x: f64,
    y: f64
) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("marker-overlay") {
        use tauri::LogicalPosition;
        window.set_position(LogicalPosition::new(x, y))
            .map_err(|e| format!("Failed to update position: {}", e))?;
    }
    Ok(())
}

// ===== Android Marker Overlay Window Commands =====

#[tauri::command]
#[cfg(desktop)]
async fn create_android_marker_overlay(app: tauri::AppHandle) -> Result<String, String> {
    create_overlay_window(&app, "android-marker-overlay", "/android-marker-overlay", "EvoLoop Android Marker Overlay", &ANDROID_MARKER_OVERLAY_OPEN)
}

#[tauri::command]
#[cfg(desktop)]
async fn close_android_marker_overlay(app: tauri::AppHandle) -> Result<String, String> {
    use std::sync::atomic::Ordering;

    if let Some(window) = app.get_webview_window("android-marker-overlay") {
        let _ = window.close();
    }

    ANDROID_MARKER_OVERLAY_OPEN.store(false, Ordering::SeqCst);
    Ok("android-marker-overlay-closed".to_string())
}

#[tauri::command]
#[cfg(desktop)]
async fn update_android_marker_position(
    app: tauri::AppHandle,
    x: f64,
    y: f64
) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("android-marker-overlay") {
        use tauri::LogicalPosition;
        window.set_position(LogicalPosition::new(x, y))
            .map_err(|e| format!("Failed to update position: {}", e))?;
    }
    Ok(())
}

// ===== Application Entry Point =====

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let _ = rustls::crypto::ring::default_provider().install_default();
    #[cfg(desktop)]
    {
        env_logger::init();
        std::panic::set_hook(Box::new(|info| {
        let msg = format!("Panic occurred: {:?}", info);
        println!("{}", msg);
        // Try to write to a file in the current working directory
        let _ = std::fs::write("panic.log", msg);
    }));
    }

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build());

    let builder = builder.setup(|_app| {
        #[cfg(mobile)]
        {
            // Mobile setup if needed
        }

        #[cfg(desktop)]
        {
            let quit_i = MenuItem::with_id(_app, "quit", "退出", true, Some("CmdOrCtrl+Q"))?;
            let show_i = MenuItem::with_id(_app, "show", "显示主界面", true, None::<&str>)?;
            let record_i = MenuItem::with_id(_app, "record", "技能录制", true, None::<&str>)?;
            let voice_dictation_i = MenuItem::with_id(_app, "voice_dictation", "语音听写", true, Some("F12"))?;
            let voice_dialogue_i = MenuItem::with_id(_app, "voice_dialogue", "语音对话", true, Some("F12"))?;

            let service_state = AppServiceState {
                children: Arc::new(Mutex::new(Vec::new())),
                tray: Arc::new(Mutex::new(None)),
                record_item: Arc::new(Mutex::new(Some(record_i.clone()))),
                show_item: Arc::new(Mutex::new(Some(show_i.clone()))),
                quit_item: Arc::new(Mutex::new(Some(quit_i.clone()))),
                global_observer: Arc::new(GlobalObserver::new()),
                // Screen recording (Two-Track Architecture)
                recording_process: Arc::new(Mutex::new(None)),
                recording_path: Arc::new(Mutex::new(None)),
                is_blinking: Arc::new(AtomicBool::new(false)),
                // Timer: stores the Instant when recording started (None when not recording)
                recording_start_time: Arc::new(Mutex::new(None)),
                is_preparing: Arc::new(AtomicBool::new(false)),
                countdown: Arc::new(AtomicI32::new(0)),
                voice_active: Arc::new(AtomicBool::new(false)),
                // Event count from frontend (DOM + Global events)
                event_count: Arc::new(AtomicUsize::new(0)),
            // Backend Sidecar (HTTP Server)
            sidecar_client: Arc::new(Mutex::new(None)),
            // Full-duplex voice manager
            voice_manager: {
                let mut paths = Vec::new();
                if let Ok(dir) = _app.path().resource_dir() {
                    paths.push(dir.join("models"));
                }
                if let Ok(dir) = _app.path().app_data_dir() {
                    paths.push(dir.join("models"));
                }
                spawn_voice_manager(paths)
            },
        };
            _app.manage(service_state);

            // Build system tray
            let tray = tray::setup_tray(_app, &show_i, &record_i, &voice_dictation_i, &voice_dialogue_i, &quit_i)?;

            let state = _app.state::<AppServiceState>();
            *state.tray.lock().unwrap() = Some(tray);

            // Start Backend Sidecar (HTTP Server)
            let mut sidecar_client = SidecarClient::new();
            match sidecar_client.start(_app.handle(), None) {
                Ok(()) => {
                    use crate::sidecar::BACKEND_PORT;
                    log::info!("Backend started successfully on port {}", BACKEND_PORT);
                    // Store the client
                    *state.sidecar_client.lock().unwrap() = Some(sidecar_client);

                    // Backend will emit "backend-ready" event via HTTP polling
                }
                Err(e) => {
                    log::error!("Failed to start Backend: {}", e);
                    let _ = _app.emit("backend-error", e);
                }
            }
        }
        Ok(())
    });

    let app = builder
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                #[cfg(desktop)]
                if window.label() == "main" {
                    let _ = window.hide();
                    #[cfg(target_os = "macos")]
                    window.app_handle().set_activation_policy(tauri::ActivationPolicy::Accessory).ok();
                    api.prevent_close();
                }
            }
        })
        .on_page_load(|_window, _payload| {
            #[cfg(any(target_os = "android", target_os = "ios"))]
            {
                // This is a simplified way to hint, but real permission handling
                // for Webview strictly requires Rust-side implementation in Tauri v2
                // or creating a custom plugin to hook into WebChromeClient on PermissionRequest.
                // However, Tauri v2 usually auto-grants if OS permission is present.
                // Let's ensure the webview is created with media access.
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::screenshot::capture_screenshot,
            start_global_recording,
            stop_global_recording,
            is_global_recording,
            commands::permissions::check_accessibility_permission,
            commands::permissions::open_accessibility_settings,
            tray::sync_tray_recording_state,
            tray::sync_tray_translations,
            tray::sync_tray_event_count,
            tray::sync_tray_countdown,
            tray::set_recording_start_time,
            tray::sync_tray_voice_state,
            screen_recorder::start_screen_recording,
            screen_recorder::stop_screen_recording,
            commands::permissions::check_screen_recording_permission,
            commands::permissions::open_screen_recording_settings,
            create_marker_overlay,
            close_marker_overlay,
            update_marker_overlay_position,
            create_android_marker_overlay,
            close_android_marker_overlay,
            update_android_marker_position,
            show_main_window,
            commands::window::get_window_bounds_by_title,
            commands::window::get_mirror_window_bounds,
            // Backend commands
            commands::sidecar::backend_get_url,
            commands::sidecar::sidecar_is_ready,
            commands::sidecar::sidecar_get_status,
            commands::sidecar::sidecar_restart,
    // TTS commands
    speak_text,
    stop_speaking,
    list_system_voices,
    set_tts_engine,
    get_tts_engine,
    set_tts_voice,
    set_tts_speed,
    set_qwen_api_key,
    // Voice shortcut commands
    start_voice_shortcut_listener,
            stop_voice_shortcut_listener,
            set_voice_shortcut_key,
            set_voice_shortcut_duration,
            // Version commands
            version::get_version_info,
            version::get_version,
            version::is_stage,
            version::compare_versions,
            version::needs_update,
            // Full-duplex voice commands
            init_voice_engines,
            connect_voice_backend,
            start_voice_session,
            stop_voice_session,
            trigger_voice_barge_in,
            get_voice_state,
            start_dictation,
            // Wake word commands
            start_wake_word_listener,
            stop_wake_word_listener,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| match event {
        #[cfg(desktop)]
        tauri::RunEvent::Reopen { .. } => {
            if let Some(window) = app_handle.get_webview_window("main") {
                #[cfg(target_os = "macos")]
                app_handle.set_activation_policy(tauri::ActivationPolicy::Regular).ok();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
        #[cfg(desktop)]
        tauri::RunEvent::Exit => {
            let state = app_handle.state::<AppServiceState>();
            // Stop global observer
            state.global_observer.stop();

            // Stop sidecar client and wait for it to finish
            if let Some(client) = state.sidecar_client.lock().unwrap().take() {
                if let Err(e) = client.stop() {
                    log::error!("Failed to stop backend: {}", e);
                }
                // Give it time to clean up
                std::thread::sleep(std::time::Duration::from_millis(1000));
            }

            let mut children = state.children.lock().unwrap();
            while let Some(child) = children.pop() {
                let _ = child.kill();
            }
            // Stop screen recording if active
            {
                let mut rec_lock = state.recording_process.lock().unwrap();
                if let Some(mut rec_child) = rec_lock.take() {
                    #[cfg(unix)]
                    safe_kill(rec_child.id() as i32);
                    #[cfg(not(unix))]
                    let _ = rec_child.kill();
                    let _ = rec_child.wait();
                }
            }
            
            // Force kill any remaining evoloop-backend processes
            #[cfg(unix)]
            {
                use std::process::Command;
                let _ = Command::new("pkill")
                    .args(["-9", "-f", "evoloop-backend"])
                    .output();
            }
        }
        _ => {}
    });
}
