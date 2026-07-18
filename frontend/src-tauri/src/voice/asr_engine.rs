use sherpa_onnx::{OnlineRecognizer, OnlineRecognizerConfig, OnlineParaformerModelConfig, OnlineModelConfig};
use std::sync::Arc;
use log::{info, error};

#[derive(Clone)]
pub struct AsrEngine {
    recognizer: Arc<OnlineRecognizer>,
}

impl AsrEngine {
    pub fn new(model_dir: &str) -> Result<Self, String> {
        let config = OnlineRecognizerConfig {
            model_config: OnlineModelConfig {
                paraformer: OnlineParaformerModelConfig {
                    encoder: Some(format!("{}/encoder.int8.onnx", model_dir)),
                    decoder: Some(format!("{}/decoder.int8.onnx", model_dir)),
                },
                tokens: Some(format!("{}/tokens.txt", model_dir)),
                num_threads: 4,
                ..Default::default()
            },
            enable_endpoint: false,
            rule1_min_trailing_silence: 2.0,
            rule2_min_trailing_silence: 0.0,
            rule3_min_utterance_length: 20.0,
            ..Default::default()
        };

        let recognizer = OnlineRecognizer::create(&config)
            .ok_or_else(|| "Failed to create OnlineRecognizer".to_string())?;

        info!("[asr] recognizer created from {}", model_dir);

        Ok(Self {
            recognizer: Arc::new(recognizer),
        })
    }

    /// Process a chunk of audio samples (f32, 16kHz mono).
    /// Returns (partial_text, is_endpoint) where is_endpoint indicates
    /// the VAD/endpoint detector believes the utterance is complete.
    pub fn process(&self, stream: &sherpa_onnx::OnlineStream, samples: &[f32]) -> (String, bool) {
        stream.accept_waveform(16000, samples);

        let mut partial = String::new();
        if self.recognizer.is_ready(stream) {
            self.recognizer.decode(stream);
            if let Some(result) = self.recognizer.get_result(stream) {
                partial = result.text;
            }
        }

        let is_endpoint = self.recognizer.is_endpoint(stream);
        if is_endpoint {
            self.recognizer.reset(stream);
        }

        (partial, is_endpoint)
    }

    pub fn create_stream(&self) -> sherpa_onnx::OnlineStream {
        self.recognizer.create_stream()
    }

    pub fn recognizer(&self) -> &Arc<OnlineRecognizer> {
        &self.recognizer
    }
}
