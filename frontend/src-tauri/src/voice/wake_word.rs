use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use log::info;

pub struct WakeWordDetector {
    running: Arc<AtomicBool>,
}

impl WakeWordDetector {
    pub fn new() -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn start(&mut self, _app_handle: tauri::AppHandle, word: String) -> Result<(), String> {
        if self.running.swap(true, Ordering::SeqCst) {
            return Ok(());
        }
        info!("[wake] WakeWordDetector started (stub, offline wake word disabled)");
        Ok(())
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        info!("[wake] WakeWordDetector stopped");
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}
