use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::{mpsc, Mutex, RwLock};
use tokio_tungstenite::tungstenite::Message;
use log::{info, warn, error};

type EnvelopeHandler = Arc<dyn Fn(VoiceEnvelope) + Send + Sync>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VoiceEnvelope {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub body: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message_id: Option<String>,
}

pub struct VoiceWsClient {
    tx: Arc<Mutex<Option<mpsc::UnboundedSender<String>>>>,
    handler: EnvelopeHandler,
    url: String,
    connected: Arc<RwLock<bool>>,
}

impl VoiceWsClient {
    pub fn new(url: String, handler: EnvelopeHandler) -> Self {
        Self {
            tx: Arc::new(Mutex::new(None)),
            handler,
            url,
            connected: Arc::new(RwLock::new(false)),
        }
    }

    pub fn is_connected(&self) -> bool {
        *self.connected.blocking_read()
    }

    pub async fn connect(&self) -> Result<(), String> {
        let (ws_stream, _) = tokio_tungstenite::connect_async(&self.url)
            .await
            .map_err(|e| format!("WS connect failed: {}", e))?;

        let (mut ws_sender, mut ws_receiver) = ws_stream.split();
        let (tx, mut rx) = mpsc::unbounded_channel::<String>();

        *self.tx.lock().await = Some(tx);
        *self.connected.write().await = true;
        info!("[voice-ws] connected to {}", self.url);

        let handler = self.handler.clone();
        let connected = self.connected.clone();

        // Spawn receive loop
        tokio::spawn(async move {
            while let Some(msg_result) = ws_receiver.next().await {
                match msg_result {
                    Ok(Message::Text(text)) => {
                        if let Ok(envelope) = serde_json::from_str::<VoiceEnvelope>(&text) {
                            handler(envelope);
                        } else {
                            warn!("[voice-ws] failed to parse envelope: {}", &text[..text.len().min(200)]);
                        }
                    }
                    Ok(Message::Frame(_)) | Ok(Message::Binary(_)) => {
                        // Binary/raw frames not expected in normal path
                    }
                    Ok(Message::Ping(_)) | Ok(Message::Pong(_)) => {}
                    Ok(Message::Close(_)) => {
                        info!("[voice-ws] server closed connection");
                        break;
                    }
                    Err(e) => {
                        error!("[voice-ws] receive error: {}", e);
                        break;
                    }
                }
            }
            *connected.write().await = false;
        });

        // Spawn send loop
        tokio::spawn(async move {
            while let Some(text) = rx.recv().await {
                if ws_sender.send(Message::Text(text)).await.is_err() {
                    error!("[voice-ws] send failed");
                    break;
                }
            }
        });

        Ok(())
    }

    pub async fn send(&self, msg_type: &str, body: serde_json::Value) -> Result<(), String> {
        let envelope = serde_json::json!({
            "version": "2.0",
            "type": msg_type,
            "message_id": uuid::Uuid::new_v4().to_string(),
            "body": body,
        });
        let text = serde_json::to_string(&envelope).map_err(|e| e.to_string())?;
        let tx = self.tx.lock().await;
        if let Some(tx) = tx.as_ref() {
            tx.send(text).map_err(|e| e.to_string())?;
            Ok(())
        } else {
            Err("WebSocket not connected".to_string())
        }
    }

    pub async fn send_partial(&self, thread_id: &str, text: &str) -> Result<(), String> {
        self.send("voice.partial", serde_json::json!({
            "thread_id": thread_id,
            "text": text,
        })).await
    }

    pub async fn send_route(&self, thread_id: &str, text: &str, message_id: &str) -> Result<(), String> {
        self.send("voice.route", serde_json::json!({
            "thread_id": thread_id,
            "text": text,
            "message_id": message_id,
        })).await
    }

    pub async fn send_barge_in(&self, thread_id: &str) -> Result<(), String> {
        self.send("voice.barge_in", serde_json::json!({
            "thread_id": thread_id,
        })).await
    }

    pub async fn send_cancel(&self, thread_id: &str) -> Result<(), String> {
        self.send("voice.cancel", serde_json::json!({
            "thread_id": thread_id,
        })).await
    }

    pub async fn send_voice_start(&self, thread_id: &str) -> Result<(), String> {
        self.send("voice.start", serde_json::json!({
            "thread_id": thread_id,
        })).await
    }

    pub async fn send_voice_stop(&self, thread_id: &str) -> Result<(), String> {
        self.send("voice.stop", serde_json::json!({
            "thread_id": thread_id,
        })).await
    }

    pub async fn send_dictation_finalize(&self, thread_id: &str, raw_text: &str, target_locale: &str) -> Result<(), String> {
        self.send("voice.dictation.finalize", serde_json::json!({
            "thread_id": thread_id,
            "raw_text": raw_text,
            "target_locale": target_locale,
        })).await
    }

    pub async fn disconnect(&self) {
        *self.tx.lock().await = None;
        *self.connected.write().await = false;
        info!("[voice-ws] disconnected");
    }
}
