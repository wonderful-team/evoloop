// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use tauri::Manager;
#[cfg(desktop)]
use std::sync::{Arc, Mutex};
#[cfg(desktop)]
use tauri_plugin_shell::process::CommandChild;
#[cfg(desktop)]
use tauri_plugin_shell::ShellExt;
#[cfg(desktop)]
use tauri::tray::TrayIcon;
use tauri::WindowEvent;

#[cfg(desktop)]
mod global_observer;
#[cfg(desktop)]
use global_observer::GlobalObserver;

#[cfg(desktop)]
struct AppServiceState {
    children: Arc<Mutex<Vec<CommandChild>>>,
    tray: Arc<Mutex<Option<TrayIcon>>>,
    global_observer: Arc<GlobalObserver>,
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
#[cfg(desktop)]
async fn capture_screenshot() -> Result<String, String> {
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
async fn capture_screenshot() -> Result<String, String> {
    Err("Screen capture is not supported on mobile.".to_string())
}

#[tauri::command]
#[cfg(desktop)]
async fn start_global_recording(state: tauri::State<'_, AppServiceState>, app: tauri::AppHandle) -> Result<(), String> {
    println!("Start global recording requested");
    state.global_observer.start(app);
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn start_global_recording() -> Result<(), String> {
    Err("Global recording is not supported on mobile".to_string())
}

#[tauri::command]
#[cfg(desktop)]
async fn stop_global_recording(state: tauri::State<'_, AppServiceState>) -> Result<(), String> {
    println!("Stop global recording requested");
    state.global_observer.stop();
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn stop_global_recording() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
#[cfg(desktop)]
fn is_global_recording(state: tauri::State<'_, AppServiceState>) -> bool {
    state.global_observer.is_recording()
}

#[tauri::command]
#[cfg(mobile)]
fn is_global_recording() -> bool {
    false
}

// ... existing capture_screenshot ...

#[cfg(target_os = "macos")]
#[tauri::command]
fn check_accessibility_permission() -> bool {
    macos_accessibility_client::accessibility::application_is_trusted()
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn check_accessibility_permission() -> bool {
    true
}

#[cfg(target_os = "macos")]
#[tauri::command]
fn open_accessibility_settings() {
    println!("Requesting accessibility permission...");
    // Force prompt first
    let result = macos_accessibility_client::accessibility::application_is_trusted_with_prompt();
    println!("Prompt result: {}", result);
    
    if !result {
        println!("Permission not granted, opening system settings...");
         let _ = std::process::Command::new("open")
            .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
            .spawn();
    }
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn open_accessibility_settings() {}

// ... existing run() function ...

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(desktop)]
    std::panic::set_hook(Box::new(|info| {
        let msg = format!("Panic occurred: {:?}", info);
        println!("{}", msg);
        // Try to write to a file in the current working directory
        let _ = std::fs::write("panic.log", msg);
    }));

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_stt::init())
        .plugin(tauri_plugin_tts::init());
        

    let builder = builder.setup(|_app| {
        #[cfg(mobile)]
        {
            // Mobile setup if needed
        }

        #[cfg(desktop)]
        {
             let service_state = AppServiceState {
                 children: Arc::new(Mutex::new(Vec::new())),
                 tray: Arc::new(Mutex::new(None)),
                 global_observer: Arc::new(GlobalObserver::new()),
             };
             _app.manage(service_state);

             // Create Tray Icon FIRST to ensure visibility
             use tauri::menu::{Menu, MenuItem};
             use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
             use tauri::image::Image;

             let quit_i = MenuItem::with_id(_app, "quit", "彻底退出", true, Some("CmdOrCtrl+Q"))?;
             let show_i = MenuItem::with_id(_app, "show", "显示主界面", true, None::<&str>)?;
             let menu = Menu::with_items(_app, &[&show_i, &quit_i])?;
     
             let icon_bytes = include_bytes!("../icons/logo-tray.png");
             let image_buffer = image::load_from_memory(icon_bytes)
                .expect("failed to load tray icon")
                .to_rgba8();
             let (width, height) = image_buffer.dimensions();
             let icon = Image::new(&image_buffer, width, height);

             let tray = TrayIconBuilder::with_id("tray")
                 .menu(&menu)
                 .icon(icon)
                 .icon_as_template(true)
                 .on_menu_event(|app, event| match event.id.as_ref() {
                     "quit" => {
                         let state = app.state::<AppServiceState>();
                         // Kill observer first?
                         state.global_observer.stop();
                         
                         let mut children = state.children.lock().unwrap();
                         while let Some(child) = children.pop() {
                            let _ = child.kill();
                         }
                         app.exit(0);
                     }
                     "show" => {
                         if let Some(window) = app.get_webview_window("main") {
                             #[cfg(target_os = "macos")]
                             app.set_activation_policy(tauri::ActivationPolicy::Regular).ok();
                             let _ = window.show();
                             let _ = window.set_focus();
                         }
                     }
                     _ => {}
                 })
                 .on_tray_icon_event(|tray, event| match event {
                     TrayIconEvent::Click {
                         button: MouseButton::Left,
                         ..
                     } => {
                         let app = tray.app_handle();
                         if let Some(window) = app.get_webview_window("main") {
                             #[cfg(target_os = "macos")]
                             app.set_activation_policy(tauri::ActivationPolicy::Regular).ok();
                             let _ = window.show();
                             let _ = window.set_focus();
                         }
                     }
                     _ => {}
                 })
                 .build(_app)?;
                 
             let state = _app.state::<AppServiceState>();
             *state.tray.lock().unwrap() = Some(tray);

             let _shell = _app.shell();

             // Start Web Server
             // Sidecar: evoloop-backend api
             /* COMMENTED OUT FOR DEBUGGING
             let cmd = shell.sidecar("evoloop-backend")
                 .expect("failed to create sidecar command")
                 .args(["api"]);
                 
             if let Ok((mut rx, child)) = cmd.spawn() {
                 state.children.lock().unwrap().push(child);
                 
                 let app_handle = _app.handle().clone();
                 tauri::async_runtime::spawn(async move {
                     use tauri_plugin_shell::process::CommandEvent;
                     use tauri::Emitter;

                     while let Some(event) = rx.recv().await {
                         match event {
                             CommandEvent::Stdout(line) => {
                                 let text = String::from_utf8_lossy(&line).to_string();
                                 println!("[API] {}", text);
                                 let _ = app_handle.emit("backend-log", text);
                             }
                             CommandEvent::Stderr(line) => {
                                 let text = String::from_utf8_lossy(&line).to_string();
                                 eprintln!("[API ERR] {}", text);
                                 let _ = app_handle.emit("backend-log", text);
                             }
                             _ => {}
                         }
                     }
                 });
             }

             // Start Celery Worker
             // Sidecar: evoloop-backend worker
             let cmd_celery = shell.sidecar("evoloop-backend")
                 .expect("failed to create sidecar command")
                 .args(["worker"]);
                 
             if let Ok((mut rx, child)) = cmd_celery.spawn() {
                 state.children.lock().unwrap().push(child);
                 
                 let app_handle = _app.handle().clone();
                 tauri::async_runtime::spawn(async move {
                     use tauri_plugin_shell::process::CommandEvent;
                     use tauri::Emitter;
                     
                     while let Some(event) = rx.recv().await {
                         match event {
                             CommandEvent::Stdout(line) => {
                                 let text = String::from_utf8_lossy(&line).to_string();
                                 println!("[WORKER] {}", text);
                                 let _ = app_handle.emit("backend-log", text);
                             }
                             CommandEvent::Stderr(line) => {
                                 let text = String::from_utf8_lossy(&line).to_string();
                                 eprintln!("[WORKER ERR] {}", text);
                                 let _ = app_handle.emit("backend-log", text);
                             }
                             _ => {}
                         }
                     }
                 });
             }
             */
        }
        Ok(())
    });

    let app = builder
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                #[cfg(desktop)]
                {
                    let _ = window.hide();
                    #[cfg(target_os = "macos")]
                    window.app_handle().set_activation_policy(tauri::ActivationPolicy::Accessory).ok();
                    api.prevent_close();
                }
            }
        })
        .on_page_load(|_window, _payload| {
            #[cfg(any(target_os = "android", target_os = "ios"))]
             {
                // This is a simplified way to hint, but real permission handling 
                // for Webview strictly requires Rust-side implementation in Tauri v2
                // or creating a custom plugin to hook into WebChromeClient on PermissionRequest.
                // However, Tauri v2 usually auto-grants if OS permission is present.
                // Let's ensure the webview is created with media access.
             }
        })
        .invoke_handler(tauri::generate_handler![
            greet, 
            capture_screenshot,
            start_global_recording,
            stop_global_recording,
            is_global_recording,
            check_accessibility_permission,
            open_accessibility_settings
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| match event {
        #[cfg(desktop)]
        tauri::RunEvent::Reopen { .. } => {
            if let Some(window) = app_handle.get_webview_window("main") {
                #[cfg(target_os = "macos")]
                app_handle.set_activation_policy(tauri::ActivationPolicy::Regular).ok();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
        #[cfg(desktop)]
        tauri::RunEvent::Exit => {
             let state = app_handle.state::<AppServiceState>();
             // Stop global observer
             state.global_observer.stop();

             let mut children = state.children.lock().unwrap();
             while let Some(child) = children.pop() {
                let _ = child.kill();
             }
        }
        _ => {}
    });
}
