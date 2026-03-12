/// Screen recording via ffmpeg (Two-Track Architecture).
/// Manages an ffmpeg child process for capturing screen video to ~/.evoloop/artifacts/recordings/.
///
/// AppServiceState fields used:
///   - recording_process: Arc<Mutex<Option<std::process::Child>>>
///   - recording_path:    Arc<Mutex<Option<String>>>

#[cfg(desktop)]
use crate::AppServiceState;

// ===== start_screen_recording =====

#[tauri::command]
#[cfg(desktop)]
pub async fn start_screen_recording(
    state: tauri::State<'_, AppServiceState>,
    _app: tauri::AppHandle,
) -> Result<String, String> {
    use std::process::{Command, Stdio};
    use std::fs;
    use std::io::{BufRead, BufReader};
    use std::thread;

    let mut proc_lock = state.recording_process.lock().unwrap();
    if proc_lock.is_some() {
        return Err("Screen recording already in progress".to_string());
    }

    // Use ~/.evoloop/artifacts/recordings for better visibility (Tauri AppData is hidden on macOS)
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    let recordings_dir = std::path::PathBuf::from(home).join(".evoloop").join("artifacts").join("recordings");

    fs::create_dir_all(&recordings_dir)
        .map_err(|e| format!("Failed to create recordings dir: {}", e))?;

    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_millis();
    let video_path = recordings_dir.join(format!("{}.mp4", timestamp));
    let video_path_str = video_path.to_string_lossy().to_string();

    println!("[ScreenRecorder] Attempting to start recording to: {}", video_path_str);

    // Using ffmpeg for more reliable background recording on macOS
    // -y: overwrite
    // -f avfoundation: input format
    // -i "0": main screen
    // -pix_fmt yuv420p: format for compatibility
    // -r 15: framerate
    // -c:v libx264: encoder
    // -preset ultrafast: minimize CPU impact
    // -tune zerolatency: for streaming-like capture
    println!("[ScreenRecorder] Launching ffmpeg recording...");

    let mut child = Command::new("/usr/local/bin/ffmpeg")
        .args([
            "-y",
            "-f", "avfoundation",
            "-capture_cursor", "1",
            "-framerate", "15",
            "-i", "0",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            &video_path_str,
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn /usr/local/bin/ffmpeg: {}", e))?;

    let pid = child.id();
    println!("[ScreenRecorder] ffmpeg process spawned with PID: {}", pid);

    // Capture stderr to see if it fails
    let stderr_capture = std::sync::Arc::new(std::sync::Mutex::new(String::new()));
    let stderr_capture_clone = stderr_capture.clone();

    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(l) = line {
                    // Filter out known benign AVFoundation warnings that contain 'failed'
                    let is_benign_warning = l.contains("Configuration of video device failed");

                    if (l.contains("Error") || l.contains("failed")) && !is_benign_warning {
                        eprintln!("[ffmpeg ERR] {}", l);
                    }
                    if let Ok(mut buffer) = stderr_capture_clone.lock() {
                        buffer.push_str(&l);
                        buffer.push('\n');
                    }
                }
            }
        });
    }

    // Wait for it to initialize
    thread::sleep(std::time::Duration::from_millis(1500));
    if let Ok(Some(status)) = child.try_wait() {
        let error_msg = if let Ok(buffer) = stderr_capture.lock() {
            format!("ffmpeg exited immediately with status: {}. Logs: {}", status, buffer)
        } else {
            format!("ffmpeg exited immediately with status: {}", status)
        };
        return Err(error_msg);
    }

    *proc_lock = Some(child);
    *state.recording_path.lock().unwrap() = Some(video_path_str.clone());

    // --- Record start time for tray timer (Set BEFORE sleep to avoid gap) ---
    *state.recording_start_time.lock().unwrap() = Some(std::time::Instant::now());

    // --- Watchdog: 10-minute hard limit + 500 MB size fuse ---
    {
        use std::sync::Arc;
        use std::sync::atomic::Ordering;
        use tauri::Emitter;

        let is_blinking_wdg = Arc::clone(&state.is_blinking);
        let proc_wdg        = Arc::clone(&state.recording_process);
        let start_time_wdg  = Arc::clone(&state.recording_start_time);
        let path_wdg        = video_path_str.clone();
        let app_wdg         = _app.clone();

        std::thread::spawn(move || {
            const MAX_SECS: u64  = 10 * 60;            // 10 minutes
            const MAX_BYTES: u64 = 500 * 1024 * 1024;  // 500 MB

            loop {
                std::thread::sleep(std::time::Duration::from_secs(30));

                // Recording already stopped manually — exit watchdog
                if !is_blinking_wdg.load(Ordering::Relaxed) {
                    break;
                }

                let elapsed = start_time_wdg.lock().unwrap()
                    .map(|t: std::time::Instant| t.elapsed().as_secs())
                    .unwrap_or(0);
                let size = std::fs::metadata(&path_wdg).map(|m| m.len()).unwrap_or(0);

                let reason: Option<&str> = if elapsed >= MAX_SECS {
                    Some("timeout")
                } else if size >= MAX_BYTES {
                    Some("size_limit")
                } else {
                    None
                };

                if let Some(r) = reason {
                    println!("[ScreenRecorder] Watchdog triggered: {}", r);
                    let mut lock = proc_wdg.lock().unwrap();
                    if let Some(mut child) = lock.take() {
                        #[cfg(unix)]
                        unsafe { libc::kill(child.id() as i32, libc::SIGINT); }
                        #[cfg(not(unix))]
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                    *start_time_wdg.lock().unwrap() = None;
                    is_blinking_wdg.store(false, Ordering::Relaxed);
                    let _ = app_wdg.emit("recording-auto-stopped", r);
                    break;
                }
            }
        });
    }

    Ok(video_path_str)
}

