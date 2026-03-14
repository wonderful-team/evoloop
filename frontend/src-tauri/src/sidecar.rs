use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::Write;
use std::process::{ChildStdin, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Manager};
use tokio::sync::{mpsc, oneshot};

/// Message from Tauri to Client
#[derive(Debug, Serialize, Clone)]
#[serde(tag = "type")]
#[serde(rename_all = "snake_case")]
pub enum ToClientMessage {
    Execute {
        id: String,
        tool: String,
        params: serde_json::Value,
    },
    Ping {
        id: String,
    },
    Init {
        id: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        workspace_root: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        config: Option<serde_json::Value>,
    },
    Shutdown {
        #[serde(skip_serializing_if = "Option::is_none")]
        id: Option<String>,
    },
    Status {
        id: String,
    },
}

/// Message from Client to Tauri
#[derive(Debug, Deserialize, Clone)]
#[serde(tag = "type")]
#[serde(rename_all = "snake_case")]
pub enum FromClientMessage {
    Result {
        id: Option<String>,
        #[serde(default)]
        result: Option<serde_json::Value>,
        #[serde(default)]
        error: Option<String>,
        #[serde(flatten)]
        extra: HashMap<String, serde_json::Value>,
    },
    Event {
        event: String,
        #[serde(flatten)]
        data: HashMap<String, serde_json::Value>,
    },
    Error {
        #[serde(default)]
        error: Option<String>,
        #[serde(flatten)]
        extra: HashMap<String, serde_json::Value>,
    },
}

/// Response from Client
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientResponse {
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
}

/// Event from Client
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientEvent {
    pub event_type: String,
    pub data: HashMap<String, serde_json::Value>,
}

/// Sidecar client managing the Python process
pub struct SidecarClient {
    pub process: Arc<Mutex<Option<std::process::Child>>>,
    pub stdin: Arc<Mutex<Option<ChildStdin>>>,
    pub ready: Arc<Mutex<bool>>,
    pub pending_requests: Arc<Mutex<HashMap<String, oneshot::Sender<ClientResponse>>>>,
    pub event_tx: Option<mpsc::UnboundedSender<ClientEvent>>,
    pub app_handle: Option<AppHandle>,
}

