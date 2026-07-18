use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, Stream, StreamConfig};
use rubato::{Resampler, SincFixedIn, SincInterpolationParameters, SincInterpolationType, WindowFunction};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use log::{error, info, warn};

const TARGET_SAMPLE_RATE: u32 = 16000;

pub struct MicCapture {
    device: Option<Device>,
    stream: Option<Stream>,
    running: Arc<AtomicBool>,
}

impl MicCapture {
    pub fn new() -> Self {
        let host = cpal::default_host();
        let device = host.default_input_device();
        if device.is_none() {
            warn!("[mic] no default input device found");
        }
        Self {
            device,
            stream: None,
            running: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Start capturing audio. The callback receives f32 samples at 16kHz mono.
    pub fn start<F>(&mut self, callback: F) -> Result<(), String>
    where
        F: FnMut(&[f32]) + Send + 'static,
    {
        let device = self.device.as_ref()
            .ok_or("No input device available")?;

        let supported_config = device
            .supported_input_configs()
            .map_err(|e| format!("Failed to get input configs: {}", e))?
            .find(|c| c.channels() >= 1 && c.min_sample_rate().0 <= TARGET_SAMPLE_RATE)
            .ok_or("No suitable input config found")?;

        let sample_rate = supported_config.min_sample_rate().0.max(TARGET_SAMPLE_RATE);
        let channels = supported_config.channels();

        let config = StreamConfig {
            channels,
            sample_rate: cpal::SampleRate(sample_rate),
            buffer_size: cpal::BufferSize::Default,
        };

        info!(
            "[mic] starting capture: {}Hz, {}ch (target {}Hz)",
            sample_rate, channels, TARGET_SAMPLE_RATE
        );

        let running = self.running.clone();
        let callback = Arc::new(std::sync::Mutex::new(callback));

        let stream = device
            .build_input_stream(
                &config,
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    if !running.load(Ordering::SeqCst) {
                        return;
                    }

                    // Downmix to mono if needed
                    let mono: Vec<f32> = if channels > 1 {
                        data.chunks(channels as usize)
                            .map(|chunk| chunk.iter().sum::<f32>() / channels as f32)
                            .collect()
                    } else {
                        data.to_vec()
                    };

                    // Resample if needed (rubato Sinc band-limited)
                    let resampled = if sample_rate != TARGET_SAMPLE_RATE {
                        resample_rubato(&mono, sample_rate, TARGET_SAMPLE_RATE)
                    } else {
                        mono
                    };

                    if let Ok(mut cb) = callback.lock() {
                        cb(&resampled);
                    }
                },
                |err| error!("[mic] stream error: {}", err),
                None,
            )
            .map_err(|e| format!("Failed to build input stream: {}", e))?;

        stream.play().map_err(|e| format!("Failed to start stream: {}", e))?;

        self.stream = Some(stream);
        self.running.store(true, Ordering::SeqCst);
        info!("[mic] capture started");

        Ok(())
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        if let Some(stream) = self.stream.take() {
            drop(stream);
        }
        info!("[mic] capture stopped");
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}

/// Audio resampler using rubato (Sinc band-limited interpolation).
fn resample_rubato(input: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if from_rate == to_rate || input.is_empty() {
        return input.to_vec();
    }

    let ratio = to_rate as f64 / from_rate as f64;
    let params = SincInterpolationParameters {
        sinc_len: 256,
        f_cutoff: 0.95,
        interpolation: SincInterpolationType::Linear,
        oversampling_factor: 256,
        window: WindowFunction::BlackmanHarris2,
    };

    let mut resampler = SincFixedIn::<f32>::new(
        ratio,
        1.0,
        params,
        input.len(),
        1,
    ).expect("Failed to create rubato resampler");

    let waves_in = vec![input.to_vec()];
    let mut output = resampler.process(&waves_in, None).expect("Rubato resampling failed");
    output.remove(0)
}
