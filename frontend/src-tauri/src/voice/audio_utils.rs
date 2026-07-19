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
