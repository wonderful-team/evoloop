//! Server-Client Proxy
//!
//! Forwards HTTP requests from Server to Client and vice versa.
//! When Server needs a tool executed, it calls Tauri via HTTP,
//! and Tauri forwards the request to Client via Sidecar.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::mpsc;

use crate::sidecar::SidecarClient;

/// Configuration for the proxy server
#[derive(Debug, Clone)]
pub struct ProxyConfig {
    /// Server base URL
    pub server_url: String,
    /// Auth token for Server
    pub auth_token: Option<String>,
}

impl Default for ProxyConfig {
    fn default() -> Self {
        Self {
            server_url: "https://api.evoloop.dev".to_string(),
            auth_token: None,
        }
    }
}

/// Pending tool requests from Server
#[derive(Debug)]
pub struct PendingToolRequest {
    pub request_id: String,
    pub thread_id: String,
    pub tool: String,
    pub params: serde_json::Value,
    pub response_tx: tokio::sync::oneshot::Sender<ToolResult>,
}

/// Tool execution result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub success: bool,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
}

/// Proxy state
pub struct ProxyState {
    pub config: Arc<Mutex<ProxyConfig>>,
    pub pending_requests: Arc<Mutex<HashMap<String, tokio::sync::oneshot::Sender<ToolResult>>>>,
    pub is_running: Arc<Mutex<bool>>,
}

impl ProxyState {
    pub fn new() -> Self {
        Self {
            config: Arc::new(Mutex::new(ProxyConfig::default())),
            pending_requests: Arc::new(Mutex::new(HashMap::new())),
            is_running: Arc::new(Mutex::new(false)),
        }
    }

    /// Configure the proxy
    pub fn configure(&self, server_url: String, auth_token: Option<String>) {
        let mut config = self.config.lock().unwrap();
        config.server_url = server_url;
        config.auth_token = auth_token;
    }
}

impl Default for ProxyState {
    fn default() -> Self {
        Self::new()
    }
}

/// Handle a tool request from Server
pub async fn handle_server_tool_request(
    app: &AppHandle,
    request: ServerToolRequest,
) -> Result<ToolResult, String> {
    let state = app.state::<super::AppServiceState>();

    // Get the sidecar client
    let client_opt = {
        let lock = state.sidecar_client.lock().map_err(|e| format!("Lock error: {}", e))?;
        lock.clone()
    };

    if let Some(client) = client_opt {
        if !client.is_ready() {
            return Err("Client not ready".to_string());
        }

        // Execute tool through Client
        use crate::sidecar::ToClientMessage;

        let response = client
            .request(ToClientMessage::Execute {
                id: request.request_id.clone(),
                tool: request.tool,
                params: request.params,
            })
            .await
            .map_err(|e| format!("Tool execution failed: {}", e))?;

        Ok(ToolResult {
            success: response.error.is_none(),
            result: response.result,
            error: response.error,
        })
    } else {
        Err("Sidecar Client not available".to_string())
    }
}

/// Tool request from Server
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ServerToolRequest {
    pub request_id: String,
    pub thread_id: String,
    pub tool: String,
    pub params: serde_json::Value,
}

/// Submit tool result back to Server
pub async fn submit_tool_result_to_server(
    config: &ProxyConfig,
    thread_id: String,
    request_id: String,
    result: ToolResult,
) -> Result<(), String> {
    let client = reqwest::Client::new();

    let url = format!("{}/api/v1/chat/{}/tool_result", config.server_url, thread_id);

    let mut request = client
        .post(&url)
        .json(&serde_json::json!({
            "request_id": request_id,
            "result": result,
        }));

    if let Some(ref token) = config.auth_token {
        request = request.header("Authorization", format!("Bearer {}", token));
    }

    let response = request
        .send()
        .await
        .map_err(|e| format!("HTTP error: {}", e))?;

    if response.status().is_success() {
        Ok(())
    } else {
        let status = response.status();
        let text = response
            .text()
            .await
            .unwrap_or_default();
        Err(format!("Server error {}: {}", status, text))
    }
}

/// Poll Server for pending tool requests
pub async fn poll_server_for_requests(
    config: &ProxyConfig,
) -> Result<Vec<ServerToolRequest>, String> {
    let client = reqwest::Client::new();

    let url = format!("{}/api/v1/pending_tools", config.server_url);

    let mut request = client.get(&url);

    if let Some(ref token) = config.auth_token {
        request = request.header("Authorization", format!("Bearer {}", token));
    }

    let response = request
        .send()
        .await
        .map_err(|e| format!("HTTP error: {}", e))?;

    if response.status().is_success() {
        let requests: Vec<ServerToolRequest> = response
            .json()
            .await
            .map_err(|e| format!("JSON parse error: {}", e))?;
        Ok(requests)
    } else {
        let status = response.status();
        let text = response
            .text()
            .await
            .unwrap_or_default();
        Err(format!("Server error {}: {}", status, text))
    }
}

/// Start the proxy polling loop
pub fn start_proxy_polling(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let proxy_state = app.state::<super::ProxyState>();

        loop {
            let config = {
                let cfg = proxy_state.config.lock().unwrap();
                cfg.clone()
            };

            if *proxy_state.is_running.lock().unwrap() {
                match poll_server_for_requests(&config).await {
                    Ok(requests) => {
                        for request in requests {
                            // Process each request
                            match handle_server_tool_request(&app, request.clone()).await {
                                Ok(result) => {
                                    // Submit result back to server
                                    let _ = submit_tool_result_to_server(
                                        &config,
                                        request.thread_id,
                                        request.request_id,
                                        result,
                                    )
                                    .await;
                                }
                                Err(e) => {
                                    log::error!("Failed to handle tool request: {}", e);
                                    // Submit error result
                                    let _ = submit_tool_result_to_server(
                                        &config,
                                        request.thread_id,
                                        request.request_id,
                                        ToolResult {
                                            success: false,
                                            result: None,
                                            error: Some(e),
                                        },
                                    )
                                    .await;
                                }
                            }
                        }
                    }
                    Err(e) => {
                        log::debug!("Proxy polling error (may be expected if no pending): {}", e);
                    }
                }
            }

            // Poll every 2 seconds
            tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
        }
    });
}
