use std::io::{BufRead, BufReader};
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

/// Backend state
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BackendState {
    Idle,
    Starting,
    Ready,
    Failed,
}

/// Check if a port is already in use
fn is_port_in_use(port: u16) -> bool {
    use std::net::TcpListener;
    TcpListener::bind(format!("127.0.0.1:{}", port)).is_err()
}

/// Kill any existing evoloop-backend process
fn kill_existing_backend() {
    #[cfg(unix)]
    {
        use std::process::Command;
        // Try graceful kill first
        let _ = Command::new("pkill")
            .args(["-15", "-f", "evoloop-backend"])
            .output();
        
        thread::sleep(Duration::from_millis(500));
        
        // Force kill if still running
        let _ = Command::new("pkill")
            .args(["-9", "-f", "evoloop-backend"])
            .output();
        
        // Wait for port release
        thread::sleep(Duration::from_millis(500));
    }
}

/// Backend Manager - Manages the Python Backend process lifecycle
pub struct SidecarClient {
    process: Arc<Mutex<Option<std::process::Child>>>,
    state: Arc<Mutex<BackendState>>,
    app_handle: Option<AppHandle>,
}

/// Default Backend port
/// 从环境变量 EVOLOOP_BACKEND_PORT 读取（通过 build.rs 注入，默认 20160）
/// 与 scripts/build/config.sh 保持一致
pub const BACKEND_PORT: u16 = {
    // env! 在编译时展开，build.rs 保证该变量始终存在
    let port_str = env!("EVOLOOP_BACKEND_PORT");
    // 编译时计算常量
    let bytes = port_str.as_bytes();
    let mut port: u16 = 0;
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] < b'0' || bytes[i] > b'9' {
            panic!("EVOLOOP_BACKEND_PORT must be a number");
        }
        port = port * 10 + (bytes[i] - b'0') as u16;
        i += 1;
    }
    port
};

/// Default Backend URL
pub fn get_backend_url() -> String {
    format!("http://127.0.0.1:{}", BACKEND_PORT)
}

