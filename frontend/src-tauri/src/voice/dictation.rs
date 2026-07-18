use log::{info, warn, error};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::RwLock;

/// Dictation mode: ASR text → LLM polish → paste.
/// Calls LM Studio directly (127.0.0.1:1234) with stream=true.
pub struct DictationEngine {
    lm_studio_url: String,
    model_name: String,
}

#[derive(Debug, Serialize)]
struct ChatCompletionRequest {
    model: String,
    messages: Vec<ChatMessage>,
    stream: bool,
    temperature: f32,
    max_tokens: i32,
}

#[derive(Debug, Serialize, Deserialize)]
struct ChatMessage {
    role: String,
    content: String,
}

impl DictationEngine {
    pub fn new(lm_studio_url: String, model_name: String) -> Self {
        Self {
            lm_studio_url,
            model_name,
        }
    }

    /// Polish raw ASR text using LM Studio with streaming output.
    /// Calls the callback for each token chunk received.
    pub async fn polish_stream<F>(
        &self,
        raw_text: &str,
        target_locale: &str,
        mut on_token: F,
    ) -> Result<String, String>
    where
        F: FnMut(&str),
    {
        let system_prompt = if target_locale.starts_with("en") {
            "You are a dictation polish assistant. Rewrite the ASR text into clean, \
             grammatically correct text while preserving the original meaning. \
             Output only the polished text, nothing else.".to_string()
        } else {
            "你是语音输入润色助手。把用户通过语音识别输入的口语化中文改写成通顺且意思表达准确的内容。\n\
             规则：\n\
             - 保持原意，删除语气词和重复，修正明显的识别错误。\n\
             - 只输出最终润色后的文本本身，不要输出任何解释、前缀、标签或示例。\n\
             - 如果完全无法理解，只能输出：<CLARIFY>请再说一遍</CLARIFY>\n".to_string()
        };

        let request = ChatCompletionRequest {
            model: self.model_name.clone(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: system_prompt,
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: raw_text.to_string(),
                },
            ],
            stream: true,
            temperature: 0.3,
            max_tokens: 512,
        };

        let url = format!("{}/v1/chat/completions", self.lm_studio_url);
        info!("[dictation] polishing via LM Studio: {}", url);

        let client = reqwest::Client::new();
        let response = client
            .post(&url)
            .json(&request)
            .timeout(std::time::Duration::from_secs(30))
            .send()
            .await
            .map_err(|e| format!("LM Studio request failed: {}", e))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            error!("[dictation] LM Studio error {}: {}", status, body);
            return Err(format!("LM Studio returned {}: {}", status, body));
        }

        // Process SSE stream
        let mut full_text = String::new();
        let mut stream = response.bytes_stream();

        use futures_util::StreamExt;
        let mut buffer = String::new();

        while let Some(chunk_result) = stream.next().await {
            let chunk = chunk_result.map_err(|e| format!("Stream error: {}", e))?;
            buffer.push_str(&String::from_utf8_lossy(&chunk));

            // Process complete SSE lines
            while let Some(pos) = buffer.find('\n') {
                let line = buffer[..pos].trim().to_string();
                buffer = buffer[pos + 1..].to_string();

                if line.is_empty() || line.starts_with(":") {
                    continue;
                }

                if let Some(data) = line.strip_prefix("data: ") {
                    if data == "[DONE]" {
                        continue;
                    }

                    if let Ok(json) = serde_json::from_str::<serde_json::Value>(data) {
                        if let Some(delta) = json
                            .get("choices")
                            .and_then(|c| c.get(0))
                            .and_then(|c| c.get("delta"))
                            .and_then(|d| d.get("content"))
                            .and_then(|c| c.as_str())
                        {
                            if !delta.is_empty() {
                                full_text.push_str(delta);
                                on_token(delta);
                            }
                        }
                    }
                }
            }
        }

        let polished = full_text.trim().to_string();
        info!(
            "[dictation] polished: {} → {}",
            &raw_text[..raw_text.len().min(30)],
            &polished[..polished.len().min(30)]
        );

        Ok(polished)
    }
}
