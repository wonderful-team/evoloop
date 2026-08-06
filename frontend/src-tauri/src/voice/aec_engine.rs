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
    use crate::voice::audio_utils::resample_rubato;
    use coreaudio::audio_unit::{
        AudioUnit, Element, IOType, SampleFormat, Scope, StreamFormat,
        audio_format::LinearPcmFlags,
        render_callback::{self, data},
    };

    const BYPASS_VOICE_PROCESSING: u32 = 2100; // kAUVoiceIOProperty_BypassVoiceProcessing
    const VOICE_PROCESSING_AGC: u32 = 2101;    // kAUVoiceIOProperty_VoiceProcessingEnableAGC

    /// Pull the next TTS source sample from the ring buffer, refilling the
    /// small stack buffer when exhausted. Returns 0.0 (silence) when the
    /// queue is empty. Real-time safe: no locks, no heap allocation.
    fn next_src_sample(
        consumer: &mut HeapCons<f32>,
        buf: &mut [f32; 16],
        len: &mut usize,
        idx: &mut usize,
    ) -> f32 {
        if *idx >= *len {
            *len = consumer.pop_slice(buf);
            *idx = 0;
        }
        if *len == 0 {
            0.0
        } else {
            let s = buf[*idx];
            *idx += 1;
            s
        }
    }

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
            // Bluetooth HFP devices lock their stream format, so this is
            // best-effort: the unit falls back to the device's native format
            // and the input callback resamples to 16kHz if needed.
            if let Err(e) = audio_unit.set_stream_format(format, Scope::Output, Element::Input) {
                warn!("[aec] input stream format not writable ({}), using device default", e);
            }

            // Output stream: input scope, output element (bus 0).
            if let Err(e) = audio_unit.set_stream_format(format, Scope::Input, Element::Output) {
                warn!("[aec] output stream format not writable ({}), using device default", e);
            }

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
            if let Err(e) = audio_unit.set_property(
                VOICE_PROCESSING_AGC,
                Scope::Global,
                Element::Output,
                Some(&agc),
            ) {
                warn!("[aec] failed to enable AGC ({}), continuing without", e);
            }

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

            // Query the actual stream formats FIRST. Bluetooth aggregate
            // devices lock their formats (the earlier best-effort 16k set is
            // ignored), so we must adapt to whatever the unit really delivers.
            let input_format = self.audio_unit.input_stream_format().ok();
            let output_format = self.audio_unit.output_stream_format().ok();
            let input_rate = input_format.as_ref().map(|f| f.sample_rate).unwrap_or(TARGET_SAMPLE_RATE as f64);
            let output_rate = output_format.as_ref().map(|f| f.sample_rate).unwrap_or(TARGET_SAMPLE_RATE as f64);
            let input_non_interleaved = input_format
                .as_ref()
                .map(|f| f.flags.contains(LinearPcmFlags::IS_NON_INTERLEAVED))
                .unwrap_or(true);
            let input_is_float = input_format
                .as_ref()
                .map(|f| f.flags.contains(LinearPcmFlags::IS_FLOAT))
                .unwrap_or(true);
            let input_channels = input_format.as_ref().map(|f| f.channels as usize).unwrap_or(1);
            info!(
                "[aec] VPIO formats: in={:.0}Hz/{}ch/{}interleaved/{}float out={:.0}Hz",
                input_rate,
                input_channels,
                if input_non_interleaved { "non-" } else { "" },
                input_is_float,
                output_rate,
            );
            let input_needs_resample = (input_rate - TARGET_SAMPLE_RATE as f64).abs() > 1.0;
            let output_needs_resample = (output_rate - TARGET_SAMPLE_RATE as f64).abs() > 1.0;

            // Output render callback: play TTS from the ring buffer, or silence.
            // This is a real-time audio thread: no locks, no allocation.
            // When the device runs at a different rate than the 16k TTS
            // reference, a stateful linear-interpolation SRC keeps playback
            // speed correct.
            let running = self.running.clone();
            let mut src_buf = [0.0f32; 16];
            let mut src_len = 0usize;
            let mut src_idx = 0usize;
            let mut src_pos = 0.0f64;
            let mut src_cur = 0.0f32;
            let mut src_nxt = 0.0f32;
            let mut src_primed = false;
            let src_ratio = TARGET_SAMPLE_RATE as f64 / output_rate;
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
                    // The TTS reference is mono: run the SRC only on the first
                    // channel (advancing src_pos once per output FRAME, not per
                    // channel), then broadcast the result to the remaining
                    // channels. Advancing per channel would consume the queue at
                    // channels-per-frame times the real rate (2x on stereo output).
                    let mut channel_iter = args.data.channels_mut();
                    if let Some(first) = channel_iter.next() {
                        if output_needs_resample {
                            if !src_primed {
                                src_cur = next_src_sample(&mut consumer, &mut src_buf, &mut src_len, &mut src_idx);
                                src_nxt = next_src_sample(&mut consumer, &mut src_buf, &mut src_len, &mut src_idx);
                                src_primed = true;
                            }
                            for sample in first.iter_mut() {
                                while src_pos >= 1.0 {
                                    src_pos -= 1.0;
                                    src_cur = src_nxt;
                                    src_nxt = next_src_sample(&mut consumer, &mut src_buf, &mut src_len, &mut src_idx);
                                }
                                *sample = src_cur + (src_nxt - src_cur) * src_pos as f32;
                                src_pos += src_ratio;
                            }
                        } else {
                            let filled = consumer.pop_slice(first);
                            for sample in &mut first[filled..] {
                                *sample = 0.0;
                            }
                        }
                        for channel in channel_iter {
                            for (dst, src) in channel.iter_mut().zip(first.iter()) {
                                *dst = *src;
                            }
                        }
                    }
                    Ok(())
                }
            ).map_err(|e| format!("failed to set output render callback: {:?}", e))?;

            // Input callback: normalize whatever the device delivers (float or
            // integer, interleaved or not, any rate) to 16k mono f32 for the
            // upstream voice session.
            let input_rate_u32 = input_rate as u32;
            let set_input: Result<(), coreaudio::error::Error> = {
                if input_non_interleaved && input_is_float {
                    let running = self.running.clone();
                    let callback = callback.clone();
                    self.audio_unit.set_input_callback(
                        move |args: render_callback::Args<data::NonInterleaved<f32>>| {
                            if !running.load(Ordering::SeqCst) {
                                return Ok(());
                            }
                            if let Some(samples) = args.data.channels().next() {
                                if let Ok(mut cb) = callback.lock() {
                                    let out = if input_needs_resample {
                                        resample_rubato(samples, input_rate_u32, TARGET_SAMPLE_RATE)
                                    } else {
                                        samples.to_vec()
                                    };
                                    cb(&out);
                                }
                            }
                            Ok(())
                        }
                    )
                } else if input_non_interleaved {
                    let running = self.running.clone();
                    let callback = callback.clone();
                    self.audio_unit.set_input_callback(
                        move |args: render_callback::Args<data::NonInterleaved<i16>>| {
                            if !running.load(Ordering::SeqCst) {
                                return Ok(());
                            }
                            if let Some(samples) = args.data.channels().next() {
                                let samples: Vec<f32> = samples.iter().map(|&s| s as f32 / 32768.0).collect();
                                if let Ok(mut cb) = callback.lock() {
                                    let out = if input_needs_resample {
                                        resample_rubato(&samples, input_rate_u32, TARGET_SAMPLE_RATE)
                                    } else {
                                        samples
                                    };
                                    cb(&out);
                                }
                            }
                            Ok(())
                        }
                    )
                } else if input_is_float {
                    let running = self.running.clone();
                    let callback = callback.clone();
                    self.audio_unit.set_input_callback(
                        move |args: render_callback::Args<data::Interleaved<f32>>| {
                            if !running.load(Ordering::SeqCst) {
                                return Ok(());
                            }
                            let channels = args.data.channels.max(1);
                            let samples: Vec<f32> = args.data.buffer
                                .chunks_exact(channels)
                                .map(|frame| frame.iter().sum::<f32>() / channels as f32)
                                .collect();
                            if !samples.is_empty() {
                                if let Ok(mut cb) = callback.lock() {
                                    let out = if input_needs_resample {
                                        resample_rubato(&samples, input_rate_u32, TARGET_SAMPLE_RATE)
                                    } else {
                                        samples
                                    };
                                    cb(&out);
                                }
                            }
                            Ok(())
                        }
                    )
                } else {
                    let running = self.running.clone();
                    let callback = callback.clone();
                    self.audio_unit.set_input_callback(
                        move |args: render_callback::Args<data::Interleaved<i16>>| {
                            if !running.load(Ordering::SeqCst) {
                                return Ok(());
                            }
                            let channels = args.data.channels.max(1);
                            let samples: Vec<f32> = args.data.buffer
                                .chunks_exact(channels)
                                .map(|frame| frame.iter().map(|&s| s as f32 / 32768.0).sum::<f32>() / channels as f32)
                                .collect();
                            if !samples.is_empty() {
                                if let Ok(mut cb) = callback.lock() {
                                    let out = if input_needs_resample {
                                        resample_rubato(&samples, input_rate_u32, TARGET_SAMPLE_RATE)
                                    } else {
                                        samples
                                    };
                                    cb(&out);
                                }
                            }
                            Ok(())
                        }
                    )
                }
            };
            set_input.map_err(|e| format!("failed to set input callback: {:?}", e))?;

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
