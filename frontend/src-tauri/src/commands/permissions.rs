/// Permission-related Tauri commands.
/// Handles accessibility and screen recording permission checks/prompts on macOS.

// ===== Accessibility =====

#[cfg(target_os = "macos")]
#[tauri::command]
pub fn check_accessibility_permission() -> bool {
    macos_accessibility_client::accessibility::application_is_trusted()
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
pub fn check_accessibility_permission() -> bool {
    true
}

#[cfg(target_os = "macos")]
#[tauri::command]
pub fn open_accessibility_settings() {
    if cfg!(debug_assertions) {
        println!("Requesting accessibility permission...");
    }
    // Force prompt first
    let result = macos_accessibility_client::accessibility::application_is_trusted_with_prompt();
    if cfg!(debug_assertions) {
        println!("Prompt result: {}", result);
    }

    if !result {
        if cfg!(debug_assertions) {
            println!("Permission not granted, opening system settings...");
        }
        let _ = std::process::Command::new("open")
            .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
            .spawn();
    }
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
pub fn open_accessibility_settings() {}

// ===== Screen Recording =====

#[cfg(target_os = "macos")]
#[tauri::command]
pub async fn check_screen_recording_permission() -> bool {
    use std::process::{Command, Stdio};
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    // Use a more stable directory in user home instead of system temp_dir
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    let temp_dir = std::path::PathBuf::from(home).join(".evoloop").join("temp");

    if let Err(e) = fs::create_dir_all(&temp_dir) {
        if cfg!(debug_assertions) {
            println!("[PermissionCheck] Failed to create temp dir: {}", e);
        }
    }

    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_millis();
    let temp_file = temp_dir.join(format!("evoloop_perm_check_{}.png", now));
    let temp_file_str = temp_file.to_str().unwrap_or("/tmp/evoloop_perm_check.png");

    if cfg!(debug_assertions) {
        println!("[PermissionCheck] Testing screen recording via screencapture to {}...", temp_file_str);
    }

    // Try to capture a tiny 1x1 area
    let status = Command::new("/usr/sbin/screencapture")
        .args(["-x", "-R0,0,1,1", "-t", "png", temp_file_str])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    match status {
        Ok(s) => {
            if s.success() && temp_file.exists() {
                let metadata = std::fs::metadata(&temp_file);
                let has_data = metadata.map(|m| m.len() > 0).unwrap_or(false);
                if cfg!(debug_assertions) {
                    println!("[PermissionCheck] screencapture success. File size > 0: {}", has_data);
                }
                // Clean up
                let _ = std::fs::remove_file(&temp_file);
                has_data
            } else {
                if cfg!(debug_assertions) {
                    println!("[PermissionCheck] screencapture failed or file not created. Status: {:?}", s);
                }
                false
            }
        }
        Err(e) => {
            if cfg!(debug_assertions) {
                println!("[PermissionCheck] screencapture command failed to start: {}", e);
            }
            false
        }
    }
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
pub async fn check_screen_recording_permission() -> bool {
    true
}

#[cfg(target_os = "macos")]
#[tauri::command]
pub fn open_screen_recording_settings() {
    if cfg!(debug_assertions) {
        println!("Opening screen recording privacy settings...");
    }
    let _ = std::process::Command::new("open")
        .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        .spawn();
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
pub fn open_screen_recording_settings() {}
