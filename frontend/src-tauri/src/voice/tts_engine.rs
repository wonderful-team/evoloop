#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TtsEngineKind {
    EdgeTts,
    QwenTts,
    VolcEngine,
}

impl TtsEngineKind {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "edge" | "edge-tts" | "edgetts" => TtsEngineKind::EdgeTts,
            "qwen" | "qwen-tts" | "qwents" => TtsEngineKind::QwenTts,
            "volc" | "volcengine" | "volc-engine" => TtsEngineKind::VolcEngine,
            _ => TtsEngineKind::EdgeTts,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            TtsEngineKind::EdgeTts => "edge-tts",
            TtsEngineKind::QwenTts => "qwen-tts",
            TtsEngineKind::VolcEngine => "volcengine",
        }
    }
}
