/// Offline ASR engine for dictation mode.
/// Uses Qwen3 ASR model via sherpa-onnx's offline recognizer.
/// Designed for VAD-triggered recognition (speak → silence → recognize).

use log::info;
use sherpa_onnx::{
    OfflineRecognizer, OfflineRecognizerConfig, OfflineQwen3ASRModelConfig,
};

pub struct OfflineAsrEngine {
    recognizer: OfflineRecognizer,
}

impl OfflineAsrEngine {
    pub fn new(model_dir: &str) -> Result<Self, String> {
        let conv_frontend = format!("{}/conv_frontend.onnx", model_dir);
        let encoder = format!("{}/encoder.int8.onnx", model_dir);
        let decoder = format!("{}/decoder.int8.onnx", model_dir);
        let tokenizer = format!("{}/tokenizer", model_dir);
        let tokens = format!("{}/tokens.txt", model_dir);

        if !std::path::Path::new(&encoder).exists() {
            return Err(format!("Qwen3 ASR model not found: {}", encoder));
        }
        if !std::path::Path::new(&conv_frontend).exists() {
            return Err(format!("Qwen3 ASR conv_frontend not found: {}", conv_frontend));
        }
        if !std::path::Path::new(&decoder).exists() {
            return Err(format!("Qwen3 ASR decoder not found: {}", decoder));
        }
        if !std::path::Path::new(&tokenizer).exists() {
            return Err(format!("Qwen3 ASR tokenizer not found: {}", tokenizer));
        }

        let mut config = OfflineRecognizerConfig::default();
        config.model_config.qwen3_asr = OfflineQwen3ASRModelConfig {
            conv_frontend: Some(conv_frontend.clone()),
            encoder: Some(encoder.clone()),
            decoder: Some(decoder.clone()),
            tokenizer: Some(tokenizer.clone()),
            ..Default::default()
        };
        config.model_config.tokens = Some(tokens);
        config.model_config.num_threads = 4;

        let recognizer = OfflineRecognizer::create(&config)
            .ok_or_else(|| "Failed to create OfflineRecognizer (Qwen3 ASR)".to_string())?;

        info!("[offline_asr] Qwen3 ASR loaded");
        Ok(Self { recognizer })
    }

    /// Recognize audio samples (f32, 16kHz mono).
    /// Returns the recognized text.
    pub fn recognize(&self, samples: &[f32]) -> Result<String, String> {
        let stream = self.recognizer.create_stream();
        stream.accept_waveform(16000, samples);
        self.recognizer.decode(&stream);
        match stream.get_result() {
            Some(result) => {
                let text = result.text.trim().to_string();
                Ok(text)
            }
            None => Err("No recognition result".to_string()),
        }
    }
}
