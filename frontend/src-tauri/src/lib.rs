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
        
        
        // ... existing desktop setup ...
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
             let icon = Image::from_bytes(icon_bytes).expect("failed to load tray icon");

             let tray = TrayIconBuilder::with_id("tray")
                 .menu(&menu)
                 .icon(icon)
                 .icon_as_template(true)
                 .title("EvoLoop")
                 .on_menu_event(|app, event| match event.id.as_ref() {
                     "quit" => {
                         let state = app.state::<AppServiceState>();
                         let children = state.children.lock().unwrap();
                         for child in children.iter() {
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
             // uv run --directory ../backend fastapi run app/main.py --workers 4
             let cmd = shell.command("uv")
                 .args([
                     "run",
                     "--directory", "../backend",
                     "fastapi", "run", "app/main.py", "--workers", "4"
                 ]);
             if let Ok((_, child)) = cmd.spawn() {
                 state.children.lock().unwrap().push(child);
             }

             // Start Celery Worker
             // uv run --directory ../backend celery -A app.celery_app worker -l info -P solo -Q celery
             let cmd_celery = shell.command("uv")
                 .args([
                     "run",
                     "--directory", "../backend",
                     "celery", "-A", "app.celery_app", "worker", "-l", "info", "-P", "solo", "-Q", "celery"
                 ]);
             if let Ok((_, child)) = cmd_celery.spawn() {
                 state.children.lock().unwrap().push(child);
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
        _ => {}
    });
}
