use sherpa_onnx::{VoiceActivityDetector, VadModelConfig, SileroVadModelConfig, CircularBuffer};
use std::sync::Arc;
use log::info;

const SAMPLE_RATE: i32 = 16000;

#[derive(Clone)]
pub struct VadEngine {
    vad: Arc<VoiceActivityDetector>,
}

impl VadEngine {
    pub fn new(model_path: &str, silence_duration_ms: f32) -> Result<Self, String> {
        let config = VadModelConfig {
            silero_vad: SileroVadModelConfig {
                model: Some(model_path.to_string()),
                threshold: 0.5,
                min_silence_duration: silence_duration_ms / 1000.0,
                min_speech_duration: 0.25,
                max_speech_duration: 30.0,
                window_size: 512,
            },
            ..Default::default()
        };

        let vad = VoiceActivityDetector::create(&config, 60.0)
            .ok_or_else(|| "Failed to create VAD".to_string())?;

        info!(
            "[vad] created with silence={}ms, model={}",
            silence_duration_ms, model_path
        );

        Ok(Self {
            vad: Arc::new(vad),
        })
    }

    /// Feed audio samples into VAD. Returns a list of completed speech segments.
    /// Each segment is a Vec<f32> of 16kHz mono samples.
    pub fn process(&self, samples: &[f32]) -> Vec<Vec<f32>> {
        self.vad.accept_waveform(samples);

        let mut segments = Vec::new();

        while !self.vad.is_empty() {
            if let Some(segment) = self.vad.front() {
                let seg_samples = segment.samples().to_vec();
                if !seg_samples.is_empty() {
                    segments.push(seg_samples);
                }
                self.vad.pop();
            } else {
                break;
            }
        }

        segments
    }

    /// Check if speech is currently active (for barge-in detection).
    pub fn is_speech_active(&self) -> bool {
        self.vad.detected()
    }

    pub fn reset(&self) {
        self.vad.reset();
    }

    pub fn flush(&self) {
        self.vad.flush();
    }
}
