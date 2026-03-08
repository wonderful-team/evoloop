/// System tray setup and tray-related Tauri commands.
///
/// `setup_tray` is called from lib.rs's setup closure after AppServiceState is managed.
/// `sync_tray_recording_state` / `sync_tray_translations` are Tauri commands used by the frontend.

#[cfg(desktop)]
use crate::AppServiceState;

#[cfg(desktop)]
use std::sync::{Arc, atomic::Ordering};
#[cfg(desktop)]
use tauri::{Emitter, Manager};
#[cfg(desktop)]
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
#[cfg(desktop)]
use tauri::tray::{TrayIconBuilder, TrayIcon};

// ===== Tray Sync Commands =====

#[tauri::command]
#[cfg(desktop)]
pub fn sync_tray_recording_state(
    state: tauri::State<'_, AppServiceState>,
    is_recording: bool,
    start_text: String,
    stop_text: String,
) {
    let item_lock = state.record_item.lock().unwrap();
    if let Some(record_item) = item_lock.as_ref() {
        let text = if is_recording { stop_text } else { start_text };
        let _ = record_item.set_text(text);
    }
    // Update blinking state
    state.is_blinking.store(is_recording, Ordering::Relaxed);
}

#[tauri::command]
#[cfg(desktop)]
pub fn sync_tray_translations(
    state: tauri::State<'_, AppServiceState>,
    show_text: String,
    quit_text: String,
) {
    {
        let item_lock = state.show_item.lock().unwrap();
        if let Some(show_item) = item_lock.as_ref() {
            let _ = show_item.set_text(show_text);
        }
    }
    {
        let item_lock = state.quit_item.lock().unwrap();
        if let Some(quit_item) = item_lock.as_ref() {
            let _ = quit_item.set_text(quit_text);
        }
    }
}

#[tauri::command]
#[cfg(mobile)]
pub fn sync_tray_recording_state() {}

#[tauri::command]
#[cfg(mobile)]
pub fn sync_tray_translations() {}

#[tauri::command]
#[cfg(desktop)]
pub fn sync_tray_event_count(
    state: tauri::State<'_, AppServiceState>,
    count: usize,
) {
    state.event_count.store(count, Ordering::Relaxed);
}

#[tauri::command]
#[cfg(mobile)]
pub fn sync_tray_event_count() {}

// ===== Tray Setup =====

/// Builds and returns the system tray icon.
/// Call this from lib.rs setup after AppServiceState has been managed.
/// The returned TrayIcon must be stored in `state.tray`.
#[cfg(desktop)]
pub fn setup_tray(
    app: &mut tauri::App,
    show_i: &MenuItem<tauri::Wry>,
    record_i: &MenuItem<tauri::Wry>,
    quit_i: &MenuItem<tauri::Wry>,
) -> tauri::Result<TrayIcon<tauri::Wry>> {
    use tauri::image::Image;

    let menu = Menu::with_items(app, &[
        show_i,
        record_i,
        &PredefinedMenuItem::separator(app)?,
        quit_i,
    ])?;

    // 1. Prepare icons
    let icon_bytes = include_bytes!("../icons/logo-tray.png");
    let normal_img = image::load_from_memory(icon_bytes)
        .expect("failed to load tray icon")
        .to_rgba8();
    let (width, height) = normal_img.dimensions();
    
    let normal_raw = normal_img.clone().into_raw();
    let normal_data: &'static [u8] = Box::leak(normal_raw.into_boxed_slice());
    let normal_icon = Image::new(normal_data, width, height);

    // Create a red version for the "active" state
    let mut active_raw = normal_img.into_raw();
    for i in (0..active_raw.len()).step_by(4) {
        // If it's the white ring (approximate), tint it red
        if active_raw[i] > 150 && active_raw[i+1] > 150 && active_raw[i+2] > 150 {
            active_raw[i] = 255;   // Red
            active_raw[i+1] = 50;  // Green
            active_raw[i+2] = 50;  // Blue
        }
    }
    let active_data: &'static [u8] = Box::leak(active_raw.into_boxed_slice());
    let active_icon = Image::new(active_data, width, height);

    let tray = TrayIconBuilder::with_id("tray")
        .menu(&menu)
        .icon(normal_icon.clone())
        .icon_as_template(true)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "quit" => {
                let state = app.state::<AppServiceState>();
                // Stop observer first
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
            "record" => {
                let state = app.state::<AppServiceState>();
                if state.is_blinking.load(Ordering::Relaxed) {
                    if let Some(window) = app.get_webview_window("main") {
                        #[cfg(target_os = "macos")]
                        app.set_activation_policy(tauri::ActivationPolicy::Regular).ok();
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                let _ = app.emit("tray-record-toggle", ());
            }
            _ => {}
        })
        .build(app)?;

    // 2. Start timer + event count thread
    let state = app.state::<AppServiceState>();
    let is_blinking       = state.is_blinking.clone();
    let recording_start   = Arc::clone(&state.recording_start_time);
    let record_item_arc   = Arc::clone(&state.record_item);
    let event_count_arc   = Arc::clone(&state.event_count);
    let tray_handle       = tray.clone();

    std::thread::spawn(move || {
        let mut was_recording = false;  // Track if we were in recording state last iteration
        loop {
            let is_recording = is_blinking.load(Ordering::Relaxed);
            if is_recording {
                was_recording = true;

                // --- Keep red icon while recording (no blinking) ---
                let _ = tray_handle.set_icon(Some(active_icon.clone()));

                // --- Calculate time ---
                let elapsed_secs = recording_start.lock().unwrap()
                    .map(|t| t.elapsed().as_secs())
                    .unwrap_or(0);
                let mm = elapsed_secs / 60;
                let ss = elapsed_secs % 60;
                let time_str = format!("{:02}:{:02}", mm, ss);

                // --- Show time in tray title (macOS) ---
                #[cfg(target_os = "macos")]
                let _ = tray_handle.set_title(Some(&time_str));

                // --- Event count in menu text ---
                let event_count = event_count_arc.load(Ordering::Relaxed);
                let label = format!("停止录制 [{} 事件]", event_count);
                let lock = record_item_arc.lock().unwrap();
                if let Some(item) = lock.as_ref() {
                    let _ = item.set_text(label);
                }

                std::thread::sleep(std::time::Duration::from_millis(700));
            } else {
                // Only reset when transitioning from recording to stopped state
                if was_recording {
                    let _ = tray_handle.set_icon(Some(normal_icon.clone()));
                    // Clear tray title (macOS)
                    #[cfg(target_os = "macos")]
                    let _ = tray_handle.set_title(None::<&str>);
                    let lock = record_item_arc.lock().unwrap();
                    if let Some(item) = lock.as_ref() {
                        let _ = item.set_text("开始录制");
                    }
                    was_recording = false;
                }
                std::thread::sleep(std::time::Duration::from_millis(1000));
            }
        }
    });

    Ok(tray)
}
