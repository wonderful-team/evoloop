//! Tauri commands for Sidecar Client interaction

use serde::Deserialize;
use tauri::{command, AppHandle, Manager, State};

use crate::AppServiceState;

/// Execute a tool through the Sidecar Client
#[command]
pub async fn sidecar_execute_tool(
    state: State<'_, AppServiceState>,
    tool: String,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let client_opt = {
        let lock = state.sidecar_client.lock().map_err(|e| format!("Lock error: {}", e))?;
        lock.clone()
    };

    if let Some(client) = client_opt {
        client.execute_tool(&tool, params).await
    } else {
        Err("Sidecar Client not initialized".to_string())
    }
}

/// Check if Sidecar Client is ready
#[command]
pub fn sidecar_is_ready(state: State<'_, AppServiceState>) -> bool {
    if let Ok(client) = state.sidecar_client.lock() {
        if let Some(ref c) = *client {
            return c.is_ready();
        }
    }
    false
}

/// Get Sidecar Client status
#[command]
pub async fn sidecar_get_status(
    state: State<'_, AppServiceState>,
) -> Result<serde_json::Value, String> {
    let is_ready = sidecar_is_ready(state);

    Ok(serde_json::json!({
        "ready": is_ready,
        "status": if is_ready { "ready" } else { "initializing" }
    }))
}

/// Read file through Sidecar Client
#[command]
pub async fn sidecar_read_file(
    state: State<'_, AppServiceState>,
    path: String,
) -> Result<String, String> {
    let client_opt = {
        let lock = state.sidecar_client.lock().map_err(|e| format!("Lock error: {}", e))?;
        lock.clone()
    };

    if let Some(client) = client_opt {
        let result = client
            .execute_tool("file_read", serde_json::json!({"path": path}))
            .await?;

        match result {
            serde_json::Value::String(content) => Ok(content),
            _ => Err("Unexpected response format".to_string()),
        }
    } else {
        Err("Sidecar Client not initialized".to_string())
    }
}

/// Write file through Sidecar Client
#[command]
pub async fn sidecar_write_file(
    state: State<'_, AppServiceState>,
    path: String,
    content: String,
) -> Result<(), String> {
    let client_opt = {
        let lock = state.sidecar_client.lock().map_err(|e| format!("Lock error: {}", e))?;
        lock.clone()
    };

    if let Some(client) = client_opt {
        client
            .execute_tool(
                "file_write",
                serde_json::json!({
                    "path": path,
                    "content": content
                }),
            )
            .await?;
        Ok(())
    } else {
        Err("Sidecar Client not initialized".to_string())
    }
}

/// Execute shell command through Sidecar Client
#[command]
pub async fn sidecar_shell(
    state: State<'_, AppServiceState>,
    command: String,
    #[allow(unused_variables)]
    cwd: Option<String>,
    timeout: Option<u64>,
) -> Result<serde_json::Value, String> {
    let client_opt = {
        let lock = state.sidecar_client.lock().map_err(|e| format!("Lock error: {}", e))?;
        lock.clone()
    };

    if let Some(client) = client_opt {
        let mut params = serde_json::json!({
            "command": command,
        });

        if let Some(cwd) = cwd {
            params["cwd"] = serde_json::json!(cwd);
        }

        if let Some(timeout) = timeout {
            params["timeout"] = serde_json::json!(timeout);
        }

        client.execute_tool("shell", params).await
    } else {
        Err("Sidecar Client not initialized".to_string())
    }
}

/// List directory through Sidecar Client
#[command]
pub async fn sidecar_list_dir(
    state: State<'_, AppServiceState>,
    path: String,
) -> Result<serde_json::Value, String> {
    let client_opt = {
        let lock = state.sidecar_client.lock().map_err(|e| format!("Lock error: {}", e))?;
        lock.clone()
    };

    if let Some(client) = client_opt {
        client
            .execute_tool("file_list", serde_json::json!({"path": path}))
            .await
    } else {
        Err("Sidecar Client not initialized".to_string())
    }
}

/// Initialize Sidecar Client with workspace
#[command]
pub async fn sidecar_init(
    state: State<'_, AppServiceState>,
    workspace_root: Option<String>,
) -> Result<serde_json::Value, String> {
    let client_opt = {
        let lock = state.sidecar_client.lock().map_err(|e| format!("Lock error: {}", e))?;
        lock.clone()
    };

    if let Some(client) = client_opt {
        use crate::sidecar::ToClientMessage;

        let response = client
            .request(ToClientMessage::Init {
                id: "init-1".to_string(),
                workspace_root,
                config: None,
            })
            .await?;

        if let Some(error) = response.error {
            Err(error)
        } else {
            Ok(response.result.unwrap_or(serde_json::Value::Null))
        }
    } else {
        Err("Sidecar Client not initialized".to_string())
    }
}

/// Restart the Sidecar Client
#[command]
pub async fn sidecar_restart(app: AppHandle) -> Result<(), String> {
    let state = Manager::state::<AppServiceState>(&app);

    // Stop existing client
    {
        let mut client_guard = state.sidecar_client.lock().unwrap();
        if let Some(client) = client_guard.take() {
            let client: crate::sidecar::SidecarClient = client;
            let _: Result<(), String> = client.stop();
        }
    }

    // Start new client
    let mut new_client = crate::sidecar::SidecarClient::new();
    match new_client.start(&app, None) {
        Ok(_) => {
            *state.sidecar_client.lock().unwrap() = Some(new_client);

            // Wait for ready
            let client_arc = state.sidecar_client.clone();
            tauri::async_runtime::spawn(async move {
                let client_opt = {
                    let lock = client_arc.lock().unwrap();
                    lock.clone()
                };

                if let Some(client) = client_opt {
                    let client: crate::sidecar::SidecarClient = client;
                    match client.wait_for_ready(30).await {
                        Ok(_) => {
                            log::info!("Client restarted successfully");
                            let _ = tauri::Emitter::emit(&app, "client-ready", ());
                        }
                        Err(e) => {
                            log::error!("Client failed to restart: {}", e);
                            let _ = tauri::Emitter::emit(&app, "client-error", e);
                        }
                    }
                }
            });

            Ok(())
        }
        Err(e) => Err(e),
    }
}
