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
struct AppServiceState {
    children: Arc<Mutex<Vec<CommandChild>>>,
    tray: Arc<Mutex<Option<TrayIcon>>>,
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
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
             };
             _app.manage(service_state);

             // Create Tray Icon FIRST to ensure visibility
             use tauri::menu::{Menu, MenuItem};
             use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
             use tauri::image::Image;

             let quit_i = MenuItem::with_id(_app, "quit", "Quit", true, None::<&str>)?;
             let show_i = MenuItem::with_id(_app, "show", "Show App", true, None::<&str>)?;
             let menu = Menu::with_items(_app, &[&show_i, &quit_i])?;
     
             let icon_bytes = include_bytes!("../icons/32x32.png");
             let image_buffer = image::load_from_memory(icon_bytes)
                .expect("failed to load tray icon")
                .to_rgba8();
             let (width, height) = image_buffer.dimensions();
             let icon = Image::new(&image_buffer, width, height);

             let tray = TrayIconBuilder::with_id("tray")
                 .menu(&menu)
                 .icon(icon)
                 .icon_as_template(true)
                 .title("EvoLoop")
                 .on_menu_event(|app, event| match event.id.as_ref() {
                     "quit" => {
                         let state = app.state::<AppServiceState>();
                         let mut children = state.children.lock().unwrap();
                         while let Some(child) = children.pop() {
                            let _ = child.kill();
                         }
                         app.exit(0);
                     }
                     "show" => {
                         if let Some(window) = app.get_webview_window("main") {
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
                             let _ = window.show();
                             let _ = window.set_focus();
                         }
                     }
                     _ => {}
                 })
                 .build(_app)?;
                 
             let state = _app.state::<AppServiceState>();
             *state.tray.lock().unwrap() = Some(tray);

             let shell = _app.shell();

             // Start Web Server
             // Sidecar: evoloop-backend api
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
        }
        Ok(())
    });

    let app = builder
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                #[cfg(desktop)]
                {
                    let _ = window.hide();
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
        .invoke_handler(tauri::generate_handler![greet, capture_screenshot])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| match event {
        #[cfg(desktop)]
        tauri::RunEvent::Reopen { .. } => {
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
        #[cfg(desktop)]
        tauri::RunEvent::Exit => {
             let state = app_handle.state::<AppServiceState>();
             let mut children = state.children.lock().unwrap();
             while let Some(child) = children.pop() {
                let _ = child.kill();
             }
        }
        _ => {}
    });
}
