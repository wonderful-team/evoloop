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
    pub position: Option<(i32, i32)>,
    pub window_title: Option<String>,
    pub app_name: Option<String>,
    pub process_id: Option<u64>,
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
        // In dev mode (and prod if bundled correctly), it should be in the same folder as the main executable.
        let exe_path = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("recorder"));
        let mut cmd_path = exe_path.clone();
        cmd_path.pop(); // Remove executable name
        cmd_path.push("recorder"); // Add recorder binary name

        // Run the recorder binary directly.
        // In dev mode (and prod if bundled correctly), it should be in the same folder as the main executable.
        let exe_path = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("recorder"));
        let mut cmd_path = exe_path.clone();
        cmd_path.pop(); // Remove executable name
        cmd_path.push("recorder"); // Add recorder binary name

        if !cmd_path.exists() {
             // Valid for dev mode where CWD is src-tauri
             cmd_path = std::path::PathBuf::from("./target/debug/recorder");
             if !cmd_path.exists() {
                  if let Ok(cwd) = std::env::current_dir() {
                      cmd_path = cwd.join("target/debug/recorder");
                  }
             }
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
        println!("Stop global recording requested");
        let mut child_lock = self.child.lock().unwrap();
        if let Some(mut child) = child_lock.take() {
            let _ = child.kill();
            let _ = child.wait(); // Prevent zombie
            println!("Recorder process killed");
        }
    }

    pub fn is_recording(&self) -> bool {
        let child_lock = self.child.lock().unwrap();
        child_lock.is_some()
    }
}
