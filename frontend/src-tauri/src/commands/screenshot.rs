/// capture_screenshot
/// Captures the primary monitor and returns a base64-encoded PNG data URL.

#[tauri::command]
#[cfg(desktop)]
pub async fn capture_screenshot() -> Result<String, String> {
    use std::io::Cursor;
    use base64::Engine as _;

    // Get primary monitor
    let monitors = xcap::Monitor::all().map_err(|e| e.to_string())?;
    let monitor = monitors.first().ok_or("No monitor found")?;

    // Capture image
    let image = monitor.capture_image().map_err(|e| e.to_string())?;

    // Convert to PNG bytes
    let mut bytes: Vec<u8> = Vec::new();
    image
        .write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Png)
        .map_err(|e| e.to_string())?;

    // Encode to base64
    let base64_string = base64::engine::general_purpose::STANDARD.encode(&bytes);

    Ok(format!("data:image/png;base64,{}", base64_string))
}

#[tauri::command]
#[cfg(mobile)]
pub async fn capture_screenshot() -> Result<String, String> {
    Err("Screen capture is not supported on mobile.".to_string())
}