impl SidecarClient {
    pub fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
            stdin: Arc::new(Mutex::new(None)),
            ready: Arc::new(Mutex::new(false)),
            pending_requests: Arc::new(Mutex::new(HashMap::new())),
            event_tx: None,
            app_handle: None,
        }
    }

    /// Start the sidecar Python process
    pub fn start(&mut self, app: &AppHandle, python_path: Option<&str>) -> Result<(), String> {
        let mut child = if cfg!(debug_assertions) {
            // Development: use Python source in evoloop/client
            let client_dir = get_client_dir(app)?;
            
            // Try to find python in .venv
            let venv_python = client_dir.join(".venv").join("bin").join("python3");
            let python_exe = if venv_python.exists() {
                venv_python.to_string_lossy().to_string()
            } else {
                "python3".to_string()
            };

            log::info!("Starting Python sidecar from: {} using {}", client_dir.display(), python_exe);
            
            std::process::Command::new(&python_exe)
                .args(&["-m", "app.main"])
                .current_dir(&client_dir)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|e| format!("Failed to spawn Python client: {}", e))?
        } else {
            // Production: use bundled sidecar binary
            let sidecar_name = "evoloop-client";

            // Get platform-specific triple
            #[cfg(target_os = "macos")]
            let triple = if cfg!(target_arch = "aarch64") { "aarch64-apple-darwin" } else { "x86_64-apple-darwin" };
            #[cfg(target_os = "windows")]
            let triple = if cfg!(target_arch = "x86_64") { "x86_64-pc-windows-msvc" } else { "aarch64-pc-windows-msvc" };
            #[cfg(target_os = "linux")]
            let triple = if cfg!(target_arch = "x86_64") { "x86_64-unknown-linux-gnu" } else { "aarch64-unknown-linux-gnu" };

            let binary_name = format!("{}-{}", sidecar_name, triple);
            #[cfg(target_os = "windows")]
            let binary_name = format!("{}.exe", binary_name);

            // Resolve sidecar path. In Tauri v2, they are in the resource dir under 'binaries'
            // or directly in MacOS folder. resolve_resource is the safest.
            let binary_path = app.path()
                .resolve(format!("binaries/{}", binary_name), tauri::path::BaseDirectory::Resource)
                .map_err(|e| format!("Failed to resolve sidecar path: {}", e))?;

            log::info!("Starting Client sidecar (Production/Binary) from: {}", binary_path.display());

            std::process::Command::new(binary_path)
                .arg("api")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|e| format!("Failed to spawn sidecar binary: {}", e))?
        };

        // Take stdin for writing
        let stdin = child.stdin.take().ok_or("Failed to get stdin")?;
        *self.stdin.lock().unwrap() = Some(stdin);

        // Store process
        *self.process.lock().unwrap() = Some(child);
        self.app_handle = Some(app.clone());

        // Create event channel
        let (event_tx, mut event_rx) = mpsc::unbounded_channel::<ClientEvent>();
        self.event_tx = Some(event_tx.clone());

        // Start stdout reader thread
        let stdout = self
            .process
            .lock()
            .unwrap()
            .as_mut()
            .unwrap()
            .stdout
            .take()
            .ok_or("Failed to get stdout")?;

        let pending = self.pending_requests.clone();
        let ready_flag = self.ready.clone();
        let app_handle = app.clone();

        thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(stdout);

            for line in reader.lines() {
                match line {
                    Ok(text) => {
                        log::debug!("[CLIENT STDOUT] {}", text);

                        match serde_json::from_str::<FromClientMessage>(&text) {
                            Ok(msg) => {
                                handle_client_message_sync(
                                    msg,
                                    &pending,
                                    &ready_flag,
                                    &event_tx,
                                    &app_handle,
                                );
                            }
                            Err(e) => {
                                log::error!("Failed to parse client message: {}", e);
                            }
                        }
                    }
                    Err(e) => {
                        log::error!("Error reading from client stdout: {}", e);
                        break;
                    }
                }
            }

            log::info!("Client stdout reader thread ended");
        });

        // Start stderr reader thread
        let stderr = self
            .process
            .lock()
            .unwrap()
            .as_mut()
            .unwrap()
            .stderr
            .take()
            .ok_or("Failed to get stderr")?;

        let app_handle = app.clone();
        thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(stderr);

            for line in reader.lines() {
                if let Ok(text) = line {
                    log::error!("[CLIENT STDERR] {}", text);
                    let _ = tauri::Emitter::emit(&app_handle, "client-stderr", text);
                }
            }
        });

        // Event forwarding to frontend (async)
        let app_handle = app.clone();
        tauri::async_runtime::spawn(async move {
            while let Some(event) = event_rx.recv().await {
                let _ = tauri::Emitter::emit(&app_handle, "client-event", serde_json::json!({
                    "type": event.event_type,
                    "data": event.data,
                }));
            }
        });

        log::info!("Client sidecar started, waiting for ready event...");
        Ok(())
    }

    /// Wait for Client to be ready
    pub async fn wait_for_ready(&self, timeout_secs: u64) -> Result<(), String> {
        let start = std::time::Instant::now();
        let timeout = std::time::Duration::from_secs(timeout_secs);

        loop {
            if *self.ready.lock().unwrap() {
                log::info!("Client is ready!");
                return Ok(());
            }
            if start.elapsed() > timeout {
                return Err(format!("Timeout waiting for Client ready ({}s)", timeout_secs));
            }
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
        }
    }

    /// Send a message and wait for response
    pub async fn request(&self, msg: ToClientMessage) -> Result<ClientResponse, String> {
        let id = extract_id(&msg);

        let (tx, rx) = oneshot::channel::<ClientResponse>();
        self.pending_requests
            .lock()
            .unwrap()
            .insert(id.clone(), tx);

        // Serialize and send via stdin
        let json = serde_json::to_string(&msg).map_err(|e| e.to_string())?;
        self.send_raw(&json)?;

        // Wait for response
        match tokio::time::timeout(tokio::time::Duration::from_secs(60), rx).await {
            Ok(Ok(response)) => Ok(response),
            Ok(Err(_)) => Err("Response channel closed".to_string()),
            Err(_) => {
                self.pending_requests.lock().unwrap().remove(&id);
                Err("Request timeout".to_string())
            }
        }
    }

    /// Send a message without waiting for response
    pub fn send(&self, msg: ToClientMessage) -> Result<(), String> {
        let json = serde_json::to_string(&msg).map_err(|e| e.to_string())?;
        self.send_raw(&json)
    }

    /// Send raw JSON line to Client stdin
    fn send_raw(&self, json: &str) -> Result<(), String> {
        let mut stdin = self.stdin.lock().unwrap();
        if let Some(ref mut s) = *stdin {
            writeln!(s, "{}", json).map_err(|e| format!("Failed to write to stdin: {}", e))?;
            s.flush()
                .map_err(|e| format!("Failed to flush stdin: {}", e))?;
            log::debug!("[TAURI -> CLIENT] {}", json);
            Ok(())
        } else {
            Err("Client stdin not available".to_string())
        }
    }

    /// Stop the sidecar process
    pub fn stop(&self) -> Result<(), String> {
        log::info!("Stopping Client sidecar...");

        // Try graceful shutdown first
        let _ = self.send(ToClientMessage::Shutdown { id: None });

        // Give it a moment to shutdown gracefully
        std::thread::sleep(std::time::Duration::from_millis(500));

        // Kill if still running
        if let Some(mut child) = self.process.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }

        *self.ready.lock().unwrap() = false;
        log::info!("Client sidecar stopped");
        Ok(())
    }

    /// Check if Client is ready
    pub fn is_ready(&self) -> bool {
        *self.ready.lock().unwrap()
    }

    /// Execute a tool through the Client
    pub async fn execute_tool(
        &self,
        tool: &str,
        params: serde_json::Value,
    ) -> Result<serde_json::Value, String> {
        let id = format!("exec-{}", uuid::Uuid::new_v4());
        let response = self
            .request(ToClientMessage::Execute {
                id,
                tool: tool.to_string(),
                params,
            })
            .await?;

        if let Some(error) = response.error {
            Err(error)
        } else {
            Ok(response.result.unwrap_or(serde_json::Value::Null))
        }
    }
}

