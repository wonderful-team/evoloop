use std::str::FromStr;
use std::sync::LazyLock;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::Emitter;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

/// Global shortcut manager for voice input & skill recording.
///
/// Uses Tauri's official global-shortcut plugin.
pub struct GlobalShortcutManager {
    is_registered: AtomicBool,
    target_key: Arc<Mutex<String>>,
    record_key: Arc<Mutex<String>>,
    app_handle: Arc<Mutex<Option<tauri::AppHandle>>>,
}

impl GlobalShortcutManager {
    pub fn new() -> Self {
        Self {
            is_registered: AtomicBool::new(false),
            target_key: Arc::new(Mutex::new("F12".to_string())),
            record_key: Arc::new(Mutex::new("CmdOrCtrl+Shift+KeyR".to_string())),
            app_handle: Arc::new(Mutex::new(None)),
        }
    }

    pub fn set_app_handle(&self, app: tauri::AppHandle) {
        *self.app_handle.lock().unwrap() = Some(app);
    }

    pub fn set_target_key(&self, key: String) {
        *self.target_key.lock().unwrap() = key;
    }

    pub fn set_record_key(&self, key: String) {
        *self.record_key.lock().unwrap() = key;
    }

    pub fn set_long_press_threshold(&self, _ms: u64) {}

    pub fn set_trigger_mode(&self, _mode: TriggerMode) {}
    pub fn set_press_duration(&self, ms: u64) { self.set_long_press_threshold(ms); }
    pub fn set_double_click_interval(&self, _ms: u64) {}

    pub fn start_listening(&self) {
        if self.is_registered.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst).is_err() {
            return;
        }

        let handle = self.app_handle.lock().unwrap().clone();
        let Some(ref app) = handle else {
            return;
        };

        // macOS: CGEventTap requires Accessibility permission; warn early if missing
        #[cfg(target_os = "macos")]
        {
            let trusted = macos_accessibility_client::accessibility::application_is_trusted();
            if !trusted {
                log::warn!("[shortcut] macOS Accessibility permission not granted — global shortcuts (F12 etc.) will NOT work");
                log::warn!("[shortcut] Go to System Settings → Privacy & Security → Accessibility → add this app");
            }
        }

        // 1. Voice shortcut (F12) — short press: dialogue, long press: dictation
        let key = self.target_key.lock().unwrap().clone();
        match Shortcut::from_str(&key) {
            Ok(shortcut) => {
                let key_for_log = key.clone();
                let long_press_handled: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));
                if let Err(e) = app.global_shortcut().on_shortcut(shortcut, move |app, _event, state| {
                    match state.state {
                        ShortcutState::Pressed => {
                            log::debug!("[shortcut] F12 pressed");
                            long_press_handled.store(false, Ordering::SeqCst);
                            let app = app.clone();
                            let h = long_press_handled.clone();
                            tauri::async_runtime::spawn(async move {
                                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
                                if !h.load(Ordering::SeqCst) {
                                    h.store(true, Ordering::SeqCst);
                                    log::info!("[shortcut] F12 long press (hold) — dictation mode");
                                    let _ = app.emit("tray-voice-dictation-toggle", ());
                                }
                            });
                        }
                        ShortcutState::Released => {
                            log::debug!("[shortcut] F12 released");
                            if !long_press_handled.swap(true, Ordering::SeqCst) {
                                log::info!("[shortcut] F12 short press — dialogue mode");
                                let _ = app.emit("tray-voice-dialogue-toggle", ());
                            }
                        }
                        _ => {}
                    }
                }) {
                    log::error!("[shortcut] failed to register voice handler: {:?}", e);
                } else {
                    log::info!("[shortcut] voice shortcut registered: {key_for_log:?}");
                }
            }
            Err(e) => log::warn!("[shortcut] failed to parse voice shortcut key {key:?}: {e}"),
        }

        // 2. Skill recording global shortcut
        let rec_key_str = self.record_key.lock().unwrap().clone();
        match Shortcut::from_str(&rec_key_str) {
            Ok(rec_shortcut) => {
                let app_clone = app.clone();
                let rec_key_for_log = rec_key_str.clone();
                if let Err(e) = app.global_shortcut().on_shortcut(rec_shortcut, move |_app, _event, state| {
                    if state.state == ShortcutState::Pressed {
                        let _ = app_clone.emit("tray-record-toggle", ());
                    }
                }) {
                    log::error!("[shortcut] failed to register record handler: {:?}", e);
                } else {
                    log::info!("[shortcut] record shortcut registered: {rec_key_for_log:?}");
                }
            }
            Err(e) => log::warn!("[shortcut] failed to parse record shortcut key {rec_key_str:?}: {e}"),
        }

        self.is_registered.store(true, Ordering::SeqCst);
        log::info!("[shortcut] global shortcuts registered");
    }

    pub fn stop_listening(&self) {
        if !self.is_registered.load(Ordering::SeqCst) {
            return;
        }
        if let Ok(handle) = self.app_handle.lock() {
            if let Some(ref app) = *handle {
                let key = self.target_key.lock().unwrap().clone();
                if let Ok(shortcut) = Shortcut::from_str(&key) {
                    let _ = app.global_shortcut().unregister(shortcut);
                }
                let rec_key_str = self.record_key.lock().unwrap().clone();
                if let Ok(rec_shortcut) = Shortcut::from_str(&rec_key_str) {
                    let _ = app.global_shortcut().unregister(rec_shortcut);
                }
            }
        }
        self.is_registered.store(false, Ordering::SeqCst);
        log::info!("[shortcut] global shortcuts unregistered");
    }

    pub fn is_recording(&self) -> bool {
        false
    }
}

#[derive(Clone, Debug)]
#[allow(dead_code)]
pub enum TriggerMode {
    LongPress,
    DoubleClick,
}

pub static GLOBAL_SHORTCUT_MANAGER: LazyLock<GlobalShortcutManager> = LazyLock::new(GlobalShortcutManager::new);
