use rubato::{Resampler, SincFixedIn, SincInterpolationParameters, SincInterpolationType, WindowFunction};

/// Audio resampler using rubato (Sinc band-limited interpolation).
/// Shared between mic_capture (input) and tts_engine (output).
pub fn resample_rubato(input: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
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

#[cfg(test)]
mod tests {
    use super::*;
    use ringbuf::{HeapRb, traits::{Consumer, Producer, Split}};

    #[test]
    fn resample_24k_to_16k_preserves_length_ratio() {
        // Use a longer signal (1 s @ 24 kHz) so the resampler's filter delay is
        // small relative to the signal. The output should be close to 2/3 of input.
        let samples_24k: Vec<f32> = (0..24000)
            .map(|i| {
                let t = i as f32 / 24000.0;
                (2.0 * std::f32::consts::PI * 440.0 * t).sin()
            })
            .collect();
        let samples_16k = resample_rubato(&samples_24k, 24000, 16000);
        assert!(!samples_16k.is_empty());
        let expected = (samples_24k.len() as f32 * 16000.0 / 24000.0) as usize;
        let ratio = samples_16k.len() as f32 / expected as f32;
        assert!(
            ratio >= 0.95 && ratio <= 1.05,
            "resampled length {} too far from expected {} (ratio {})",
            samples_16k.len(),
            expected,
            ratio
        );
    }

    #[test]
    fn resample_identity_returns_clone() {
        let input: Vec<f32> = (0..100).map(|i| i as f32 / 100.0).collect();
        let output = resample_rubato(&input, 16000, 16000);
        assert_eq!(input, output);
    }

    #[test]
    fn ringbuf_carries_resampled_tts_samples() {
        let samples_24k: Vec<f32> = (0..240).map(|i| (i as f32 * 0.01).sin()).collect();
        let samples_16k = resample_rubato(&samples_24k, 24000, 16000);
        assert!(!samples_16k.is_empty());

        let rb = HeapRb::<f32>::new(1024);
        let (mut prod, mut cons) = rb.split();

        let pushed = prod.push_slice(&samples_16k);
        assert_eq!(pushed, samples_16k.len(), "ring buffer should accept all resampled samples");

        let mut read_back = vec![0.0f32; pushed];
        let popped = cons.pop_slice(&mut read_back);
        assert_eq!(popped, pushed, "consumer should pop all pushed samples");
        assert_eq!(read_back, samples_16k, "samples should be unchanged through ring buffer");
    }

    #[test]
    fn ringbuf_clear_drops_all_samples() {
        let rb = HeapRb::<f32>::new(256);
        let (mut prod, mut cons) = rb.split();
        let samples: Vec<f32> = (0..100).map(|i| i as f32).collect();
        prod.push_slice(&samples);
        assert_eq!(cons.clear(), samples.len());
        let mut buf = [0.0f32; 1];
        assert_eq!(cons.pop_slice(&mut buf), 0);
    }
}
