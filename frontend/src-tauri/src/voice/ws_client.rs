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
    #[serde(skip)]
    pub raw_bytes: Option<Vec<u8>>,
}

const RECONNECT_DELAY_SECS: u64 = 3;
const PING_INTERVAL_SECS: u64 = 20;
const PING_TIMEOUT_SECS: u64 = 45;

pub struct VoiceWsClient {
    tx: Arc<Mutex<Option<mpsc::UnboundedSender<Message>>>>,
    handler: EnvelopeHandler,
    url: String,
    connected: Arc<RwLock<bool>>,
    ping_failures: Arc<Mutex<u32>>,
}

impl VoiceWsClient {
    pub fn new(url: String, handler: EnvelopeHandler) -> Self {
        Self {
            tx: Arc::new(Mutex::new(None)),
            handler,
            url,
            connected: Arc::new(RwLock::new(false)),
            ping_failures: Arc::new(Mutex::new(0)),
        }
    }

    pub fn is_connected(&self) -> bool {
        *self.connected.blocking_read()
    }

    /// Connect and auto-reconnect on disconnect.
    pub async fn connect(&self) -> Result<(), String> {
        let url = self.url.clone();
        let handler = self.handler.clone();
        let tx_state = self.tx.clone();
        let connected_state = self.connected.clone();
        let ping_failures = self.ping_failures.clone();

        tokio::spawn(async move {
            loop {
                match tokio_tungstenite::connect_async(&url).await {
                    Ok((ws_stream, _)) => {
                        info!("[voice-ws] connected to {}", url);
                        let (mut ws_sender, mut ws_receiver) = ws_stream.split();
                        let (tx, mut rx) = mpsc::unbounded_channel::<Message>();

                        *tx_state.lock().await = Some(tx);
                        *connected_state.write().await = true;
                        *ping_failures.lock().await = 0;

                        let handler = handler.clone();
                        let connected_inner = connected_state.clone();
                        let tx_state_inner = tx_state.clone();
                        let last_recv = Arc::new(Mutex::new(tokio::time::Instant::now()));

                        // Receive loop (no ping, just update last_recv timestamp) (no ping, just update last_recv timestamp)
                        let last_recv_recv = last_recv.clone();
                        let recv = tokio::spawn(async move {
                            while let Some(msg_result) = ws_receiver.next().await {
                                match msg_result {
                                    Ok(Message::Text(text)) => {
                                        *last_recv_recv.lock().await = tokio::time::Instant::now();
                                        if let Ok(envelope) = serde_json::from_str::<VoiceEnvelope>(&text) {
                                            handler(envelope);
                                        } else {
                                            warn!("[voice-ws] failed to parse envelope: {}",
                                                &text[..text.len().min(200)]);
                                        }
                                    }
                                    Ok(Message::Binary(bin)) => {
                                        *last_recv_recv.lock().await = tokio::time::Instant::now();
                                        let envelope = VoiceEnvelope {
                                            msg_type: "voice.audio_frame".to_string(),
                                            body: None,
                                            message_id: None,
                                            raw_bytes: Some(bin),
                                        };
                                        handler(envelope);
                                    }
                                    Ok(Message::Frame(_)) => {}
                                    Ok(Message::Ping(_)) | Ok(Message::Pong(_)) => {
                                        *last_recv_recv.lock().await = tokio::time::Instant::now();
                                    }
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
                            *connected_inner.write().await = false;
                            *tx_state_inner.lock().await = None;
                        });

                        // Send loop with keepalive ping + timeout detection
                        let mut last_ping = tokio::time::Instant::now();
                        loop {
                            tokio::select! {
                                msg = rx.recv() => {
                                    match msg {
                                        Some(m) => {
                                            if ws_sender.send(m).await.is_err() {
                                                error!("[voice-ws] send failed");
                                                break;
                                            }
                                        }
                                        None => break,
                                    }
                                }
                                _ = tokio::time::sleep_until(
                                    (last_ping + std::time::Duration::from_secs(PING_INTERVAL_SECS)).into()
                                ) => {
                                    // JSON ping keepalive
                                    let ping = serde_json::json!({
                                        "version": "2.0",
                                        "type": "ping",
                                        "message_id": uuid::Uuid::new_v4().to_string(),
                                        "body": {},
                                    });
                                    if let Ok(ping_text) = serde_json::to_string(&ping) {
                                        if ws_sender.send(Message::Text(ping_text)).await.is_err() {
                                            warn!("[voice-ws] ping send failed");
                                            break;
                                        }
                                    }
                                    last_ping = tokio::time::Instant::now();

                                    // Timeout detection
                                    let elapsed = last_recv.lock().await.elapsed();
                                    if elapsed > std::time::Duration::from_secs(PING_TIMEOUT_SECS) {
                                        warn!("[voice-ws] no message for {:?}, reconnecting", elapsed);
                                        break;
                                    }
                                }
                            }
                        }

                        recv.abort();
                        *connected_state.write().await = false;
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
        // Wait for connection (max ~3s = reconnect interval)
        for _ in 0..30 {
            let tx = self.tx.lock().await;
            if let Some(tx) = tx.as_ref() {
                return tx.send(Message::Text(text)).map_err(|e| e.to_string());
            }
            drop(tx);
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        }
        Err("WebSocket not connected".to_string())
    }

    pub async fn send_binary(&self, bytes: Vec<u8>) -> Result<(), String> {
        // Wait for connection (max ~3s)
        for _ in 0..30 {
            let tx = self.tx.lock().await;
            if let Some(tx) = tx.as_ref() {
                return tx.send(Message::Binary(bytes)).map_err(|e| e.to_string());
            }
            drop(tx);
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        }
        Err("WebSocket not connected".to_string())
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

    pub async fn send_voice_start(&self, thread_id: &str, mode: &str) -> Result<(), String> {
        self.send("voice.start", serde_json::json!({
            "thread_id": thread_id,
            "mode": mode,
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

