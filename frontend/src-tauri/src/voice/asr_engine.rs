use sherpa_onnx::{OnlineRecognizer, OnlineRecognizerConfig, OnlineParaformerModelConfig, OnlineModelConfig};
use std::sync::Arc;
use log::info;

#[derive(Clone)]
pub struct AsrEngine {
    recognizer: Arc<OnlineRecognizer>,
}

impl AsrEngine {
    pub fn new(model_dir: &str) -> Result<Self, String> {
        // Try non-quantized Paraformer first (encoder.onnx), fall back to int8
        let encoder = format!("{}/encoder.onnx", model_dir);
        let encoder_int8 = format!("{}/encoder.int8.onnx", model_dir);
        let decoder = format!("{}/decoder.onnx", model_dir);
        let decoder_int8 = format!("{}/decoder.int8.onnx", model_dir);
        let tokens = format!("{}/tokens.txt", model_dir);

        let (enc_path, dec_path) = if std::path::Path::new(&encoder).exists() {
            info!("[asr] using non-quantized Paraformer model from {}", model_dir);
            (encoder, decoder)
        } else {
            info!("[asr] using int8 quantized Paraformer model from {}", model_dir);
            (encoder_int8, decoder_int8)
        };

        let config = OnlineRecognizerConfig {
            model_config: OnlineModelConfig {
                paraformer: OnlineParaformerModelConfig {
                    encoder: Some(enc_path),
                    decoder: Some(dec_path),
                },
                tokens: Some(tokens),
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
            .ok_or_else(|| format!("Failed to create OnlineRecognizer from {}", model_dir))?;

        info!("[asr] recognizer created");
        Ok(Self { recognizer: Arc::new(recognizer) })
    }

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
