use tauri::{AppHandle, Emitter};
use std::sync::{Arc, Mutex};
use serde::{Deserialize, Serialize};
use std::process::{Command, Stdio, Child};
use std::io::{BufRead, BufReader};
use std::thread;

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct GlobalEvent {
    pub timestamp: u64,
    pub event_type: String,
    pub key: Option<String>,
    pub mouse_button: Option<String>,
    pub position: Option<(f64, f64)>,
    pub window_title: Option<String>,
    pub app_name: Option<String>,
    pub process_id: Option<u64>,
    pub window_bounds: Option<(f64, f64, f64, f64)>,
}

pub struct GlobalObserver {
    child: Arc<Mutex<Option<Child>>>,
}

impl GlobalObserver {
    pub fn new() -> Self {
        Self {
            child: Arc::new(Mutex::new(None)),
        }
    }

    pub fn start(&self, app: AppHandle) {
        println!("GlobalObserver::start called");

        let mut child_lock = self.child.lock().unwrap();
        if child_lock.is_some() {
             println!("GlobalObserver already recording");
             return;
        }

        // Run the recorder binary directly.
        // Try multiple locations for development and production.
        let exe_path = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("recorder"));
        let mut cmd_path = std::path::PathBuf::new();

        // Helper to find target directory from executable path
        // In dev: target/debug/EvoLoop -> target/debug/recorder
        // In prod: EvoLoop.app/Contents/MacOS/EvoLoop -> EvoLoop.app/Contents/MacOS/recorder
        fn find_from_exe_dir(exe: &std::path::Path) -> Option<std::path::PathBuf> {
            let mut p = exe.to_path_buf();
            p.pop(); // Remove exe name
            p.push("recorder");
            if p.exists() { Some(p) } else { None }
        }

        fn find_in_target(exe: &std::path::Path, profile: &str) -> Option<std::path::PathBuf> {
            // Walk up to find target directory
            let mut p = exe.to_path_buf();
            while p.pop() {
                if p.file_name().map(|n| n == "target").unwrap_or(false) {
                    let mut recorder = p.clone();
                    recorder.push(profile);
                    recorder.push("recorder");
                    if recorder.exists() {
                        return Some(recorder);
                    }
                    break;
                }
            }
            None
        }

        // 1. Try same directory as main executable (works for both dev and prod)
        if let Some(p) = find_from_exe_dir(&exe_path) {
            cmd_path = p;
            println!("Found recorder at: {:?}", cmd_path);
        }

        // 2. Try target/debug/recorder (walking up from exe)
        if cmd_path.as_os_str().is_empty() {
            if let Some(p) = find_in_target(&exe_path, "debug") {
                cmd_path = p;
                println!("Found recorder in target/debug: {:?}", cmd_path);
            }
        }

        // 3. Try target/release/recorder
        if cmd_path.as_os_str().is_empty() {
            if let Some(p) = find_in_target(&exe_path, "release") {
                cmd_path = p;
                println!("Found recorder in target/release: {:?}", cmd_path);
            }
        }

        // 4. Try CWD-based paths (fallback)
        if cmd_path.as_os_str().is_empty() {
            if let Ok(cwd) = std::env::current_dir() {
                let candidates = [
                    cwd.join("target/debug/recorder"),
                    cwd.join("target/release/recorder"),
                    cwd.join("frontend/src-tauri/target/debug/recorder"),
                    cwd.join("frontend/src-tauri/target/release/recorder"),
                    cwd.join("src-tauri/target/debug/recorder"),
                    cwd.join("src-tauri/target/release/recorder"),
                ];
                for p in &candidates {
                    if p.exists() {
                        cmd_path = p.clone();
                        println!("Found recorder via CWD: {:?}", cmd_path);
                        break;
                    }
                }
            }
        }

        if cmd_path.as_os_str().is_empty() {
            eprintln!("ERROR: Could not find recorder binary. Checked:");
            eprintln!("  - Same dir as executable: {:?}", exe_path.parent());
            eprintln!("  - target/debug/recorder");
            eprintln!("  - target/release/recorder");
            eprintln!("");
            eprintln!("To build recorder, run:");
            eprintln!("  cd frontend/src-tauri && cargo build --bin recorder");
            return;
        }
        
        let mut cmd = Command::new(cmd_path);
        cmd.stdout(Stdio::piped())
           .stderr(Stdio::piped());

        println!("Spawning recorder process...");
        match cmd.spawn() {
            Ok(mut child) => {
                println!("Recorder process spawned successfully, pid: {}", child.id());
                
                if let Some(stdout) = child.stdout.take() {
                    let app_handle = app.clone();
                    thread::spawn(move || {
                        let reader = BufReader::new(stdout);
                        for line in reader.lines() {
                            match line {
                                Ok(l) => {
                                    if let Ok(event) = serde_json::from_str::<GlobalEvent>(&l) {
                                        if event.event_type.contains("click") || event.event_type.contains("press") {
                                            println!("[GlobalObserver] Emitting event: {}", event.event_type);
                                        }
                                        let _ = app_handle.emit("global-event", event);
                                    } else {
                                        println!("[Recorder] {}", l);
                                    }
                                }
                                Err(_) => break,
                            }
                        }
                    });
                }
                
                if let Some(stderr) = child.stderr.take() {
                     thread::spawn(move || {
                        let reader = BufReader::new(stderr);
                         for line in reader.lines() {
                             if let Ok(l) = line {
                                 eprintln!("[Recorder ERR] {}", l);
                             }
                         }
                     });
                }
                
                *child_lock = Some(child);
            },
            Err(e) => {
                println!("Failed to spawn recorder: {:?}", e);
            }
        }
    }

    pub fn stop(&self) {
        let mut child_lock = self.child.lock().unwrap();
        if let Some(mut child) = child_lock.take() {
            println!("Stop global recording - Killing process {}", child.id());
            let _ = child.kill();
            let _ = child.wait(); // Prevent zombie
        }
    }

    pub fn is_recording(&self) -> bool {
        let child_lock = self.child.lock().unwrap();
        child_lock.is_some()
    }
}
