use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use rdev::{listen, EventType, Key};
use tauri::Emitter;

/// Global shortcut manager for voice input
pub struct GlobalShortcutManager {
    is_listening: Arc<AtomicBool>,
    is_recording: Arc<AtomicBool>,
    target_key: Arc<Mutex<String>>,
    trigger_mode: Arc<Mutex<TriggerMode>>,
    press_duration: Arc<Mutex<u64>>, // for long press (milliseconds)
    double_click_interval: Arc<Mutex<u64>>, // for double click (milliseconds)
    app_handle: Arc<Mutex<Option<tauri::AppHandle>>>,
}

#[derive(Clone, Debug)]
pub enum TriggerMode {
    LongPress,
    DoubleClick,
}

impl GlobalShortcutManager {
    pub fn new() -> Self {
        Self {
            is_listening: Arc::new(AtomicBool::new(false)),
            is_recording: Arc::new(AtomicBool::new(false)),
            target_key: Arc::new(Mutex::new("Ctrl".to_string())),
            trigger_mode: Arc::new(Mutex::new(TriggerMode::DoubleClick)), // Default to double click
            press_duration: Arc::new(Mutex::new(500)),
            double_click_interval: Arc::new(Mutex::new(300)), // 300ms default for double click
            app_handle: Arc::new(Mutex::new(None)),
        }
    }

    pub fn set_app_handle(&self, app: tauri::AppHandle) {
        *self.app_handle.lock().unwrap() = Some(app);
    }

    pub fn set_target_key(&self, key: String) {
        *self.target_key.lock().unwrap() = key;
    }

    pub fn set_trigger_mode(&self, mode: TriggerMode) {
        *self.trigger_mode.lock().unwrap() = mode;
    }

    pub fn set_press_duration(&self, duration_ms: u64) {
        *self.press_duration.lock().unwrap() = duration_ms;
    }

    pub fn set_double_click_interval(&self, interval_ms: u64) {
        *self.double_click_interval.lock().unwrap() = interval_ms;
    }

    pub fn start_listening(&self) {
        if self.is_listening.load(Ordering::SeqCst) {
            return;
        }
        self.is_listening.store(true, Ordering::SeqCst);

        let is_listening = self.is_listening.clone();
        let is_recording = self.is_recording.clone();
        let target_key = self.target_key.clone();
        let trigger_mode = self.trigger_mode.clone();
        let press_duration = self.press_duration.clone();
        let double_click_interval = self.double_click_interval.clone();
        let app_handle = self.app_handle.clone();

        thread::spawn(move || {
            // State for long press
            let mut key_pressed: Option<Instant> = None;
            let mut sent_start = false;

            // State for double click
            let mut last_click: Option<Instant> = None;
            let mut click_count = 0u32;

            let callback = move |event: rdev::Event| {
                if !is_listening.load(Ordering::SeqCst) {
                    return;
                }

                let target = target_key.lock().unwrap().clone();
                let mode = trigger_mode.lock().unwrap().clone();

                match mode {
                    TriggerMode::LongPress => {
                        Self::handle_long_press(
                            &event,
                            &target,
                            &press_duration,
                            &mut key_pressed,
                            &mut sent_start,
                            &is_recording,
                            &app_handle,
                        );
                    }
                    TriggerMode::DoubleClick => {
                        Self::handle_double_click(
                            &event,
                            &target,
                            &double_click_interval,
                            &mut last_click,
                            &mut click_count,
                            &is_recording,
                            &app_handle,
                        );
                    }
                }
            };

            // Run the listener (this blocks the thread)
            if let Err(e) = listen(callback) {
                eprintln!("Global shortcut listener error: {:?}", e);
            }
        });
    }

    fn handle_long_press(
        event: &rdev::Event,
        target: &str,
        press_duration: &Arc<Mutex<u64>>,
        key_pressed: &mut Option<Instant>,
        sent_start: &mut bool,
        is_recording: &Arc<AtomicBool>,
        app_handle: &Arc<Mutex<Option<tauri::AppHandle>>>,
    ) {
        let duration = *press_duration.lock().unwrap();

        match event.event_type {
            EventType::KeyPress(key) => {
                if matches_key(&key, target) && key_pressed.is_none() {
                    *key_pressed = Some(Instant::now());
                    *sent_start = false;
                }
            }
            EventType::KeyRelease(key) => {
                if matches_key(&key, target) {
                    if let Some(pressed_time) = *key_pressed {
                        let elapsed = pressed_time.elapsed().as_millis() as u64;

                        if elapsed >= duration && is_recording.load(Ordering::SeqCst) {
                            // Long press completed - stop recording
                            is_recording.store(false, Ordering::SeqCst);
                            Self::emit_event(app_handle, "voice-shortcut-end");
                        }
                    }
                    *key_pressed = None;
                    *sent_start = false;
                }
            }
            _ => {}
        }

        // Check for long press while key is held
        if let Some(pressed_time) = *key_pressed {
            let elapsed = pressed_time.elapsed().as_millis() as u64;
            if elapsed >= duration && !*sent_start && !is_recording.load(Ordering::SeqCst) {
                *sent_start = true;
                is_recording.store(true, Ordering::SeqCst);
                Self::emit_event(app_handle, "voice-shortcut-start");
            }
        }
    }

