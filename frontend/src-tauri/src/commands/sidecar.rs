//! Tauri commands for Backend management (Sidecar mode)

use tauri::{command, AppHandle, Manager, State};

use crate::sidecar::BACKEND_PORT;
use crate::AppServiceState;

/// Get Backend URL (for Frontend to use)
#[command]
pub fn backend_get_url() -> Result<String, String> {
    Ok(crate::sidecar::get_backend_url())
}

/// Check if Backend is ready
#[command]
pub fn sidecar_is_ready(state: State<'_, AppServiceState>) -> bool {
    if let Ok(client) = state.sidecar_client.lock() {
        if let Some(ref c) = *client {
            return c.is_ready();
        }
    }
    false
}

/// Get Backend status
#[command]
pub async fn sidecar_get_status(
    state: State<'_, AppServiceState>,
) -> Result<serde_json::Value, String> {
    let (is_ready, port) = if let Ok(client) = state.sidecar_client.lock() {
        let ready = client.as_ref().map(|c| c.is_ready()).unwrap_or(false);
        let port = client.as_ref().and_then(|c| c.get_port());
        (ready, port)
    } else {
        (false, None)
    };

    Ok(serde_json::json!({
        "ready": is_ready,
        "port": port,
        "url": port.map(|p| format!("http://127.0.0.1:{}", p)),
        "status": if is_ready { "ready" } else { "initializing" }
    }))
}

/// Restart the Backend
#[command]
pub async fn sidecar_restart(app: AppHandle) -> Result<(), String> {
    let state = Manager::state::<AppServiceState>(&app);

    // Stop existing backend
    {
        let mut client_guard = state.sidecar_client.lock().unwrap();
        if let Some(client) = client_guard.take() {
            let _: Result<(), String> = client.stop();
        }
    }

    // Start new backend
    let mut new_client = crate::sidecar::SidecarClient::new();
    match new_client.start(&app, None) {
        Ok(()) => {
            *state.sidecar_client.lock().unwrap() = Some(new_client);

            // Wait for ready
            let client_arc = state.sidecar_client.clone();
            let app_handle = app.clone();
            tauri::async_runtime::spawn(async move {
                let client_opt = {
                    let lock = client_arc.lock().unwrap();
                    lock.clone()
                };

                if let Some(client) = client_opt {
                    match client.wait_for_ready(30).await {
                        Ok(_) => {
                            log::info!("Backend restarted successfully on port {}", BACKEND_PORT);
                            let _ = tauri::Emitter::emit(&app_handle, "backend-ready", crate::sidecar::get_backend_url());
                        }
                        Err(e) => {
                            log::error!("Backend failed to restart: {}", e);
                            let _ = tauri::Emitter::emit(&app_handle, "backend-error", e);
                        }
                    }
                }
            });

            Ok(())
        }
        Err(e) => Err(e),
    }
}
