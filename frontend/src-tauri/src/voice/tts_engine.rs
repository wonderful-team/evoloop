use std::collections::VecDeque;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use log::{info, warn};

use crate::voice::audio_utils::resample_rubato;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TtsEngineKind {
    System,
    EdgeTts,
    QwenTts,
}

impl TtsEngineKind {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "edge" | "edge-tts" | "edgetts" => TtsEngineKind::EdgeTts,
            "qwen" | "qwen-tts" | "qwents" => TtsEngineKind::QwenTts,
            _ => TtsEngineKind::System,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            TtsEngineKind::System => "system",
            TtsEngineKind::EdgeTts => "edge-tts",
            TtsEngineKind::QwenTts => "qwen-tts",
        }
    }
}

#[derive(Clone)]
pub struct TtsEngine {
    pub(crate) speaking: Arc<AtomicBool>,
    pub(crate) sentence_queue: Arc<Mutex<Vec<String>>>,
    pub(crate) audio_queue: Arc<Mutex<VecDeque<f32>>>,
    stop_signal: Arc<AtomicBool>,
    lang: Arc<Mutex<String>>,
    engine: Arc<Mutex<TtsEngineKind>>,
    voice_name: Arc<Mutex<String>>,
    speed: Arc<Mutex<f32>>,
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
            engine: Arc::new(Mutex::new(TtsEngineKind::System)),
            voice_name: Arc::new(Mutex::new("zh-CN-XiaoxiaoNeural".to_string())),
            speed: Arc::new(Mutex::new(1.0)),
        })
    }

    pub fn set_engine(&self, kind: TtsEngineKind) {
        if let Ok(mut e) = self.engine.lock() {
            *e = kind;
            info!("[tts] engine set to {:?}", kind);
        }
    }

    pub fn get_engine(&self) -> TtsEngineKind {
        self.engine.lock().map(|e| *e).unwrap_or(TtsEngineKind::System)
    }

    pub fn set_voice(&self, name: String) {
        if let Ok(mut v) = self.voice_name.lock() {
            *v = name;
        }
    }

    pub fn get_voice(&self) -> String {
        self.voice_name.lock().map(|v| v.clone()).unwrap_or_default()
    }

    pub fn set_speed(&self, speed: f32) {
        if let Ok(mut s) = self.speed.lock() {
            *s = speed.clamp(0.5, 2.0);
        }
    }

    pub fn get_speed(&self) -> f32 {
        self.speed.lock().map(|s| *s).unwrap_or(1.0)
    }
    
    #[cfg(target_os = "macos")]
    fn speak_system(&self, text: &str, lang: &str) {
        self.speaking.store(true, Ordering::SeqCst);
        info!("[tts] system speak: {}...", &text[..text.len().min(50)]);
        let speed = self.get_speed();
        let speaking = self.speaking.clone();
        let text = text.to_string();
        let lang_str = lang.to_string();
        let engine_clone = self.clone();
        std::thread::spawn(move || {
            let voice = if lang_str.starts_with("zh") { "Ting-Ting" } else { "Samantha" };
            let rate = (speed * 200.0) as i32;
            let status = std::process::Command::new("say")
                .arg("-v").arg(voice)
                .arg("-r").arg(rate.to_string())
                .arg(&text)
                .status();
            if let Ok(status) = status {
                if !status.success() {
                    warn!("[tts] say command failed for: {}", text);
                }
            }
            speaking.store(false, Ordering::SeqCst);
            engine_clone.speak_next(&lang_str);
        });
    }

    fn speak_edge(&self, text: &str, _lang: &str) {
        self.speaking.store(true, Ordering::SeqCst);
        info!("[tts] edge-tts: {}...", &text[..text.len().min(50)]);
        let speaking = self.speaking.clone();
        let text = text.to_string();
        let lang_str = _lang.to_string();
        let voice_name = self.get_voice();
        let final_voice = if voice_name.is_empty() { "zh-CN-XiaoxiaoNeural".to_string() } else { voice_name };
        let engine_clone = self.clone();
        tokio::spawn(async move {
            let res = speak_edge_tts(&text, &final_voice, true).await;
            if let Err(e) = res {
                warn!("[tts] Edge-TTS failed: {}", e);
            }
            speaking.store(false, Ordering::SeqCst);
            engine_clone.speak_next(&lang_str);
        });
    }

    fn speak_qwen(&self, text: &str, _lang: &str) {
        self.speaking.store(true, Ordering::SeqCst);
        info!("[tts] qwen-tts: {}...", &text[..text.len().min(50)]);
        let speaking = self.speaking.clone();
        let text = text.to_string();
        let lang_str = _lang.to_string();
        let voice_name = self.get_voice();
        let engine_clone = self.clone();
        tokio::spawn(async move {
            let res = speak_qwen_tts(&text, &voice_name).await;
            if let Err(e) = res {
                warn!("[tts] Qwen-TTS failed: {}", e);
            }
            speaking.store(false, Ordering::SeqCst);
            engine_clone.speak_next(&lang_str);
        });
    }

    #[cfg(target_os = "macos")]
    pub fn speak(&self, text: &str, lang: &str) {
        if text.is_empty() { return; }
        let engine = self.engine.lock().map(|e| *e).unwrap_or(TtsEngineKind::System);
        match engine {
            TtsEngineKind::System => self.speak_system(text, lang),
            TtsEngineKind::EdgeTts => self.speak_edge(text, lang),
            TtsEngineKind::QwenTts => self.speak_qwen(text, lang),
        }
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
        if self.is_speaking() {
            return;
        }
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

async fn speak_edge_tts(text: &str, voice_name: &str, _is_zh: bool) -> Result<(), String> {
    use msedge_tts::tts::{client::tokio_runtime::connect_async, SpeechConfig};

    let config = SpeechConfig {
        voice_name: voice_name.to_string(),
        audio_format: "audio-24khz-48kbitrate-mono-mp3".to_string(),
        pitch: 0,
        rate: 0,
        volume: 0,
    };

    let mut client = connect_async().await
        .map_err(|e| {
            let err = format!("Edge-TTS connect failed: {}", e);
            warn!("[tts] {}", err);
            err
        })?;

    let audio = client.synthesize(text, &config).await
        .map_err(|e| {
            let err = format!("Edge-TTS synthesize failed: {}", e);
            warn!("[tts] {}", err);
            err
        })?;

    info!("[tts] edge-tts received {} bytes audio", audio.audio_bytes.len());
    let path = std::env::temp_dir().join(format!("evoloop_edge_{}.mp3", uuid::Uuid::new_v4()));
    std::fs::write(&path, &audio.audio_bytes)
        .map_err(|e| {
            let err = format!("Edge-TTS failed to write temp file: {}", e);
            warn!("[tts] {}", err);
            err
        })?;

    let status = std::process::Command::new("afplay")
        .arg(&path)
        .status()
        .map_err(|e| {
            let err = format!("afplay failed: {}", e);
            warn!("[tts] {}", err);
            let _ = std::fs::remove_file(&path);
            err
        })?;

    let _ = std::fs::remove_file(&path);

    if !status.success() {
        return Err(format!("afplay exited with status: {:?}", status.code()));
    }

    Ok(())
}

pub async fn speak_edge_tts_for_preview(text: &str, voice_name: &str) -> Result<(), String> {
    speak_edge_tts(text, voice_name, false).await
}

pub async fn speak_qwen_tts_for_preview(text: &str, voice_name: &str) -> Result<(), String> {
    speak_qwen_tts(text, voice_name).await
}

async fn speak_qwen_tts(text: &str, voice: &str) -> Result<(), String> {
    // Qwen-TTS via DashScope API (Alibaba Cloud)
    // Requires API key from env: EVOLOOP_QWEN_TTS_KEY or config
    let api_key = std::env::var("EVOLOOP_QWEN_TTS_KEY").unwrap_or_default();
    if api_key.is_empty() {
        let err = "Qwen-TTS: EVOLOOP_QWEN_TTS_KEY not set".to_string();
        warn!("[tts] {}", err);
        return Err(err);
    }

    let final_voice = if voice.is_empty() || voice == "standard_voice" { "Cherry" } else { voice };

    let client = reqwest::Client::new();
    let body = serde_json::json!({
        "model": "qwen3-tts-flash",
        "input": {
            "text": text,
            "voice": final_voice,
            "language_type": "Chinese"
        },
        "parameters": {
            "format": "wav"
        }
    });

    let resp = client
        .post("https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&body)
        .send()
        .await
        .map_err(|e| {
            let mut err_msg = format!("Qwen-TTS request failed: {}", e);
            let mut current = std::error::Error::source(&e);
            while let Some(cause) = current {
                err_msg = format!("{}: {}", err_msg, cause);
                current = std::error::Error::source(cause);
            }
            warn!("[tts] {}", err_msg);
            err_msg
        })?;

    if !resp.status().is_success() {
        let status = resp.status();
        let err_body = resp.text().await.unwrap_or_default();
        let err = format!("Qwen-TTS API error status {}: {}", status, err_body);
        warn!("[tts] {}", err);
        return Err(err);
    }

    let json_resp: serde_json::Value = resp.json().await
        .map_err(|e| format!("Qwen-TTS parse response failed: {}", e))?;

    let audio_url = json_resp
        .pointer("/output/audio/url")
        .and_then(|v| v.as_str())
        .ok_or_else(|| {
            let err = format!("Qwen-TTS API response missing audio URL: {:?}", json_resp);
            warn!("[tts] {}", err);
            err
        })?;

    info!("[tts] Qwen-TTS audio URL: {}", audio_url);

    let audio_resp = client.get(audio_url).send().await
        .map_err(|e| format!("Failed to download audio from Qwen-TTS: {}", e))?;

    if !audio_resp.status().is_success() {
        return Err(format!("Failed to download audio: status {}", audio_resp.status()));
    }

    let bytes = audio_resp.bytes().await
        .map_err(|e| format!("Failed to read audio bytes: {}", e))?;

    info!("[tts] qwen-tts received {} bytes", bytes.len());

    if bytes.len() < 100 {
        let text_preview = String::from_utf8_lossy(&bytes);
        return Err(format!("Downloaded audio is too small: {} bytes. Content: {}", bytes.len(), text_preview));
    }

    if bytes[0] == b'<' || bytes[0] == b'{' {
        let text_preview = String::from_utf8_lossy(&bytes[..bytes.len().min(500)]);
        return Err(format!("Downloaded data is not audio (JSON/XML). Content: {}", text_preview));
    }

    let path = std::env::temp_dir().join(format!("evoloop_qwen_{}.wav", uuid::Uuid::new_v4()));
    std::fs::write(&path, &bytes)
        .map_err(|e| {
            let err = format!("Qwen-TTS write failed: {}", e);
            warn!("[tts] {}", err);
            err
        })?;

    let status = std::process::Command::new("afplay")
        .arg(&path)
        .status()
        .map_err(|e| {
            let err = format!("afplay failed: {}", e);
            warn!("[tts] {}", err);
            let _ = std::fs::remove_file(&path);
            err
        })?;

    let _ = std::fs::remove_file(&path);

    if !status.success() {
        return Err(format!("afplay exited with error: {:?}", status.code()));
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    #[test]
    fn test_queue_sentence_empty_is_noop() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        tts.queue_sentence("".to_string());
        assert!(!tts.has_queued());
    }

    #[test]
    fn test_queue_and_check_state() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        assert!(!tts.has_queued());
        assert!(!tts.is_speaking());
        assert!(!tts.has_audio());

        tts.queue_sentence("你好".to_string());
        assert!(tts.has_queued());
    }

    #[test]
    fn test_speak_next_dequeues_and_sets_speaking() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        tts.queue_sentence("测试".to_string());
        assert!(tts.has_queued());

        tts.speak_next("zh-CN");
        assert!(!tts.has_queued());
        assert!(tts.is_speaking());
    }

    #[test]
    fn test_stop_clears_queues_and_speaking() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        tts.queue_sentence("你好".to_string());
        tts.queue_sentence("世界".to_string());
        assert!(tts.has_queued());

        tts.stop();
        assert!(!tts.has_queued());
        assert!(!tts.has_audio());
        assert!(!tts.is_speaking());
    }

    #[test]
    fn test_resume_clears_stop_signal() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        tts.stop();
        tts.resume();
        assert!(!tts.has_queued());
    }

    #[test]
    fn test_engine_kind_from_str() {
        assert_eq!(TtsEngineKind::from_str("system"), TtsEngineKind::System);
        assert_eq!(TtsEngineKind::from_str("edge"), TtsEngineKind::EdgeTts);
        assert_eq!(TtsEngineKind::from_str("edge-tts"), TtsEngineKind::EdgeTts);
        assert_eq!(TtsEngineKind::from_str("qwen"), TtsEngineKind::QwenTts);
        assert_eq!(TtsEngineKind::from_str("unknown"), TtsEngineKind::System);
    }

    #[test]
    fn test_set_and_get_engine() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        assert_eq!(tts.get_engine(), TtsEngineKind::System);
        tts.set_engine(TtsEngineKind::EdgeTts);
        assert_eq!(tts.get_engine(), TtsEngineKind::EdgeTts);
    }

    #[test]
    fn test_set_and_get_voice() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        tts.set_voice("zh-CN-XiaoxiaoNeural".to_string());
        assert_eq!(tts.get_voice(), "zh-CN-XiaoxiaoNeural");
    }

    #[test]
    fn test_set_and_get_speed() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        assert_eq!(tts.get_speed(), 1.0);
        tts.set_speed(1.5);
        assert!((tts.get_speed() - 1.5).abs() < 0.01);
        tts.set_speed(3.0);
        assert!((tts.get_speed() - 2.0).abs() < 0.01);
    }

    /// Verify the system `say` command is available and produces valid audio output.
    #[cfg(target_os = "macos")]
    #[test]
    fn test_say_command_produces_audio() {
        let out_path = "/tmp/evoloop_test_say.aiff";
        let _ = std::fs::remove_file(out_path);

        let status = std::process::Command::new("say")
            .arg("-v")
            .arg("Ting-Ting")
            .arg("-o")
            .arg(out_path)
            .arg("测试语音")
            .status()
            .expect("say command not found");
        assert!(status.success(), "say command exited with failure");

        let meta = std::fs::metadata(out_path)
            .expect("say command did not produce output file");
        assert!(meta.len() > 1024, "audio file too small: {} bytes", meta.len());

        let _ = std::fs::remove_file(out_path);
    }

    /// Verify `say` with different rate settings works.
    #[cfg(target_os = "macos")]
    #[test]
    fn test_say_command_different_rates() {
        for rate in [100, 200, 300] {
            let out_path = format!("/tmp/evoloop_test_say_rate_{}.aiff", rate);
            let _ = std::fs::remove_file(&out_path);

            let status = std::process::Command::new("say")
                .arg("-v").arg("Ting-Ting")
                .arg("-r").arg(rate.to_string())
                .arg("-o").arg(&out_path)
                .arg("速度测试")
                .status()
                .expect("say command not found");
            assert!(status.success(), "say failed at rate {}", rate);

            let meta = std::fs::metadata(&out_path)
                .unwrap_or_else(|_| panic!("no output at rate {}", rate));
            assert!(meta.len() > 500, "rate {}: audio too small", rate);

            let _ = std::fs::remove_file(&out_path);
        }
    }

    /// Verify the full TtsEngine speak lifecycle works end-to-end with System backend.
    #[cfg(target_os = "macos")]
    #[test]
    fn test_tts_engine_system_backend() {
        let tts = TtsEngine::new_with_queue(Arc::new(Mutex::new(VecDeque::new()))).unwrap();
        tts.set_engine(TtsEngineKind::System);
        tts.set_voice("Ting-Ting".to_string());
        tts.set_speed(1.0);

        tts.queue_sentence("你好".to_string());
        assert!(tts.has_queued());

        tts.speak_next("zh-CN");
        assert!(tts.is_speaking());
        assert!(!tts.has_queued());

        // Wait for the say process to finish
        std::thread::sleep(std::time::Duration::from_secs(3));

        assert!(!tts.is_speaking(), "say should have completed within 3s");
    }
}
