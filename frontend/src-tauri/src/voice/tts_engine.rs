#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TtsEngineKind {
    System,
    EdgeTts,
    QwenTts,
    CosyVoice,
}

impl TtsEngineKind {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "edge" | "edge-tts" | "edgetts" => TtsEngineKind::EdgeTts,
            "qwen" | "qwen-tts" | "qwents" => TtsEngineKind::QwenTts,
            "cosyvoice" | "cosy-voice" | "cosy" => TtsEngineKind::CosyVoice,
            _ => TtsEngineKind::System,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            TtsEngineKind::System => "system",
            TtsEngineKind::EdgeTts => "edge-tts",
            TtsEngineKind::QwenTts => "qwen-tts",
            TtsEngineKind::CosyVoice => "cosyvoice",
        }
    }
}
