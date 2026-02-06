use rdev::{listen, Event, EventType};
use serde::Serialize;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[derive(Clone, Serialize, Debug)]
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

#[derive(Clone, Debug)]
struct WindowInfo {
    title: String,
    app_name: String,
    process_id: u64,
}

fn main() {
    println!("Recorder sidecar started");

    // Spawn window poller thread
    let (tx, rx) = std::sync::mpsc::channel();
    thread::spawn(move || {
        loop {
             let script = r#"
                tell application "System Events"
                    set frontApp to name of first application process whose frontmost is true
                    set windowTitle to ""
                    try
                        tell process frontApp to set windowTitle to name of window 1
                    end try
                    return frontApp & "|||" & windowTitle
                end tell
                "#;
                
                match std::process::Command::new("osascript")
                    .arg("-e")
                    .arg(script)
                    .output() 
                {
                    Ok(output) => {
                        if output.status.success() {
                            let result = String::from_utf8_lossy(&output.stdout);
                            let parts: Vec<&str> = result.trim().split("|||").collect();
                            if parts.len() >= 2 {
                                let info = WindowInfo {
                                    app_name: parts[0].to_string(),
                                    title: parts[1].to_string(),
                                    process_id: 0,
                                };
                                let _ = tx.send(info);
                            }
                        }
                    },
                    Err(_) => {}
                }
            thread::sleep(Duration::from_secs(2));
        }
    });

    // Main thread runs rdev listener (which blocks)
    // We need to access the latest window info.
    // Since listen callback is a closure, we need a shared state.
    // But rdev listen blocks the current thread.
    // So main thread = listener thread.
    // Window poller updates shared state.
    
    let window_info = std::sync::Arc::new(std::sync::Mutex::new(None::<WindowInfo>));
    let window_info_clone = window_info.clone();

    // Consumer of window updates
    thread::spawn(move || {
        while let Ok(info) = rx.recv() {
            *window_info_clone.lock().unwrap() = Some(info);
        }
    });

    let window_info_listener = window_info.clone();

    if let Err(error) = listen(move |event| {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;
            
        let mut global_event: Option<GlobalEvent> = None;

        match event.event_type {
            EventType::KeyPress(key) => {
                global_event = Some(GlobalEvent {
                    timestamp,
                    event_type: "key_press".to_string(),
                    key: Some(format!("{:?}", key)),
                    mouse_button: None,
                    position: None,
                    window_title: None,
                    app_name: None,
                    process_id: None,
                });
            },
            EventType::ButtonPress(btn) => {
                global_event = Some(GlobalEvent {
                    timestamp,
                    event_type: "mouse_click".to_string(),
                    key: None,
                    mouse_button: Some(format!("{:?}", btn)),
                    position: None,
                    window_title: None,
                    app_name: None,
                    process_id: None,
                });
            },
            _ => {}
        }

        if let Some(mut evt) = global_event {
             if let Ok(guard) = window_info_listener.lock() {
                 if let Some(info) = guard.as_ref() {
                     evt.window_title = Some(info.title.clone());
                     evt.app_name = Some(info.app_name.clone());
                 }
             }
             
             // Print JSON to stdout for parent process (Tauri) to read
             if let Ok(json) = serde_json::to_string(&evt) {
                 println!("{}", json);
             }
        }
    }) {
        eprintln!("Error: {:?}", error);
    }
}
