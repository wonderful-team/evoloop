/// Native wake word detector using the same ASR pipeline as voice session.
///
/// Continuously feeds mic audio to the ASR engine and checks partial
/// results for the wake word. When detected, emits `wake-word-detected`
/// Tauri event so the frontend can auto-start voice session.

use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use log::info;
use tauri::Emitter;

use crate::voice::asr_engine::AsrEngine;
use crate::voice::mic_capture::MicCapture;

// MicCapture uses cpal types which are Send on macOS but not automatically detected.
unsafe impl Send for WakeWordDetector {}
unsafe impl Sync for WakeWordDetector {}

pub struct WakeWordDetector {
    running: Arc<AtomicBool>,
    mic: Option<MicCapture>,
}

impl WakeWordDetector {
    pub fn new() -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            mic: None,
        }
    }

    pub fn start(
        &mut self,
        app_handle: tauri::AppHandle,
        wake_word: String,
        asr_engine: Arc<AsrEngine>,
    ) -> Result<(), String> {
        if self.running.swap(true, Ordering::SeqCst) {
            return Ok(());
        }

        let running = self.running.clone();
        let ww = wake_word.to_lowercase();
        let mut stream = asr_engine.create_stream();
        let stream = Arc::new(Mutex::new(stream));
        let asr = asr_engine.clone();
        let app = app_handle.clone();

        let mut mic = MicCapture::new();
        {
            let running = running.clone();
            let ww = ww.clone();
            let stream = stream.clone();
            let asr = asr.clone();
            let app = app.clone();

            mic.start(move |samples: &[f32]| {
                if !running.load(Ordering::SeqCst) {
                    return;
                }

                // Feed samples to ASR
                if let Ok(mut s) = stream.lock() {
                    s.accept_waveform(16000, samples);
                    if asr.recognizer().is_ready(&s) {
                        asr.recognizer().decode(&s);
                        if let Some(result) = asr.recognizer().get_result(&s) {
                            let text = result.text.to_lowercase();
                            if text.contains(&ww) {
                                info!("[wake] Detected '{}' in '{}'", ww, text);
                                asr.recognizer().reset(&s);
                                let _ = app.emit("wake-word-detected", serde_json::json!({
                                    "word": ww,
                                    "transcript": text,
                                }));
                            }
                        }
                    }
                }
            })?;
        }

        self.mic = Some(mic);
        info!("[wake] Listener started for '{}'", wake_word);
        Ok(())
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        if let Some(mic) = self.mic.take() {
            drop(mic);
        }
        info!("[wake] Listener stopped");
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}

impl Drop for WakeWordDetector {
    fn drop(&mut self) {
        self.stop();
    }
}
