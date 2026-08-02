use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use log::{info, warn};

use super::mic_capture::MicCapture;

const TARGET_SAMPLE_RATE: u32 = 16000;

#[cfg(target_os = "macos")]
use ringbuf::HeapCons;
#[cfg(target_os = "macos")]
use ringbuf::traits::consumer::Consumer;

/// Source of TTS audio for the VoiceProcessingIO output bus.
/// On macOS the output callback consumes samples from this queue so that the
/// VoiceProcessingIO AudioUnit can use them as the AEC reference signal.
#[cfg(target_os = "macos")]
pub struct TtsAudioSource {
    pub consumer: HeapCons<f32>,
    pub clear_flag: Arc<AtomicBool>,
}

/// Acoustic echo cancellation (AEC) microphone capture.
///
/// On macOS this tries to use the system VoiceProcessingIO AudioUnit which performs
/// echo cancellation using the audio played on its own output bus as the reference
/// signal. To make AEC effective, the TTS audio must be fed to `TtsAudioSource` so that
/// the VoiceProcessingIO output callback can play it.
/// On failure or on non-macOS platforms it falls back to the regular cpal-based
/// `MicCapture`.
pub struct AecMicCapture {
    running: Arc<AtomicBool>,
    #[cfg(target_os = "macos")]
    mac: Option<MacAecCapture>,
    #[cfg(target_os = "macos")]
    mac_running: Arc<AtomicBool>,
    fallback: MicCapture,
}

unsafe impl Send for AecMicCapture {}
unsafe impl Sync for AecMicCapture {}

impl AecMicCapture {
    pub fn new() -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            #[cfg(target_os = "macos")]
            mac: MacAecCapture::new().ok(),
            #[cfg(target_os = "macos")]
            mac_running: Arc::new(AtomicBool::new(false)),
            fallback: MicCapture::new(),
        }
    }

    /// Start capturing audio. The callback receives f32 samples at 16kHz mono.
    #[cfg(target_os = "macos")]
    pub fn start<F>(
        &mut self,
        tts_source: TtsAudioSource,
        callback: F,
    ) -> Result<(), String>
    where
        F: FnMut(&[f32]) + Send + 'static,
    {
        self.running.store(true, Ordering::SeqCst);

        let callback = Arc::new(Mutex::new(callback));

        // Try VoiceProcessingIO. If it fails, log but don't disable permanently,
        // so subsequent starts can retry. Fall back to MicCapture regardless.
        if self.mac.is_none() {
            match MacAecCapture::new() {
                Ok(m) => self.mac = Some(m),
                Err(e) => warn!("[aec] MacAecCapture::new() failed: {}", e),
            }
        }
        if let Some(mac) = self.mac.as_mut() {
            match mac.start(tts_source, callback.clone()) {
                Ok(()) => {
                    info!("[aec] VoiceProcessingIO capture started with AEC");
                    self.mac_running.store(true, Ordering::SeqCst);
                    // Success with AEC - skip fallback
                    self.fallback.stop();
                    return Ok(());
                }
                Err(e) => {
                    warn!("[aec] VoiceProcessingIO failed to start ({}), falling back to MicCapture", e);
                    mac.stop();
                    self.mac_running.store(false, Ordering::SeqCst);
                    // Discard the broken AudioUnit so next start() creates a fresh one.
                    // After Bluetooth reconnect the old instance is in a bad state.
                    self.mac = None;
                }
            }
        }

        info!("[aec] using fallback MicCapture (no AEC)");
        self.fallback.start(move |samples: &[f32]| {
            if let Ok(mut cb) = callback.lock() {
                cb(samples);
            }
        })
    }

    /// Start capturing audio. The callback receives f32 samples at 16kHz mono.
    #[cfg(not(target_os = "macos"))]
    pub fn start<F>(
        &mut self,
        callback: F,
    ) -> Result<(), String>
    where
        F: FnMut(&[f32]) + Send + 'static,
    {
        self.running.store(true, Ordering::SeqCst);
        info!("[aec] using fallback MicCapture (no AEC)");
        let callback = Arc::new(Mutex::new(callback));
        self.fallback.start(move |samples: &[f32]| {
            if let Ok(mut cb) = callback.lock() {
                cb(samples);
            }
        })
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        #[cfg(target_os = "macos")]
        {
            self.mac_running.store(false, Ordering::SeqCst);
            if let Some(mac) = self.mac.as_mut() {
                mac.stop();
            }
            // Drop the AudioUnit entirely so CoreAudio restores its audio route.
            // The next start() will create a fresh one.
            self.mac = None;
        }
        // Stop fallback capture explicitly so cpal releases the mic before we
        // drop the MicCapture.  On macOS this also triggers the dummy AudioUnit
        // workaround that extinguishes the yellow indicator.
        self.fallback.stop();
        // Replace with a fresh MicCapture so cpal fully releases the old audio unit.
        // Dropping MicCapture drops the Stream, which tells CoreAudio to release the mic.
        let old = std::mem::replace(&mut self.fallback, MicCapture::new());
        drop(old); // drops MicCapture → drops Stream → CoreAudio releases mic
    }

    pub fn is_live(&self) -> bool {
        #[cfg(target_os = "macos")]
        {
            self.mac_running.load(Ordering::SeqCst) || self.fallback.is_live()
        }
        #[cfg(not(target_os = "macos"))]
        {
            self.fallback.is_live()
        }
    }

    #[cfg(target_os = "macos")]
    pub fn is_aec_active(&self) -> bool {
        self.mac_running.load(Ordering::SeqCst)
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
            tts_source: TtsAudioSource,
            callback: Arc<Mutex<F>>,
        ) -> Result<(), String>
        where
            F: FnMut(&[f32]) + Send + 'static,
        {
            self.running.store(true, Ordering::SeqCst);

            let mut consumer = tts_source.consumer;
            let clear_flag = tts_source.clear_flag;

            // Output render callback: play TTS audio from the queue, or silence.
            // This is a real-time audio thread: no locks, no allocation.
            let running = self.running.clone();
            self.audio_unit.set_render_callback(
                move |mut args: render_callback::Args<data::NonInterleaved<f32>>| {
                    if !running.load(Ordering::SeqCst) {
                        return Ok(());
                    }
                    // Drain the queue when a clear (barge-in/stop) was requested.
                    if clear_flag.load(Ordering::SeqCst) {
                        let _ = consumer.clear();
                        clear_flag.store(false, Ordering::SeqCst);
                    }
                    for channel in args.data.channels_mut() {
                        let filled = consumer.pop_slice(channel);
                        for sample in &mut channel[filled..] {
                            *sample = 0.0;
                        }
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
