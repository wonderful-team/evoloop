// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[cfg(desktop)]
use tauri::Manager;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init());
        

    let builder = builder.setup(|_app| {
        #[cfg(mobile)]
        
        
        // ... existing desktop setup ...
        #[cfg(desktop)]
        {
             use tauri::menu::{Menu, MenuItem};
             use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
     
             let quit_i = MenuItem::with_id(_app, "quit", "Quit", true, None::<&str>)?;
             let show_i = MenuItem::with_id(_app, "show", "Show App", true, None::<&str>)?;
             let menu = Menu::with_items(_app, &[&show_i, &quit_i])?;
     
             let _tray = TrayIconBuilder::with_id("tray")
                 .menu(&menu)
                 .icon(_app.default_window_icon().unwrap().clone())
                 .show_menu_on_left_click(false)
                 .on_menu_event(|app, event| match event.id.as_ref() {
                     "quit" => {
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
        }
        Ok(())
    });

    builder
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
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
