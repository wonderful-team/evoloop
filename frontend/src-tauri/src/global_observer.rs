use active_win_pos_rs::get_active_window;
use parking_lot::Mutex;
use rdev::{listen, Event, EventType, Key};
use serde::Serialize;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter};

#[derive(Clone, Serialize, Debug)]
pub struct GlobalEvent {
    pub timestamp: u64,
    pub event_type: String,
    pub key: Option<String>,
    pub mouse_button: Option<String>,
    pub position: Option<(i32, i32)>,
    pub window_title: Option<String>,
    pub app_name: Option<String>,
    pub process_id: Option<u64>,
}

pub struct GlobalObserver {
    is_recording: Arc<AtomicBool>,
    // Thread handle to allow joining/stopping if needed (though rdev listen blocks)
    // In this simple version, we just detach the thread and control logic via atomic flag
    app_handle: Arc<Mutex<Option<AppHandle>>>,
    last_mouse_pos: Arc<Mutex<Option<(f64, f64)>>>,
}

impl GlobalObserver {
    pub fn new() -> Self {
        Self {
            is_recording: Arc::new(AtomicBool::new(false)),
            app_handle: Arc::new(Mutex::new(None)),
            last_mouse_pos: Arc::new(Mutex::new(None)),
        }
    }

    pub fn start(&self, app: AppHandle) {
        if self.is_recording.load(Ordering::SeqCst) {
            return;
        }

        *self.app_handle.lock() = Some(app);
        self.is_recording.store(true, Ordering::SeqCst);

        let is_recording = self.is_recording.clone();
        let app_handle = self.app_handle.clone();
        let last_mouse_pos = self.last_mouse_pos.clone();

        // Spawn a thread for rdev listener
        thread::spawn(move || {
            if let Err(error) = listen(move |event| {
                if !is_recording.load(Ordering::SeqCst) {
                    return; // Just ignore events if not recording, but thread keeps running
                            // Optimally we would stop the listener, but rdev doesn't support clean stop easily yet
                }

                let global_event = convert_event(event, &last_mouse_pos);
                
                if let Some(mut evt) = global_event {
                    // Enrich with active window info
                    // Note: get_active_window() can be slow, so maybe throttle this or do it async?
                    // For now we do it for every significant event (not mouse move)
                    if evt.event_type != "mouse_move" {
                         if let Ok(window) = get_active_window() {
                            evt.window_title = Some(window.title);
                            evt.app_name = Some(window.app_name);
                            evt.process_id = Some(window.process_id);
                        }
                    }

                    // Emit to frontend
                    if let Some(handle) = app_handle.lock().as_ref() {
                        let _ = handle.emit("global-event", evt);
                    }
                }
            }) {
                println!("Error: {:?}", error)
            }
        });
    }

    pub fn stop(&self) {
        self.is_recording.store(false, Ordering::SeqCst);
    }

    pub fn is_recording(&self) -> bool {
        self.is_recording.load(Ordering::SeqCst)
    }
}

fn convert_event(event: Event, _last_mouse_pos: &Arc<Mutex<Option<(f64, f64)>>>) -> Option<GlobalEvent> {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis() as u64;

    match event.event_type {
        EventType::KeyPress(key) => Some(GlobalEvent {
            timestamp,
            event_type: "key_press".to_string(),
            key: Some(format!("{:?}", key)),
            mouse_button: None,
            position: None,
            window_title: None,
            app_name: None,
            process_id: None,
        }),
        EventType::KeyRelease(_) => None, // Ignore release to reduce noise
        EventType::ButtonPress(btn) => Some(GlobalEvent {
            timestamp,
            event_type: "mouse_click".to_string(),
            key: None,
            mouse_button: Some(format!("{:?}", btn)),
            position: None, // rdev button press doesn't have pos, need to track separate move or get current
            window_title: None,
            app_name: None,
            process_id: None,
        }),
        EventType::MouseMove { x: _, y: _ } => {
            // Throttle mouse moves: only emit if moved significantly or time passed?
            // For now, let's just update internal state and NOT emit every move to avoid flooding
            // OR emit with throttling. Let's skipping generic moves for now and only track clicks/keys
            // but we update the last known position if needed.
            // *last_mouse_pos.lock() = Some((x, y));
            None 
        }
        _ => None,
    }
}
