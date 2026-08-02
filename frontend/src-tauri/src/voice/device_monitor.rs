use cpal::traits::{DeviceTrait, HostTrait};
use log::{info, warn};
use tauri::Emitter;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;

#[derive(Debug, Clone)]
pub enum DeviceEvent {
    Available(Vec<String>),
    Unavailable,
    Changed(Vec<String>),
}

/// Fires the monitor loop immediately — no polling, no delay.
/// On macOS: triggered by the CoreAudio `kAudioHardwarePropertyDevices` callback.
/// On other platforms: not used (polling fallback).
#[cfg(target_os = "macos")]
static DEVICE_NOTIFY: std::sync::LazyLock<tokio::sync::Notify> =
    std::sync::LazyLock::new(|| tokio::sync::Notify::new());

pub fn spawn_device_monitor(
    app_handle: tauri::AppHandle,
    stop: Arc<AtomicBool>,
    tx: mpsc::Sender<DeviceEvent>,
) {
    #[cfg(target_os = "macos")]
    macos_listener::setup();

    tokio::spawn(async move {
        let mut last_available: Option<bool> = None;
        let mut last_names: Option<Vec<String>> = None;

        // Initial check — report current state immediately
        check_devices(&app_handle, &tx, &mut last_available, &mut last_names).await;

        loop {
            if stop.load(Ordering::SeqCst) {
                break;
            }

            // Wait for notification.
            // macOS: CoreAudio fires DEVICE_NOTIFY when device list changes.
            // Others: 2s polling timeout.
            #[cfg(target_os = "macos")]
            {
                tokio::select! {
                    _ = DEVICE_NOTIFY.notified() => {
                        // Woken by CoreAudio — check immediately
                    }
                    _ = tokio::time::sleep(Duration::from_secs(5)) => {
                        // Safety timeout (shouldn't normally fire)
                    }
                }
            }
            #[cfg(not(target_os = "macos"))]
            tokio::time::sleep(Duration::from_secs(2)).await;

            // Check device state and emit if changed
            check_devices(&app_handle, &tx, &mut last_available, &mut last_names).await;
        }
    });
}

async fn check_devices(
    app_handle: &tauri::AppHandle,
    tx: &mpsc::Sender<DeviceEvent>,
    last_available: &mut Option<bool>,
    last_names: &mut Option<Vec<String>>,
) {
    let names: Vec<String> = match cpal::default_host().input_devices() {
        Ok(devices) => devices
            .filter_map(|d| d.name().ok())
            .filter(|n| !n.is_empty())
            .collect(),
        Err(e) => {
            warn!("[device-monitor] enum failed: {}", e);
            Vec::new()
        }
    };

    let available = !names.is_empty();
    let changed = last_names.as_ref().map(|last| *last != names).unwrap_or(true);
    let avail_changed = last_available.map(|a| a != available).unwrap_or(true);

    if changed || avail_changed {
        info!("[device-monitor] available={}, devices={:?}", available, names);
        if available {
            let _ = app_handle.emit("mic:available", serde_json::json!({"devices": names}));
        } else {
            let _ = app_handle.emit("mic:unavailable", serde_json::json!({}));
        }
        if !available {
            let _ = tx.send(DeviceEvent::Unavailable).await;
        } else if avail_changed {
            let _ = tx.send(DeviceEvent::Available(names.clone())).await;
        } else {
            let _ = tx.send(DeviceEvent::Changed(names.clone())).await;
        }
        *last_available = Some(available);
        *last_names = Some(names);
    }
}

// ── macOS CoreAudio property listener ────────────────────────────────────

/// Registers a `kAudioHardwarePropertyDevices` listener on the system object.
/// The callback calls `DEVICE_NOTIFY.notify_one()` which wakes the monitor
/// loop immediately — no polling, zero delay.
#[cfg(target_os = "macos")]
mod macos_listener {
    use super::DEVICE_NOTIFY;
    use log::{info, warn};

    #[repr(C)]
    struct PropertyAddress {
        m_selector: u32,
        m_scope: u32,
        m_element: u32,
    }

    const SYSTEM_OBJECT: u32 = 1;
    const PROP_DEVICES: u32 = 0x64657620;
    const SCOPE_GLOBAL: u32 = 0x676C6F62;
    const ELEMENT_MAIN: u32 = 0;

    extern "C" {
        fn AudioObjectAddPropertyListener(
            object: u32,
            address: *const PropertyAddress,
            listener: Option<unsafe extern "C" fn(u32, u32, *const PropertyAddress, *mut std::ffi::c_void) -> i32>,
            client_data: *mut std::ffi::c_void,
        ) -> i32;
    }

    unsafe extern "C" fn callback(
        _id: u32,
        _count: u32,
        _addrs: *const PropertyAddress,
        _data: *mut std::ffi::c_void,
    ) -> i32 {
        DEVICE_NOTIFY.notify_one();
        0
    }

    pub fn setup() {
        let addr = PropertyAddress {
            m_selector: PROP_DEVICES,
            m_scope: SCOPE_GLOBAL,
            m_element: ELEMENT_MAIN,
        };
        unsafe {
            let status = AudioObjectAddPropertyListener(
                SYSTEM_OBJECT,
                &addr,
                Some(callback as unsafe extern "C" fn(_, _, _, _) -> _),
                std::ptr::null_mut(),
            );
            if status != 0 {
                warn!("[device-monitor] CoreAudio listener failed: {}", status);
            } else {
                info!("[device-monitor] CoreAudio listener registered");
            }
        }
    }
}