impl SidecarClient {
    pub fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
            state: Arc::new(Mutex::new(BackendState::Idle)),
            app_handle: None,
        }
    }

    /// Get current state
    pub fn get_state(&self) -> BackendState {
        *self.state.lock().unwrap()
    }

    /// Check if Backend is ready
    pub fn is_ready(&self) -> bool {
        self.get_state() == BackendState::Ready
    }

    /// Start the Backend HTTP Server (fixed port 8000)
    pub fn start(&mut self, app: &AppHandle, _python_path: Option<&str>) -> Result<(), String> {
        // Development mode: skip sidecar start, assume dev server is running externally
        // Run with: ./bin/evo dev (in backend directory)
        if cfg!(debug_assertions) {
            log::info!("Development mode: skipping sidecar start, using external dev server");
            *self.state.lock().unwrap() = BackendState::Ready;
            let _ = app.emit("backend-ready", get_backend_url());
            return Ok(());
        }

        // Check current state
        {
            let state = self.state.lock().unwrap();
            if *state == BackendState::Starting || *state == BackendState::Ready {
                log::info!("Backend is already {:?}, skipping start", *state);
                return Ok(());
            }
        }

        // Set state to Starting
        *self.state.lock().unwrap() = BackendState::Starting;
        log::info!("Starting backend...");

        // Clean up any existing processes
        if is_port_in_use(BACKEND_PORT) {
            log::warn!("Port {} is in use, cleaning up...", BACKEND_PORT);
            kill_existing_backend();
        }

        // Double-check port is free
        if is_port_in_use(BACKEND_PORT) {
            let err = format!("Port {} is still in use after cleanup", BACKEND_PORT);
            log::error!("{}", err);
            *self.state.lock().unwrap() = BackendState::Failed;
            return Err(err);
        }

        // Spawn the process
        let child = self.spawn_backend(app)?;
        
        // Store process and app handle
        *self.process.lock().unwrap() = Some(child);
        self.app_handle = Some(app.clone());

        // Start log readers
        self.start_log_readers(app);

        // Start health check
        self.start_health_check(app);

        Ok(())
    }

    /// Spawn the backend process
    fn spawn_backend(&self, app: &AppHandle) -> Result<std::process::Child, String> {
        if cfg!(debug_assertions) {
            // Development mode
            let backend_dir = get_backend_dir(app)?;
            let venv_python = backend_dir.join(".venv").join("bin").join("python3");
            let python_exe = if venv_python.exists() {
                venv_python.to_string_lossy().to_string()
            } else {
                "python3".to_string()
            };

            log::info!("Starting Backend (dev) from: {}", backend_dir.display());

            std::process::Command::new(&python_exe)
                .args(&["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", &BACKEND_PORT.to_string()])
                .current_dir(&backend_dir)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|e| format!("Failed to spawn Backend: {}", e))
        } else {
            // Production mode
            let _exe_path = std::env::current_exe()
                .map_err(|e| format!("Failed to get current exe path: {}", e))?;
                
            #[cfg(target_os = "macos")]
            let sidecar_path = app.path().resource_dir()
                .map_err(|e| format!("Failed to get resource dir: {}", e))?
                .join("EvoLoop Backend.app")
                .join("Contents")
                .join("MacOS")
                .join("evoloop-backend");

            #[cfg(not(target_os = "macos"))]
            let sidecar_path = _exe_path
                .parent()
                .ok_or("Failed to get exe parent dir")?
                .join("evoloop-backend");

            log::info!("Starting sidecar from: {}", sidecar_path.display());

            // Get app directories (Aligning with Python backend's ~/.evoloop)
            let home_dir = dirs::home_dir().ok_or("Failed to get home dir")?;
            let app_data_dir = home_dir.join(".evoloop");
            let workspace_dir = app_data_dir.join("workspace");
            let db_path = app_data_dir.join("database").join("backend.db");

            // Bundled core models (action_classifier, domain_classifier, KWS) live inside
            // the Tauri app bundle under Resources/models/.
            let resource_dir = app.path().resource_dir()
                .map_err(|e| format!("Failed to get resource dir: {}", e))?;
            let bundled_models_dir = resource_dir.join("models");

            std::fs::create_dir_all(&workspace_dir).ok();
            std::fs::create_dir_all(app_data_dir.join("database")).ok();

            std::process::Command::new(&sidecar_path)
                .args(&["--host", "127.0.0.1", "--port", &BACKEND_PORT.to_string()])
                .env("EMBEDDED_MODE", "true")
                .env("WORKSPACE_ROOT", &workspace_dir)
                .env("SQLITE_DB_PATH", &db_path)
                .env("PROJECT_NAME", "EvoLoop")
                .env("MODELS_DIR", &bundled_models_dir)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|e| format!("Failed to spawn sidecar: {}", e))
        }
    }

    /// Start log reader threads
    fn start_log_readers(&self, _app: &AppHandle) {
        // Clone Arc for stdout thread
        let process_stdout = Arc::clone(&self.process);
        thread::spawn(move || {
            let stdout = {
                let mut guard = process_stdout.lock().unwrap();
                guard.as_mut().and_then(|c| c.stdout.take())
            };
            
            if let Some(stdout) = stdout {
                let reader = BufReader::new(stdout);
                for line in reader.lines() {
                    if let Ok(text) = line {
                        log::debug!("[BACKEND STDOUT] {}", text);
                    }
                }
            }
        });

        // Clone Arc for stderr thread
        let process_stderr = Arc::clone(&self.process);
        let app_handle = self.app_handle.clone();
        thread::spawn(move || {
            let stderr = {
                let mut guard = process_stderr.lock().unwrap();
                guard.as_mut().and_then(|c| c.stderr.take())
            };
            
            if let Some(stderr) = stderr {
                let reader = BufReader::new(stderr);
                for line in reader.lines() {
                    if let Ok(text) = line {
                        log::error!("[BACKEND STDERR] {}", text);
                        if let Some(ref app) = app_handle {
                            let _ = app.emit("backend-stderr", text);
                        }
                    }
                }
            }
        });
    }

    /// Start async health check
    fn start_health_check(&self, app: &AppHandle) {
        let state = Arc::clone(&self.state);
        let process = Arc::clone(&self.process);
        let app_handle = app.clone();

        tauri::async_runtime::spawn(async move {
            let client = reqwest::Client::new();
            let health_url = format!("{}/api/v1/system/health", get_backend_url());

            // Try for 30 seconds
            let mut success = false;
            for i in 0..60 {
                match client.get(&health_url).timeout(Duration::from_secs(2)).send().await {
                    Ok(response) if response.status().is_success() => {
                        log::info!("Backend is ready on port {}", BACKEND_PORT);
                        *state.lock().unwrap() = BackendState::Ready;
                        let _ = app_handle.emit("backend-ready", get_backend_url());
                        success = true;
                        break;
                    }
                    Ok(response) => {
                        log::debug!("Health check returned status: {}", response.status());
                    }
                    Err(e) => {
                        if i % 10 == 0 {
                            log::debug!("Health check attempt {} failed: {}", i, e);
                        }
                    }
                }
                tokio::time::sleep(Duration::from_millis(500)).await;
            }

            if !success {
                log::error!("Backend failed to become ready within 30 seconds");
                *state.lock().unwrap() = BackendState::Failed;
                let _ = app_handle.emit("backend-error", "Timeout waiting for Backend to start");
                
                // Clean up the failed process
                if let Some(mut child) = process.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
    }

    /// Wait for Backend to be ready
    pub async fn wait_for_ready(&self, timeout_secs: u64) -> Result<(), String> {
        let start = std::time::Instant::now();
        let timeout = std::time::Duration::from_secs(timeout_secs);

        loop {
            if start.elapsed() > timeout {
                return Err(format!("Timeout waiting for Backend ready ({}s)", timeout_secs));
            }

            match self.get_state() {
                BackendState::Ready => return Ok(()),
                BackendState::Failed => return Err("Backend failed to start".to_string()),
                _ => {}
            }

            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }

    /// Stop the Backend process
    pub fn stop(&self) -> Result<(), String> {
        log::info!("Stopping Backend...");

        // Update state first
        *self.state.lock().unwrap() = BackendState::Idle;

        let child_opt = self.process.lock().unwrap().take();
        if let Some(mut child) = child_opt {
            let pid = child.id();
            
            #[cfg(unix)]
            {
                use std::process::Command;
                // Try process group kill
                let pgid = -(pid as i32);
                crate::safe_killpg(pgid);
                crate::safe_kill(pid as i32);
                thread::sleep(Duration::from_millis(500));
                
                // Force kill
                let _ = Command::new("pkill")
                    .args(["-9", "-f", "evoloop-backend"])
                    .output();
            }
            
            let _ = child.kill();
            let _ = child.wait();
        }

        log::info!("Backend stopped");
        Ok(())
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
            process: Arc::clone(&self.process),
            state: Arc::clone(&self.state),
            app_handle: self.app_handle.clone(),
        }
    }
}

impl Default for SidecarClient {
    fn default() -> Self {
        Self::new()
    }
}

fn get_backend_dir(_app: &AppHandle) -> Result<std::path::PathBuf, String> {
    // Development mode only: find backend from project directory
    if let Ok(exe_path) = std::env::current_exe() {
        let mut curr = exe_path.as_path();
        while let Some(parent) = curr.parent() {
            if parent.to_string_lossy().contains("/target/")
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
            if parent.parent().is_none() {
                break;
            }
        }
    }

    let cwd_backend = std::env::current_dir()
        .map_err(|e| format!("Failed to get cwd: {}", e))?
        .join("backend");

    if cwd_backend.exists() {
        return Ok(cwd_backend);
    }

    Err("Could not find backend directory. For production builds, use the evoloop-backend binary.".to_string())
}
