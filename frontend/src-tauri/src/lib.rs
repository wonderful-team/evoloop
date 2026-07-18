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

// ===== Trivial Command =====

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
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
}

fn spawn_voice_manager() -> VoiceManagerHandle {
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
            let session = VoiceSession::new();
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
                        session.set_app_handle(app_handle);
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
#[cfg(desktop)]
async fn set_voice_shortcut_mode(_mode: String) -> Result<(), String> {
    // Unified mode: tap = dictation, hold = dialogue. Mode selection is deprecated.
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
async fn set_voice_shortcut_interval(_interval_ms: u64) -> Result<(), String> {
    // Unified mode no longer uses double-click interval. Kept for backward compat.
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

#[tauri::command]
#[cfg(mobile)]
async fn set_voice_shortcut_mode(_mode: String) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn set_voice_shortcut_interval(_interval_ms: u64) -> Result<(), String> {
    Ok(())
}

// ===== Marker Overlay Window Commands =====

#[tauri::command]
#[cfg(desktop)]
async fn create_marker_overlay(app: tauri::AppHandle) -> Result<String, String> {
    use std::sync::atomic::Ordering;

    // Check if already open
    if MARKER_OVERLAY_OPEN.load(Ordering::SeqCst) {
        // Just show it if it exists
        if let Some(window) = app.get_webview_window("marker-overlay") {
            let _ = window.show();
            let _ = window.set_focus();
            return Ok("marker-overlay-already-exists".to_string());
        }
    }

    MARKER_OVERLAY_OPEN.store(true, Ordering::SeqCst);

    let _window = WebviewWindowBuilder::new(
        &app,
        "marker-overlay",
        tauri::WebviewUrl::App("/marker-overlay".into())
    )
    .title("EvoLoop Marker Overlay")
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
    .visible(false) // Start hidden, move in react, then show
    .transparent(true)
    .shadow(false)
    .position(100.0, 100.0)
    .build()
    .map_err(|e| format!("Failed to create marker overlay: {}", e))?;

    // We can show it immediately or let React show it. Given React does `initPosition()`, let's let React show it or show it here.
    // Actually, setting visible(false) means React needs to show it.

    Ok("marker-overlay-created".to_string())
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
    use std::sync::atomic::Ordering;

    // Check if already open
    if ANDROID_MARKER_OVERLAY_OPEN.load(Ordering::SeqCst) {
        if let Some(window) = app.get_webview_window("android-marker-overlay") {
            let _ = window.show();
            let _ = window.set_focus();
            return Ok("android-marker-overlay-already-exists".to_string());
        }
    }

    ANDROID_MARKER_OVERLAY_OPEN.store(true, Ordering::SeqCst);

    let _window = WebviewWindowBuilder::new(
        &app,
        "android-marker-overlay",
        tauri::WebviewUrl::App("/android-marker-overlay".into())
    )
    .title("EvoLoop Android Marker Overlay")
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
    .visible(false) // Start hidden to prevent jump
    .transparent(true)
    .shadow(false)
    .position(100.0, 100.0)
    .build()
    .map_err(|e| format!("Failed to create Android marker overlay: {}", e))?;

    Ok("android-marker-overlay-created".to_string())
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
        .plugin(tauri_plugin_stt::init())
        .plugin(tauri_plugin_tts::init())
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
            let record_i = MenuItem::with_id(_app, "record", "技能录制", true, Some("CmdOrCtrl+R"))?;

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
            voice_manager: spawn_voice_manager(),
        };
            _app.manage(service_state);

            // Build system tray
            let tray = tray::setup_tray(_app, &show_i, &record_i, &quit_i)?;

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
            greet,
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
            // Voice shortcut commands
            start_voice_shortcut_listener,
            stop_voice_shortcut_listener,
            set_voice_shortcut_key,
            set_voice_shortcut_duration,
            set_voice_shortcut_mode,
            set_voice_shortcut_interval,
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
                    unsafe { libc::kill(rec_child.id() as i32, libc::SIGINT); }
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
