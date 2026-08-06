use log::{info, warn};

/// rustls 0.23 同时被 aws-lc-rs / ring 两个 feature 启用时无法自动选 provider，
/// 必须在首次使用前手动安装一个，否则 connect 时直接 panic。
static CRYPTO_INIT: std::sync::Once = std::sync::Once::new();

fn ensure_crypto_provider() {
    CRYPTO_INIT.call_once(|| {
        let _ = rustls::crypto::ring::default_provider().install_default();
    });
}

/// Edge-TTS synthesis via the `msedge-tts` crate (Microsoft Edge online TTS).
/// Returns MP3 bytes.
pub async fn speak_edge_tts(text: &str, voice_name: &str) -> Result<Vec<u8>, String> {
    use msedge_tts::tts::{client::tokio_runtime::connect_async, SpeechConfig};

    ensure_crypto_provider();

    let final_voice = if voice_name.is_empty() {
        "zh-CN-XiaoxiaoNeural".to_string()
    } else {
        voice_name.to_string()
    };

    let config = SpeechConfig {
        voice_name: final_voice,
        audio_format: "audio-24khz-48kbitrate-mono-mp3".to_string(),
        pitch: 0,
        rate: 0,
        volume: 0,
    };

    let mut client = connect_async()
        .await
        .map_err(|e| format!("Edge-TTS connect failed: {}", e))?;

    let audio = client
        .synthesize(text, &config)
        .await
        .map_err(|e| format!("Edge-TTS synthesize failed: {}", e))?;

    info!("[tts] edge-tts received {} bytes", audio.audio_bytes.len());
    Ok(audio.audio_bytes)
}

/// Qwen-TTS synthesis via DashScope multimodal-generation endpoint.
/// Returns WAV bytes.
pub async fn fetch_qwen_tts(text: &str, voice: &str) -> Result<Vec<u8>, String> {
    let api_key = std::env::var("EVOLOOP_QWEN_TTS_KEY").unwrap_or_default();
    if api_key.is_empty() {
        let err = "Qwen-TTS: EVOLOOP_QWEN_TTS_KEY not set".to_string();
        warn!("[tts] {}", err);
        return Err(err);
    }

    let final_voice = if voice.is_empty() || voice == "standard_voice" {
        "Cherry"
    } else {
        voice
    };

    let client = reqwest::Client::new();
    let body = serde_json::json!({
        "model": "qwen3-tts-flash",
        "input": {
            "text": text,
            "voice": final_voice,
            "language_type": "Chinese"
        },
        "parameters": { "format": "wav" }
    });

    let resp = client
        .post("https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Qwen-TTS request failed: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let err_body = resp.text().await.unwrap_or_default();
        return Err(format!("Qwen-TTS API error status {}: {}", status, err_body));
    }

    let json_resp: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Qwen-TTS parse response failed: {}", e))?;

    let audio_url = json_resp
        .pointer("/output/audio/url")
        .and_then(|v| v.as_str())
        .ok_or_else(|| format!("Qwen-TTS API response missing audio URL: {:?}", json_resp))?;

    let audio_resp = client
        .get(audio_url)
        .send()
        .await
        .map_err(|e| format!("Failed to download audio from Qwen-TTS: {}", e))?;

    if !audio_resp.status().is_success() {
        return Err(format!(
            "Failed to download audio: status {}",
            audio_resp.status()
        ));
    }

    let bytes = audio_resp
        .bytes()
        .await
        .map_err(|e| format!("Failed to read audio bytes: {}", e))?;

    info!("[tts] qwen-tts received {} bytes", bytes.len());

    if bytes.len() < 100 {
        return Err(format!(
            "Downloaded audio is too small: {} bytes",
            bytes.len()
        ));
    }

    if bytes[0] == b'<' || bytes[0] == b'{' {
        let preview = String::from_utf8_lossy(&bytes[..bytes.len().min(500)]);
        return Err(format!("Downloaded data is not audio: {}", preview));
    }

    Ok(bytes.to_vec())
}
