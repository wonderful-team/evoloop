use std::io::{BufRead, BufReader};
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

/// Backend Manager - Manages the Python Backend process lifecycle
///
/// Responsibilities:
/// - Start Backend HTTP Server (using fixed port 8000)
/// - Monitor Backend health via HTTP
/// - Provide port to Frontend
pub struct SidecarClient {
    pub process: Arc<Mutex<Option<std::process::Child>>>,
    pub ready: Arc<Mutex<bool>>,
    pub app_handle: Option<AppHandle>,
}

/// Default Backend port
pub const BACKEND_PORT: u16 = 8000;

/// Default Backend URL
pub fn get_backend_url() -> String {
    format!("http://127.0.0.1:{}", BACKEND_PORT)
}

impl SidecarClient {
    pub fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
            ready: Arc::new(Mutex::new(false)),
            app_handle: None,
        }
    }

    /// Start the Backend HTTP Server (fixed port 8000)
    pub fn start(&mut self, app: &AppHandle, _python_path: Option<&str>) -> Result<(), String> {
        let backend_dir = get_backend_dir(app)?;

        // Try to find python in .venv
        let venv_python = backend_dir.join(".venv").join("bin").join("python3");
        let python_exe = if venv_python.exists() {
            venv_python.to_string_lossy().to_string()
        } else {
            "python3".to_string()
        };

        log::info!(
            "Starting Backend from: {} using {} on port {}",
            backend_dir.display(),
            python_exe,
            BACKEND_PORT
        );

        let child = std::process::Command::new(&python_exe)
            .args(&["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", &BACKEND_PORT.to_string()])
            .current_dir(&backend_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to spawn Backend: {}", e))?;

        // Store process
        *self.process.lock().unwrap() = Some(child);
        self.app_handle = Some(app.clone());

        // Start stdout reader thread (for logging)
        let stdout = self
            .process
            .lock()
            .unwrap()
            .as_mut()
            .unwrap()
            .stdout
            .take()
            .ok_or("Failed to get stdout")?;

        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(text) = line {
                    log::debug!("[BACKEND STDOUT] {}", text);
                }
            }
        });

        // Start stderr reader thread (for logging)
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
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(text) = line {
                    log::error!("[BACKEND STDERR] {}", text);
                    let _ = app_handle.emit("backend-stderr", text);
                }
            }
        });

        // Wait for Backend to be ready via HTTP health check
        let app_handle = app.clone();
        tauri::async_runtime::spawn(async move {
            let client = reqwest::Client::new();
            let health_url = format!("{}/api/v1/system/health", get_backend_url());

            // Try for 30 seconds
            for _ in 0..60 {
                match client.get(&health_url).timeout(Duration::from_secs(2)).send().await {
                    Ok(response) if response.status().is_success() => {
                        log::info!("Backend is ready on port {}", BACKEND_PORT);
                        let _ = app_handle.emit("backend-ready", get_backend_url());
                        return;
                    }
                    _ => {
                        tokio::time::sleep(Duration::from_millis(500)).await;
                    }
                }
            }

            log::error!("Backend failed to become ready within 30 seconds");
            let _ = app_handle.emit("backend-error", "Timeout waiting for Backend to start");
        });

        // Mark as started (not necessarily ready yet)
        *self.ready.lock().unwrap() = true;
        log::info!("Backend process started, waiting for HTTP readiness...");
        Ok(())
    }

    /// Wait for Backend to be ready
    pub async fn wait_for_ready(&self, timeout_secs: u64) -> Result<(), String> {
        let start = std::time::Instant::now();
        let timeout = std::time::Duration::from_secs(timeout_secs);

        let client = reqwest::Client::new();
        let health_url = format!("{}/api/v1/system/health", get_backend_url());

        loop {
            if start.elapsed() > timeout {
                return Err(format!(
                    "Timeout waiting for Backend ready ({}s)",
                    timeout_secs
                ));
            }

            match client.get(&health_url).timeout(Duration::from_secs(2)).send().await {
                Ok(response) if response.status().is_success() => {
                    return Ok(());
                }
                _ => {
                    tokio::time::sleep(Duration::from_millis(100)).await;
                }
            }
        }
    }

    /// Stop the Backend process
    pub fn stop(&self) -> Result<(), String> {
        log::info!("Stopping Backend...");

        if let Some(mut child) = self.process.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }

        *self.ready.lock().unwrap() = false;
        log::info!("Backend stopped");
        Ok(())
    }

    /// Check if Backend is ready (quick check, not HTTP)
    pub fn is_ready(&self) -> bool {
        *self.ready.lock().unwrap()
    }

    /// Get Backend port (always 8000)
    pub fn get_port(&self) -> Option<u16> {
        if self.is_ready() {
            Some(BACKEND_PORT)
        } else {
            None
        }
    }

    /// Get Backend URL
    pub fn get_url(&self) -> Option<String> {
        if self.is_ready() {
            Some(get_backend_url())
        } else {
            None
        }
    }
}

impl Clone for SidecarClient {
    fn clone(&self) -> Self {
        Self {
            process: self.process.clone(),
            ready: self.ready.clone(),
            app_handle: self.app_handle.clone(),
        }
    }
}

impl Default for SidecarClient {
    fn default() -> Self {
        Self::new()
    }
}

fn get_backend_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    // 1. In development, we want the actual backend directory
    if cfg!(debug_assertions) {
        if let Ok(exe_path) = std::env::current_exe() {
            let mut curr = exe_path.as_path();
            // Traverse up from target/debug/EvoLoop to find the project root
            while let Some(parent) = curr.parent() {
                // Skip anything inside "target"
                if parent
                    .to_string_lossy()
                    .contains("/target/")
                    || parent.to_string_lossy().ends_with("/target")
                {
                    curr = parent;
                    continue;
                }
                let backend_path = parent.join("backend");
                if backend_path.is_dir() && backend_path.join("app").is_dir() {
                    return Ok(backend_path);
                }
                curr = parent;
                // Don't go above root
                if parent.parent().is_none() {
                    break;
                }
            }
        }
    }

    // 2. Check if backend is in app resources
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("Failed to get resource dir: {}", e))?;

    let backend_in_resources = resource_dir.join("backend-source");
    if backend_in_resources.exists() {
        return Ok(backend_in_resources);
    }

    // 3. Fallback: assume backend is in current working directory
    let cwd_backend = std::env::current_dir()
        .map_err(|e| format!("Failed to get cwd: {}", e))?
        .join("backend");

    if cwd_backend.exists() {
        return Ok(cwd_backend);
    }

    Err(format!(
        "Could not find backend directory. Tried resources and traversing from executable."
    ))
}
