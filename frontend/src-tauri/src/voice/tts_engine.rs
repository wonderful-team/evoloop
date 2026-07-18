use std::collections::VecDeque;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use log::{info, warn};
use rubato::{Resampler, SincFixedIn, SincInterpolationParameters, SincInterpolationType, WindowFunction};
use uuid::Uuid;

/// TTS engine that produces audio into a shared queue.
/// The audio is consumed by the VoiceProcessingIO output callback, which both
/// plays it to the speakers and exposes it as the AEC reference signal.
/// On non-macOS platforms, the queue is never filled (no TTS audio).
pub struct TtsEngine {
    speaking: Arc<AtomicBool>,
    sentence_queue: Arc<Mutex<Vec<String>>>,
    audio_queue: Arc<Mutex<VecDeque<f32>>>,
    stop_signal: Arc<AtomicBool>,
    lang: Arc<Mutex<String>>,
}

impl TtsEngine {
    pub fn new_with_queue(audio_queue: Arc<Mutex<VecDeque<f32>>>) -> Result<Self, String> {
        info!("[tts] TTS engine created (audio queue backend)");
        Ok(Self {
            speaking: Arc::new(AtomicBool::new(false)),
            sentence_queue: Arc::new(Mutex::new(Vec::new())),
            audio_queue,
            stop_signal: Arc::new(AtomicBool::new(false)),
            lang: Arc::new(Mutex::new("zh-CN".to_string())),
        })
    }

    #[cfg(target_os = "macos")]
    pub fn speak(&self, text: &str, lang: &str) {
        if text.is_empty() {
            return;
        }
        self.speaking.store(true, Ordering::SeqCst);
        if let Ok(mut l) = self.lang.lock() {
            *l = lang.to_string();
        }

        info!("[tts] speaking: {}...", &text[..text.len().min(50)]);

        let audio_queue = self.audio_queue.clone();
        let speaking = self.speaking.clone();
        let stop_signal = self.stop_signal.clone();
        let text = text.to_string();
        let lang = lang.to_string();

        std::thread::spawn(move || {
            let voice = if lang.starts_with("zh") { "Ting-Ting" } else { "Samantha" };
            let temp_path = std::env::temp_dir().join(format!("evoloop_tts_{}.wav", Uuid::new_v4()));

            let status = std::process::Command::new("say")
                .arg("-v")
                .arg(voice)
                .arg("-r")
                .arg("200")
                .arg("-o")
                .arg(&temp_path)
                .arg(&text)
                .status();

            if let Ok(status) = status {
                if status.success() {
                        if let Ok(mut reader) = hound::WavReader::open(&temp_path) {
                        let spec = reader.spec();
                        let samples_i16: Vec<i16> = reader.samples::<i16>()
                            .filter_map(|s| s.ok())
                            .collect();
                        let samples_f32: Vec<f32> = samples_i16
                            .iter()
                            .map(|s| *s as f32 / i16::MAX as f32)
                            .collect();

                        let resampled = if spec.sample_rate != 16000 {
                            resample_rubato(&samples_f32,
                                spec.sample_rate,
                                16000,
                            )
                        } else {
                            samples_f32
                        };

                        if let Ok(mut q) = audio_queue.lock() {
                            if !stop_signal.load(Ordering::SeqCst) {
                                q.extend(resampled);
                            }
                        }
                    }
                }
                let _ = std::fs::remove_file(temp_path);
            }

            speaking.store(false, Ordering::SeqCst);
        });
    }

    #[cfg(not(target_os = "macos"))]
    pub fn speak(&self, _text: &str, _lang: &str) {
        warn!("[tts] TTS not supported on this platform");
    }

    /// Queue a sentence for synthesis (used by streaming TTS).
    pub fn queue_sentence(&self, sentence: String) {
        if sentence.is_empty() {
            return;
        }
        if let Ok(mut q) = self.sentence_queue.lock() {
            q.push(sentence);
        }
    }

    /// Speak the next queued sentence.
    pub fn speak_next(&self, lang: &str) {
        if let Ok(mut q) = self.sentence_queue.lock() {
            if let Some(sentence) = q.first().cloned() {
                q.remove(0);
                drop(q);
                self.speak(&sentence, lang);
            }
        }
    }

    /// Stop all speech output immediately (barge-in).
    pub fn stop(&self) {
        self.stop_signal.store(true, Ordering::SeqCst);
        self.speaking.store(false, Ordering::SeqCst);
        if let Ok(mut q) = self.sentence_queue.lock() {
            q.clear();
        }
        if let Ok(mut q) = self.audio_queue.lock() {
            q.clear();
        }
        info!("[tts] stopped (barge-in)");
    }

    pub fn resume(&self) {
        self.stop_signal.store(false, Ordering::SeqCst);
    }

    pub fn is_speaking(&self) -> bool {
        self.speaking.load(Ordering::SeqCst)
    }

    pub fn has_queued(&self) -> bool {
        if let Ok(q) = self.sentence_queue.lock() {
            !q.is_empty()
        } else {
            false
        }
    }

    pub fn has_audio(&self) -> bool {
        if let Ok(q) = self.audio_queue.lock() {
            !q.is_empty()
        } else {
            false
        }
    }
}

/// Audio resampler using rubato (Sinc band-limited interpolation).
fn resample_rubato(input: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if from_rate == to_rate || input.is_empty() {
        return input.to_vec();
    }

    let ratio = to_rate as f64 / from_rate as f64;
    let params = SincInterpolationParameters {
        sinc_len: 256,
        f_cutoff: 0.95,
        interpolation: SincInterpolationType::Linear,
        oversampling_factor: 256,
        window: WindowFunction::BlackmanHarris2,
    };

    let mut resampler = SincFixedIn::<f32>::new(
        ratio,
        1.0,
        params,
        input.len(),
        1,
    ).expect("Failed to create rubato resampler");

    let waves_in = vec![input.to_vec()];
    let mut output = resampler.process(&waves_in, None).expect("Rubato resampling failed");
    output.remove(0)
}
