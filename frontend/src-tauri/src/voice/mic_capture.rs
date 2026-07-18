use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, Stream, StreamConfig};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use log::{info, warn, error};

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

                    // Resample if needed (simple linear interpolation)
                    let resampled = if sample_rate != TARGET_SAMPLE_RATE {
                        resample_linear(&mono, sample_rate, TARGET_SAMPLE_RATE)
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

/// Simple linear interpolation resampler.
fn resample_linear(input: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if from_rate == to_rate || input.is_empty() {
        return input.to_vec();
    }

    let ratio = to_rate as f64 / from_rate as f64;
    let output_len = (input.len() as f64 * ratio).ceil() as usize;
    let mut output = Vec::with_capacity(output_len);

    for i in 0..output_len {
        let src_idx = i as f64 / ratio;
        let idx0 = src_idx.floor() as usize;
        let idx1 = (idx0 + 1).min(input.len() - 1);
        let frac = src_idx - idx0 as f64;
        let sample = input[idx0] * (1.0 - frac as f32) + input[idx1] * frac as f32;
        output.push(sample);
    }

    output
}