#[tauri::command]
#[cfg(mobile)]
pub async fn start_screen_recording() -> Result<String, String> {
    Err("Screen recording is not supported on mobile".to_string())
}

// ===== stop_screen_recording =====

#[tauri::command]
#[cfg(desktop)]
pub async fn stop_screen_recording(
    state: tauri::State<'_, AppServiceState>,
) -> Result<String, String> {
    let mut proc_lock = state.recording_process.lock().unwrap();
    let path_lock = state.recording_path.lock().unwrap();

    let video_path = path_lock.clone().unwrap_or_default();

    if let Some(mut child) = proc_lock.take() {
        // Send SIGINT (Ctrl+C) to gracefully stop ffmpeg and finalize the video file
        #[cfg(unix)]
        {
            let id = child.id();
            println!("[ScreenRecorder] Sending SIGINT to PID {}", id);
            unsafe {
                libc::kill(id as i32, libc::SIGINT);
            }
        }

        #[cfg(not(unix))]
        {
            let _ = child.kill();
        }

        // Wait for it to exit
        match child.wait() {
            Ok(status) => {
                println!("[ScreenRecorder] Process {} exited with status: {}", child.id(), status);

                // Verify if file exists and has size
                if let Ok(metadata) = std::fs::metadata(&video_path) {
                    println!("[ScreenRecorder] Final file size: {} bytes", metadata.len());
                    if metadata.len() < 1000 {
                        println!("[ScreenRecorder] WARNING: Video file is suspiciously small!");
                    }
                } else {
                    println!("[ScreenRecorder] ERROR: Video file NOT FOUND at exit!");
                }
            }
            Err(e) => println!("[ScreenRecorder] Error waiting for process: {}", e),
        }
        println!("[ScreenRecorder] Stopped recording: {}", video_path);
    } else {
        println!("[ScreenRecorder] stop_screen_recording called but no active process found");
        return Err("No screen recording in progress".to_string());
    }

    // Clear start time
    // Handled in sync_tray_recording_state for responsiveness, 
    // but also here for consistency.
    *state.recording_start_time.lock().unwrap() = None;

    Ok(video_path)
}

#[tauri::command]
#[cfg(mobile)]
pub async fn stop_screen_recording() -> Result<String, String> {
    Err("Screen recording is not supported on mobile".to_string())
}
