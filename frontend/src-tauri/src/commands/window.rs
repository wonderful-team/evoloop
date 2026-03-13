use tauri::command;

#[derive(Debug, Clone, serde::Serialize)]
pub struct WindowBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// Get the bounds of a window by its title
#[command]
#[cfg(desktop)]
pub async fn get_window_bounds_by_title(title: String) -> Result<WindowBounds, String> {
    #[cfg(target_os = "macos")]
    {
        get_window_bounds_macos(title).await
    }
    #[cfg(not(target_os = "macos"))]
    {
        Err("Window bounds detection is only supported on macOS".to_string())
    }
}

#[cfg(target_os = "macos")]
async fn get_window_bounds_macos(title: String) -> Result<WindowBounds, String> {
    // Use AppleScript to find the window by title and get its bounds
    // The window title should contain the provided string
    let script = format!(
        r#"
        tell application "System Events"
            set targetWindow to null
            repeat with proc in (get processes whose background only is false)
                try
                    repeat with win in (get windows of proc)
                        set winName to name of win as string
                        if winName contains "{}" then
                            set targetWindow to win
                            exit repeat
                        end if
                    end repeat
                    if targetWindow is not null then exit repeat
                end try
            end repeat

            if targetWindow is null then
                return "NOT_FOUND"
            end if

            set winPos to position of targetWindow
            set winSize to size of targetWindow
            return (item 1 of winPos as string) & "," & (item 2 of winPos as string) & "," & (item 1 of winSize as string) & "," & (item 2 of winSize as string)
        end tell
        "#,
        title.replace("\"", "\\\"")
    );

    let output = std::process::Command::new("osascript")
        .arg("-e")
        .arg(&script)
        .output()
        .map_err(|e| format!("Failed to execute AppleScript: {}", e))?;

    let result = String::from_utf8_lossy(&output.stdout).trim().to_string();

    if result == "NOT_FOUND" {
        return Err("Window not found".to_string());
    }

    // Parse the result: "x,y,width,height"
    let parts: Vec<&str> = result.split(',').collect();
    if parts.len() != 4 {
        return Err(format!("Unexpected AppleScript output: {}", result));
    }

    let x = parts[0].parse::<f64>().map_err(|e| format!("Failed to parse x: {}", e))?;
    let y = parts[1].parse::<f64>().map_err(|e| format!("Failed to parse y: {}", e))?;
    let width = parts[2].parse::<f64>().map_err(|e| format!("Failed to parse width: {}", e))?;
    let height = parts[3].parse::<f64>().map_err(|e| format!("Failed to parse height: {}", e))?;

    Ok(WindowBounds {
        x,
        y,
        width,
        height,
    })
}

/// Get the bounds of the EvoLoop Mirror window for a specific device
#[command]
#[cfg(desktop)]
pub async fn get_mirror_window_bounds(device_id: String) -> Result<WindowBounds, String> {
    let title = format!("EvoLoop Mirror - {}", device_id);
    get_window_bounds_by_title(title).await
}
