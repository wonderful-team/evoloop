use crate::voice::audio_utils::resample_rubato;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, Stream, StreamConfig};
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

    fn find_config(device: &Device) -> Result<(cpal::StreamConfig, u32), String> {
        // First try default_input_config (simpler, less likely to trigger CoreAudio errors)
        if let Ok(default_config) = device.default_input_config() {
            let sample_rate = default_config.sample_rate().0.max(TARGET_SAMPLE_RATE);
            let channels = default_config.channels();
            info!("[mic] using default config: {}Hz {}ch", sample_rate, channels);
            let config = cpal::StreamConfig {
                channels,
                sample_rate: cpal::SampleRate(sample_rate),
                buffer_size: cpal::BufferSize::Default,
            };
            return Ok((config, sample_rate));
        }

        // Fallback: enumerate supported configs (may fail on some CoreAudio states)
        let mut last_err = String::new();
        for attempt in 1..=3 {
            match device.supported_input_configs() {
                Ok(mut configs) => {
                    if let Some(cfg) = configs
                        .find(|c| c.channels() >= 1 && c.min_sample_rate().0 <= TARGET_SAMPLE_RATE)
                    {
                        let sample_rate = cfg.min_sample_rate().0.max(TARGET_SAMPLE_RATE);
                        let channels = cfg.channels();
                        let config = cpal::StreamConfig {
                            channels,
                            sample_rate: cpal::SampleRate(sample_rate),
                            buffer_size: cpal::BufferSize::Default,
                        };
                        return Ok((config, sample_rate));
                    }
                    return Err("No suitable input config found".to_string());
                }
                Err(e) => {
                    last_err = format!("{}", e);
                    warn!("[mic] failed to enumerate configs (attempt {}): {}", attempt, last_err);
                    std::thread::sleep(std::time::Duration::from_millis(200));
                }
            }
        }
        Err(format!("Failed to get input configs after 3 retries: {}", last_err))
    }

    /// Start capturing audio. The callback receives f32 samples at 16kHz mono.
    pub fn start<F>(&mut self, callback: F) -> Result<(), String>
    where
        F: FnMut(&[f32]) + Send + 'static,
    {
        let device = self.device.as_ref()
            .ok_or("No input device available")?;

        let (config, sample_rate) = Self::find_config(device)?;
        let channels = config.channels;

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