impl Clone for SidecarClient {
    fn clone(&self) -> Self {
        Self {
            process: self.process.clone(),
            stdin: self.stdin.clone(),
            ready: self.ready.clone(),
            pending_requests: self.pending_requests.clone(),
            event_tx: self.event_tx.clone(),
            app_handle: self.app_handle.clone(),
        }
    }
}

impl Default for SidecarClient {
    fn default() -> Self {
        Self::new()
    }
}

/// Handle messages from Client (sync version for reader thread)
fn handle_client_message_sync(
    msg: FromClientMessage,
    pending: &Arc<Mutex<HashMap<String, oneshot::Sender<ClientResponse>>>>,
    ready: &Arc<Mutex<bool>>,
    event_tx: &mpsc::UnboundedSender<ClientEvent>,
    app: &AppHandle,
) {
    match msg {
        FromClientMessage::Result { id, result, error, .. } => {
            if let Some(request_id) = id {
                if let Some(sender) = pending.lock().unwrap().remove(&request_id) {
                    let _ = sender.send(ClientResponse { result, error });
                }
            }
        }
        FromClientMessage::Event { event, data } => {
            // Set ready flag on ready event
            if event == "ready" {
                *ready.lock().unwrap() = true;
                log::info!("Client reported ready: {:?}", data);
            }

            // Forward to event channel
            let _ = event_tx.send(ClientEvent {
                event_type: event.clone(),
                data: data.clone(),
            });

            // Emit to frontend
            let _ = tauri::Emitter::emit(app, "client-event", serde_json::json!({
                "type": event,
                "data": data,
            }));
        }
        FromClientMessage::Error { error, .. } => {
            log::error!("Client error: {:?}", error);
            let _ = tauri::Emitter::emit(app, "client-error", error);
        }
    }
}

/// Extract ID from message
fn extract_id(msg: &ToClientMessage) -> String {
    match msg {
        ToClientMessage::Execute { id, .. } => id.clone(),
        ToClientMessage::Ping { id } => id.clone(),
        ToClientMessage::Init { id, .. } => id.clone(),
        ToClientMessage::Shutdown { id, .. } => {
            id.clone().unwrap_or_else(|| "shutdown".to_string())
        }
        ToClientMessage::Status { id } => id.clone(),
    }
}

fn get_client_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    // 1. In development, we want the actual source client directory
    if cfg!(debug_assertions) {
        if let Ok(exe_path) = std::env::current_exe() {
            let mut curr = exe_path.as_path();
            // Traverse up from target/debug/EvoLoop to find the project root
            while let Some(parent) = curr.parent() {
                // Skip anything inside "target"
                if parent.to_string_lossy().contains("/target/") || parent.to_string_lossy().ends_with("/target") {
                    curr = parent;
                    continue;
                }
                let client_path = parent.join("client");
                if client_path.is_dir() && client_path.join("app").is_dir() {
                    return Ok(client_path);
                }
                curr = parent;
                // Don't go above root
                if parent.parent().is_none() { break; }
            }
        }
    }

    // 2. Check if client is in app resources (Production or fallback for dev)
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("Failed to get resource dir: {}", e))?;

    let client_in_resources = resource_dir.join("client");
    if client_in_resources.exists() {
        return Ok(client_in_resources);
    }

    // 3. Fallback: assume client is in current working directory
    let cwd_client = std::env::current_dir()
        .map_err(|e| format!("Failed to get cwd: {}", e))?
        .join("client");

    if cwd_client.exists() {
        return Ok(cwd_client);
    }

    Err(format!("Could not find client directory. Tried resources and traversing up from executable."))
}

/// Managed state for the sidecar
pub struct SidecarState {
    pub client: Arc<tokio::sync::Mutex<SidecarClient>>,
}

impl SidecarState {
    pub fn new() -> Self {
        Self {
            client: Arc::new(tokio::sync::Mutex::new(SidecarClient::new())),
        }
    }
}

impl Default for SidecarState {
    fn default() -> Self {
        Self::new()
    }
}
