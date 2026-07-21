use std::str::FromStr;
use std::sync::LazyLock;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::Emitter;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

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
            target_key: Arc::new(Mutex::new("Alt+F12".to_string())),
            record_key: Arc::new(Mutex::new("CmdOrCtrl+Shift+R".to_string())),
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
        if self.is_registered.load(Ordering::SeqCst) {
            return;
        }

        let handle = self.app_handle.lock().unwrap().clone();
        let Some(app) = handle else {
            return;
        };

        // 1. Voice shortcut (e.g. "Alt+F12" = Option+F12 on macOS)
        let key = self.target_key.lock().unwrap().clone();
        if let Ok(shortcut) = Shortcut::from_str(&key) {
            let app_clone = app.clone();
            if let Err(e) = app.global_shortcut().on_shortcut(shortcut, move |_app, _event, state| {
                if state.state == ShortcutState::Pressed {
                    let _ = app_clone.emit("voice-shortcut-press", ());
                }
            }) {
                log::error!("[shortcut] failed to register voice handler: {:?}", e);
            }
            if let Err(e) = app.global_shortcut().register(shortcut) {
                log::error!("[shortcut] failed to register voice key: {:?}", e);
            }
        }

        // 2. Skill recording global shortcut
        let rec_key_str = self.record_key.lock().unwrap().clone();
        if let Ok(rec_shortcut) = Shortcut::from_str(&rec_key_str) {
            let app_clone = app.clone();
            if let Err(e) = app.global_shortcut().on_shortcut(rec_shortcut, move |_app, _event, state| {
                if state.state == ShortcutState::Pressed {
                    let _ = app_clone.emit("tray-record-toggle", ());
                }
            }) {
                log::error!("[shortcut] failed to register record handler: {:?}", e);
            }
            if let Err(e) = app.global_shortcut().register(rec_shortcut) {
                log::error!("[shortcut] failed to register record key: {:?}", e);
            }
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

fn key_to_code(key: &str) -> Option<Code> {
    match key {
        "F1" => Some(Code::F1),
        "F2" => Some(Code::F2),
        "F3" => Some(Code::F3),
        "F4" => Some(Code::F4),
        "F5" => Some(Code::F5),
        "F6" => Some(Code::F6),
        "F7" => Some(Code::F7),
        "F8" => Some(Code::F8),
        "F9" => Some(Code::F9),
        "F10" => Some(Code::F10),
        "F11" => Some(Code::F11),
        "F12" => Some(Code::F12),
        _ => None,
    }
}

pub static GLOBAL_SHORTCUT_MANAGER: LazyLock<GlobalShortcutManager> = LazyLock::new(GlobalShortcutManager::new);
