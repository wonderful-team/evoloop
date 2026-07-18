use std::collections::VecDeque;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use log::{info, warn};

use super::mic_capture::MicCapture;

const TARGET_SAMPLE_RATE: u32 = 16000;

/// Acoustic echo cancellation (AEC) microphone capture.
///
/// On macOS this tries to use the system VoiceProcessingIO AudioUnit which performs
/// echo cancellation using the audio played on its own output bus as the reference
/// signal. To make AEC effective, the TTS audio must be fed to `audio_queue` so that
/// the VoiceProcessingIO output callback can play it.
/// On failure or on non-macOS platforms it falls back to the regular cpal-based
/// `MicCapture`.
pub struct AecMicCapture {
    running: Arc<AtomicBool>,
    #[cfg(target_os = "macos")]
    mac: Option<MacAecCapture>,
    fallback: MicCapture,
}

impl AecMicCapture {
    pub fn new() -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            #[cfg(target_os = "macos")]
            mac: MacAecCapture::new().ok(),
            fallback: MicCapture::new(),
        }
    }

    /// Start capturing audio. The callback receives f32 samples at 16kHz mono.
    /// `audio_queue` is the source of TTS audio for the VoiceProcessingIO output bus.
    pub fn start<F>(
        &mut self,
        audio_queue: Arc<Mutex<VecDeque<f32>>>,
        callback: F,
    ) -> Result<(), String>
    where
        F: FnMut(&[f32]) + Send + 'static,
    {
        self.running.store(true, Ordering::SeqCst);

        let callback = Arc::new(Mutex::new(callback));

        #[cfg(target_os = "macos")]
        if let Some(mac) = self.mac.as_mut() {
            match mac.start(audio_queue.clone(), callback.clone()) {
                Ok(()) => {
                    info!("[aec] VoiceProcessingIO capture started with AEC");
                    return Ok(());
                }
                Err(e) => {
                    warn!("[aec] VoiceProcessingIO failed to start ({}), disabling it", e);
                    self.mac = None;
                }
            }
        }

        self.fallback.start(move |samples: &[f32]| {
            if let Ok(mut cb) = callback.lock() {
                cb(samples);
            }
        })
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        #[cfg(target_os = "macos")]
        if let Some(mac) = self.mac.as_mut() {
            mac.stop();
        }
        self.fallback.stop();
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}

#[cfg(target_os = "macos")]
mod macos {
    use super::*;
    use coreaudio::audio_unit::{
        AudioUnit, Element, IOType, SampleFormat, Scope, StreamFormat,
        audio_format::LinearPcmFlags,
        render_callback::{self, data},
    };

    const BYPASS_VOICE_PROCESSING: u32 = 2100; // kAUVoiceIOProperty_BypassVoiceProcessing
    const VOICE_PROCESSING_AGC: u32 = 2101;    // kAUVoiceIOProperty_VoiceProcessingEnableAGC

    pub struct MacAecCapture {
        audio_unit: AudioUnit,
        running: Arc<AtomicBool>,
    }

    impl MacAecCapture {
        pub fn new() -> Result<Self, String> {
            let mut audio_unit = AudioUnit::new(IOType::VoiceProcessingIO)
                .map_err(|e| format!("failed to create VoiceProcessingIO: {:?}", e))?;

            let format = StreamFormat {
                sample_rate: TARGET_SAMPLE_RATE as f64,
                sample_format: SampleFormat::F32,
                flags: LinearPcmFlags::IS_NON_INTERLEAVED | LinearPcmFlags::IS_PACKED,
                channels: 1,
            };

            // Input stream: output scope, input element (bus 1).
            audio_unit.set_stream_format(format, Scope::Output, Element::Input)
                .map_err(|e| format!("failed to set input stream format: {:?}", e))?;

            // Output stream: input scope, output element (bus 0).
            audio_unit.set_stream_format(format, Scope::Input, Element::Output)
                .map_err(|e| format!("failed to set output stream format: {:?}", e))?;

            // Enable AEC: do not bypass voice processing.
            let bypass: u32 = 0;
            audio_unit.set_property(
                BYPASS_VOICE_PROCESSING,
                Scope::Global,
                Element::Output,
                Some(&bypass),
            ).map_err(|e| format!("failed to enable AEC: {:?}", e))?;

            // Enable automatic gain control.
            let agc: u32 = 1;
            audio_unit.set_property(
                VOICE_PROCESSING_AGC,
                Scope::Global,
                Element::Output,
                Some(&agc),
            ).map_err(|e| format!("failed to enable AGC: {:?}", e))?;

            Ok(Self {
                audio_unit,
                running: Arc::new(AtomicBool::new(false)),
            })
        }

        pub fn start<F>(
            &mut self,
            audio_queue: Arc<Mutex<VecDeque<f32>>>,
            callback: Arc<Mutex<F>>,
        ) -> Result<(), String>
        where
            F: FnMut(&[f32]) + Send + 'static,
        {
            self.running.store(true, Ordering::SeqCst);

            // Output render callback: play TTS audio from the queue, or silence.
            let running = self.running.clone();
            self.audio_unit.set_render_callback(
                move |mut args: render_callback::Args<data::NonInterleaved<f32>>| {
                    if !running.load(Ordering::SeqCst) {
                        return Ok(());
                    }
                    for channel in args.data.channels_mut() {
                        let mut samples = Vec::with_capacity(channel.len());
                        if let Ok(mut q) = audio_queue.lock() {
                            for _ in 0..channel.len() {
                                samples.push(q.pop_front().unwrap_or(0.0));
                            }
                        } else {
                            samples.resize(channel.len(), 0.0);
                        }
                        channel.copy_from_slice(&samples);
                    }
                    Ok(())
                }
            ).map_err(|e| format!("failed to set output render callback: {:?}", e))?;

            // Input callback: forward captured samples to the user callback.
            let running = self.running.clone();
            self.audio_unit.set_input_callback(
                move |args: render_callback::Args<data::NonInterleaved<f32>>| {
                    if !running.load(Ordering::SeqCst) {
                        return Ok(());
                    }
                    let mut channels = args.data.channels();
                    if let Some(samples) = channels.next() {
                        if let Ok(mut cb) = callback.lock() {
                            cb(samples);
                        }
                    }
                    Ok(())
                }
            ).map_err(|e| format!("failed to set input callback: {:?}", e))?;

            self.audio_unit.start()
                .map_err(|e| format!("failed to start VoiceProcessingIO: {:?}", e))?;

            info!("[aec] VoiceProcessingIO started (AEC enabled)");
            Ok(())
        }

        pub fn stop(&mut self) {
            self.running.store(false, Ordering::SeqCst);
            let _ = self.audio_unit.stop();
        }
    }
}

#[cfg(target_os = "macos")]
use macos::MacAecCapture;
