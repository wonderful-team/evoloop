use rdev::{listen, EventType};
use serde::Serialize;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[derive(Clone, Serialize, Debug)]
pub struct GlobalEvent {
    pub timestamp: u64,
    pub event_type: String,
    pub key: Option<String>,
    pub mouse_button: Option<String>,
    pub position: Option<(f64, f64)>,
    pub window_title: Option<String>,
    pub app_name: Option<String>,
    pub window_bounds: Option<(f64, f64, f64, f64)>, // x, y, w, h
}

#[derive(Clone, Debug)]
struct WindowInfo {
    title: String,
    app_name: String,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
}

fn main() {
    println!("Recorder sidecar started (Improved v2)");

    let shared_window_info = Arc::new(Mutex::new(None::<WindowInfo>));
    let shared_mouse_pos = Arc::new(Mutex::new((0.0, 0.0)));

    // 1. Window Poller Thread (macOS specific)
    let window_info_clone = shared_window_info.clone();
    thread::spawn(move || {
        loop {
            let script = r#"
                tell application "System Events"
                    try
                        set frontApp to first application process whose frontmost is true
                        set appName to name of frontApp
                        set window1 to window 1 of frontApp
                        set windowTitle to name of window1
                        set {wX, wY} to position of window1
                        set {wW, wH} to size of window1
                        return appName & "|||" & windowTitle & "|||" & wX & "," & wY & "|||" & wW & "," & wH
                    on error
                        return "Unknown|||Unknown|||0,0|||0,0"
                    end try
                end tell
                "#;
                
            if let Ok(output) = std::process::Command::new("osascript")
                .arg("-e")
                .arg(script)
                .output() 
            {
                if output.status.success() {
                    let result = String::from_utf8_lossy(&output.stdout);
                    let parts: Vec<&str> = result.trim().split("|||").collect();
                    if parts.len() >= 4 {
                        let pos_parts: Vec<&str> = parts[2].split(',').collect();
                        let size_parts: Vec<&str> = parts[3].split(',').collect();
                        
                        let info = WindowInfo {
                            app_name: parts[0].to_string(),
                            title: parts[1].to_string(),
                            x: pos_parts.get(0).and_then(|&s| s.parse().ok()).unwrap_or(0.0),
                            y: pos_parts.get(1).and_then(|&s| s.parse().ok()).unwrap_or(0.0),
                            width: size_parts.get(0).and_then(|&s| s.parse().ok()).unwrap_or(0.0),
                            height: size_parts.get(1).and_then(|&s| s.parse().ok()).unwrap_or(0.0),
                        };
                        *window_info_clone.lock().unwrap() = Some(info);
                    }
                }
            }
            thread::sleep(Duration::from_millis(1000));
        }
    });

    // 2. Mouse Listener & Event Dispatcher
    let window_info_listener = shared_window_info.clone();
    let mouse_pos_listener = shared_mouse_pos.clone();

    if let Err(error) = listen(move |event| {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;
            
        let mut global_event: Option<GlobalEvent> = None;

        match event.event_type {
            EventType::MouseMove { x, y } => {
                *mouse_pos_listener.lock().unwrap() = (x, y);
            },
            EventType::KeyPress(key) => {
                let pos = *mouse_pos_listener.lock().unwrap();
                global_event = Some(GlobalEvent {
                    timestamp,
                    event_type: "key_press".to_string(),
                    key: Some(format!("{:?}", key)),
                    mouse_button: None,
                    position: Some(pos),
                    window_title: None,
                    app_name: None,
                    window_bounds: None,
                });
            },
            EventType::ButtonPress(btn) => {
                let pos = *mouse_pos_listener.lock().unwrap();
                global_event = Some(GlobalEvent {
                    timestamp,
                    event_type: "mouse_click".to_string(),
                    key: None,
                    mouse_button: Some(format!("{:?}", btn)),
                    position: Some(pos),
                    window_title: None,
                    app_name: None,
                    window_bounds: None,
                });
            },
            _ => {}
        }

        if let Some(mut evt) = global_event {
             if let Ok(guard) = window_info_listener.lock() {
                 if let Some(info) = guard.as_ref() {
                     evt.window_title = Some(info.title.clone());
                     evt.app_name = Some(info.app_name.clone());
                     evt.window_bounds = Some((info.x, info.y, info.width, info.height));
                 }
             }
             
             if let Ok(json) = serde_json::to_string(&evt) {
                 println!("{}", json);
             }
        }
    }) {
        eprintln!("Error: {:?}", error);
    }
}
