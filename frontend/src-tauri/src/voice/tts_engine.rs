#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TtsEngineKind {
    EdgeTts,
    QwenTts,
}

impl TtsEngineKind {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "edge" | "edge-tts" | "edgetts" => TtsEngineKind::EdgeTts,
            "qwen" | "qwen-tts" | "qwents" => TtsEngineKind::QwenTts,
            _ => TtsEngineKind::EdgeTts,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            TtsEngineKind::EdgeTts => "edge-tts",
            TtsEngineKind::QwenTts => "qwen-tts",
        }
    }
}
