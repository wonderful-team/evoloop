use active_win_pos_rs::get_active_window;
use tauri::command;

#[derive(Debug, Clone, serde::Serialize)]
pub struct WindowBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// Get the bounds of the active window by title.
/// Uses active-win-pos-rs (macOS Accessibility API) instead of AppleScript,
/// reducing latency from ~100-200ms to <1ms.
#[command]
#[cfg(desktop)]
pub async fn get_window_bounds_by_title(title: String) -> Result<WindowBounds, String> {
    let win = get_active_window().map_err(|_| "No active window found".to_string())?;

    if !title.is_empty() && !win.title.to_lowercase().contains(&title.to_lowercase()) {
        return Err(format!("Window '{}' not found (current: '{}')", title, win.title));
    }

    Ok(WindowBounds {
        x: win.position.x,
        y: win.position.y,
        width: win.position.width,
        height: win.position.height,
    })
}

/// Get the bounds of the EvoLoop Mirror window for a specific device
#[command]
#[cfg(desktop)]
pub async fn get_mirror_window_bounds(device_id: String) -> Result<WindowBounds, String> {
    let title = format!("EvoLoop Mirror - {}", device_id);
    get_window_bounds_by_title(title).await
}
