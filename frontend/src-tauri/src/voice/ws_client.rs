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

const RECONNECT_DELAY_SECS: u64 = 3;

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

    /// Connect and auto-reconnect on disconnect.
    /// The returned task runs forever (or until the client is dropped).
    pub async fn connect(&self) -> Result<(), String> {
        let url = self.url.clone();
        let handler = self.handler.clone();
        let tx_state = self.tx.clone();
        let connected = self.connected.clone();

        tokio::spawn(async move {
            loop {
                match tokio_tungstenite::connect_async(&url).await {
                    Ok((ws_stream, _)) => {
                        info!("[voice-ws] connected to {}", url);
                        let (mut ws_sender, mut ws_receiver) = ws_stream.split();
                        let (tx, mut rx) = mpsc::unbounded_channel::<String>();

                        *tx_state.lock().await = Some(tx);
                        *connected.write().await = true;

                        let handler = handler.clone();
                        let connected_clone = connected.clone();
                        let tx_state_clone = tx_state.clone();

                        // Receive loop
                        let recv = tokio::spawn(async move {
                            while let Some(msg_result) = ws_receiver.next().await {
                                match msg_result {
                                    Ok(Message::Text(text)) => {
                                        if let Ok(envelope) = serde_json::from_str::<VoiceEnvelope>(&text) {
                                            handler(envelope);
                                        } else {
                                            warn!("[voice-ws] failed to parse envelope: {}",
                                                &text[..text.len().min(200)]);
                                        }
                                    }
                                    Ok(Message::Frame(_)) | Ok(Message::Binary(_)) => {}
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
                            *connected_clone.write().await = false;
                            *tx_state_clone.lock().await = None;
                        });

                        // Send loop
                        while let Some(text) = rx.recv().await {
                            if ws_sender.send(Message::Text(text)).await.is_err() {
                                error!("[voice-ws] send failed");
                                break;
                            }
                        }

                        recv.abort();
                        *connected.write().await = false;
                        *tx_state.lock().await = None;
                    }
                    Err(e) => {
                        error!("[voice-ws] connect failed: {} (retry in {}s)", e, RECONNECT_DELAY_SECS);
                    }
                }

                tokio::time::sleep(std::time::Duration::from_secs(RECONNECT_DELAY_SECS)).await;
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

    pub async fn send_barge_in(&self, thread_id: &str) -> Result<(), String> {
        self.send("voice.barge_in", serde_json::json!({
            "thread_id": thread_id,
        })).await
    }

    pub async fn send_route(&self, thread_id: &str, text: &str, message_id: &str, project_id: Option<&str>) -> Result<(), String> {
        let mut body = serde_json::json!({
            "thread_id": thread_id,
            "text": text,
            "message_id": message_id,
        });
        if let Some(pid) = project_id {
            body["project_id"] = serde_json::json!(pid);
        }
        self.send("voice.route", body).await
    }

    pub async fn send_dictation_finalize(&self, thread_id: &str, raw_text: &str, target_locale: &str, project_id: Option<&str>) -> Result<(), String> {
        let mut body = serde_json::json!({
            "thread_id": thread_id,
            "raw_text": raw_text,
            "target_locale": target_locale,
        });
        if let Some(pid) = project_id {
            body["project_id"] = serde_json::json!(pid);
        }
        self.send("voice.dictation.finalize", body).await
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


    pub async fn disconnect(&self) {
        *self.tx.lock().await = None;
        *self.connected.write().await = false;
        info!("[voice-ws] disconnected");
    }
}