    fn handle_double_click(
        event: &rdev::Event,
        target: &str,
        double_click_interval: &Arc<Mutex<u64>>,
        last_click: &mut Option<Instant>,
        click_count: &mut u32,
        is_recording: &Arc<AtomicBool>,
        app_handle: &Arc<Mutex<Option<tauri::AppHandle>>>,
    ) {
        let interval = *double_click_interval.lock().unwrap();

        match event.event_type {
            EventType::KeyPress(key) => {
                if matches_key(&key, target) {
                    let now = Instant::now();

                    // Check if this is a double click
                    if let Some(last) = *last_click {
                        let elapsed = last.elapsed().as_millis() as u64;
                        if elapsed <= interval {
                            *click_count += 1;
                        } else {
                            // Too slow, reset
                            *click_count = 1;
                        }
                    } else {
                        *click_count = 1;
                    }

                    *last_click = Some(now);

                    // Double click detected
                    if *click_count >= 2 && !is_recording.load(Ordering::SeqCst) {
                        *click_count = 0;
                        is_recording.store(true, Ordering::SeqCst);
                        Self::emit_event(app_handle, "voice-shortcut-start");

                        // Auto-stop after 30 seconds (safety timeout)
                        let is_recording_clone = is_recording.clone();
                        let app_handle_clone = app_handle.clone();
                        thread::spawn(move || {
                            thread::sleep(Duration::from_secs(30));
                            if is_recording_clone.load(Ordering::SeqCst) {
                                is_recording_clone.store(false, Ordering::SeqCst);
                                Self::emit_event(&app_handle_clone, "voice-shortcut-end");
                            }
                        });
                    }
                }
            }
            EventType::KeyRelease(key) => {
                if matches_key(&key, target) && is_recording.load(Ordering::SeqCst) {
                    // For double click mode, we stop on key release
                    // But add a small delay to allow for "hold to record" behavior
                    let is_recording_clone = is_recording.clone();
                    let app_handle_clone = app_handle.clone();
                    thread::spawn(move || {
                        thread::sleep(Duration::from_millis(100));
                        if is_recording_clone.load(Ordering::SeqCst) {
                            is_recording_clone.store(false, Ordering::SeqCst);
                            Self::emit_event(&app_handle_clone, "voice-shortcut-end");
                        }
                    });
                }
            }
            _ => {}
        }
    }

    fn emit_event(app_handle: &Arc<Mutex<Option<tauri::AppHandle>>>, event: &str) {
        if let Ok(handle) = app_handle.lock() {
            if let Some(ref h) = *handle {
                let _ = h.emit(event, ());
            }
        }
    }

    pub fn stop_listening(&self) {
        self.is_listening.store(false, Ordering::SeqCst);
        self.is_recording.store(false, Ordering::SeqCst);
    }

    pub fn is_recording(&self) -> bool {
        self.is_recording.load(Ordering::SeqCst)
    }
}

fn matches_key(key: &Key, target: &str) -> bool {
    match target {
        "Alt" => matches!(key, Key::Alt | Key::AltGr),
        "Ctrl" | "Control" => matches!(key, Key::ControlLeft | Key::ControlRight),
        "Shift" => matches!(key, Key::ShiftLeft | Key::ShiftRight),
        "Cmd" | "Meta" | "Command" | "Windows" => matches!(key, Key::MetaLeft | Key::MetaRight),
        "F1" => matches!(key, Key::F1),
        "F2" => matches!(key, Key::F2),
        "F3" => matches!(key, Key::F3),
        "F4" => matches!(key, Key::F4),
        "F5" => matches!(key, Key::F5),
        "F6" => matches!(key, Key::F6),
        "F7" => matches!(key, Key::F7),
        "F8" => matches!(key, Key::F8),
        "F9" => matches!(key, Key::F9),
        "F10" => matches!(key, Key::F10),
        "F11" => matches!(key, Key::F11),
        "F12" => matches!(key, Key::F12),
        "Escape" | "Esc" => matches!(key, Key::Escape),
        "Space" => matches!(key, Key::Space),
        "Tab" => matches!(key, Key::Tab),
        _ => false,
    }
}

// Default instance for the app
lazy_static::lazy_static! {
    pub static ref GLOBAL_SHORTCUT_MANAGER: GlobalShortcutManager = GlobalShortcutManager::new();
}
