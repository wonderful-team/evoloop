use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use log::{info, error};
use tokio::io::AsyncWriteExt;
use tokio::sync::mpsc;
use tauri::Emitter;

use crate::voice::mic_capture::MicCapture;

use cpal::traits::HostTrait;
use sherpa_onnx::{KeywordSpotter, KeywordSpotterConfig};

/// Set by device_monitor when a new audio input device appears.
/// The retry loop checks this flag to skip the sleep and poll immediately.
pub(crate) static RETRY_NOW: AtomicBool = AtomicBool::new(false);

const SAMPLE_RATE: u32 = 16000;
const WAKE_REPLIES: [&str; 4] = ["我在", "嗯哼", "请说", "你说"];

/// Resolve the KWS model directory.
/// In production the sidecar sets `MODELS_DIR` to the Tauri app bundle's
/// `Resources/models/` directory. Fall back to `~/.evoloop/models/kws` for
/// development / manual installs.
fn kws_model_dir() -> PathBuf {
    std::env::var("MODELS_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            dirs::home_dir()
                .unwrap_or_default()
                .join(".evoloop/models")
        })
        .join("kws")
}

async fn play_wake_reply(text: &str) {
    let pcm_path = dirs::home_dir()
        .map(|p| p.join(".evoloop/sounds").join(format!("{}.pcm", text)));
    let pcm_path = match pcm_path {
        Some(ref p) if p.exists() => p.clone(),
        _ => return,
    };
    let data = match tokio::fs::read(&pcm_path).await {
        Ok(d) => d,
        Err(_) => return,
    };
    let mut child = match tokio::process::Command::new("ffplay")
        .args(["-f", "f32le", "-ar", "24000", "-nodisp", "-autoexit", "-"])
        .stdin(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
    {
        Ok(c) => c,
        Err(_) => return,
    };
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(&data).await;
        drop(stdin);
    }
    let _ = child.wait().await;
}

fn pinyin_kws(ch: char) -> Option<&'static str> {
    // KWS 格式: 声母 韵母(带声调)，空格分隔。零声母直接返回韵母。
    match ch {
        // 来自模型 keywords.txt 验证过的
        '你' => Some("n ǐ"), '好' => Some("h ǎo"),
        '小' => Some("x iǎo"), '爱' => Some("ài"),
        '同' => Some("t óng"), '学' => Some("x ué"),
        '米' => Some("m ǐ"), '哥' => Some("g ē"),
        '问' => Some("w èn"), '艺' => Some("y ì"),
        '美' => Some("m ěi"), '丽' => Some("l ì"),
        '蛋' => Some("d àn"), '西' => Some("x ī"),
        '林' => Some("l ín"), '军' => Some("j ūn"),
        // 声母+韵母拆分
        '天' => Some("t iān"), '气' => Some("q ì"),
        '打' => Some("d ǎ"), '开' => Some("k āi"),
        '音' => Some("y īn"), '乐' => Some("l è"),
        '帮' => Some("b āng"), '忙' => Some("m áng"),
        '智' => Some("zh ì"), '能' => Some("n éng"),
        '助' => Some("zh ù"), '手' => Some("sh ǒu"),
        '是' => Some("sh ì"), '在' => Some("z ài"),
        '的' => Some("d e"), '了' => Some("l e"),
        '我' => Some("w ǒ"), '他' => Some("t ā"),
        '她' => Some("t ā"), '一' => Some("y ī"),
        '不' => Some("b ù"), '就' => Some("j iù"),
        '这' => Some("zh è"), '那' => Some("n à"),
        '上' => Some("sh àng"), '下' => Some("x ià"),
        '说' => Some("sh uō"), '看' => Some("k àn"),
        '大' => Some("d à"), '中' => Some("zh ōng"),
        '对' => Some("d uì"), '起' => Some("q ǐ"),
        '有' => Some("y ǒu"), '人' => Some("r én"),
        '年' => Some("n ián"), '日' => Some("r ì"),
        '时' => Some("sh í"), '为' => Some("w èi"),
        '会' => Some("h uì"), '生' => Some("sh ēng"),
        '个' => Some("g è"), '到' => Some("d ào"),
        '以' => Some("y ǐ"), '家' => Some("j iā"),
        '木' => Some("m ù"), '头' => Some("t óu"),
        _ => None,
    }
}

enum WakeWordCmd {
    Start { app_handle: tauri::AppHandle, word: String, voice: String },
}

struct KwsPaths {
    encoder: String,
    decoder: String,
    joiner: String,
    tokens: String,
}

fn kws_paths() -> Option<KwsPaths> {
    let base = kws_model_dir();

    let (enc, dec, join) = if base.join("encoder-epoch-99-avg-1-chunk-16-left-64.int8.onnx").exists() {
        (
            base.join("encoder-epoch-99-avg-1-chunk-16-left-64.int8.onnx"),
            base.join("decoder-epoch-99-avg-1-chunk-16-left-64.int8.onnx"),
            base.join("joiner-epoch-99-avg-1-chunk-16-left-64.int8.onnx"),
        )
    } else {
        (
            base.join("encoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
            base.join("decoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
            base.join("joiner-epoch-12-avg-2-chunk-16-left-64.onnx"),
        )
    };

    if !enc.exists() { return None; }

    Some(KwsPaths {
        encoder: enc.to_string_lossy().to_string(),
        decoder: dec.to_string_lossy().to_string(),
        joiner: join.to_string_lossy().to_string(),
        tokens: base.join("tokens.txt").to_string_lossy().to_string(),
    })
}

pub struct WakeWordDetector {
    cmd_tx: Option<mpsc::Sender<WakeWordCmd>>,
    thread_handle: Option<std::thread::JoinHandle<()>>,
    stop_flag: Arc<AtomicBool>,
    thread_alive: Arc<AtomicBool>,
    last_params: Arc<Mutex<Option<(tauri::AppHandle, String, String)>>>,
}

impl WakeWordDetector {
    pub fn new() -> Self {
        Self { cmd_tx: None, thread_handle: None, stop_flag: Arc::new(AtomicBool::new(false)), thread_alive: Arc::new(AtomicBool::new(false)), last_params: Arc::new(Mutex::new(None)) }
    }

    pub fn start(
        &mut self,
        app_handle: tauri::AppHandle,
        word: String,
        voice: String,
    ) -> Result<(), String> {
        if self.thread_alive.load(Ordering::SeqCst) {
            return Ok(());
        }

        if let Ok(mut p) = self.last_params.lock() {
            *p = Some((app_handle.clone(), word.clone(), voice.clone()));
        }

        let paths = kws_paths().ok_or("KWS model not found")?;
        let (tx, mut rx) = mpsc::channel::<WakeWordCmd>(16);
        self.cmd_tx = Some(tx);
        self.stop_flag.store(false, Ordering::SeqCst);
        let stop = self.stop_flag.clone();
        let alive = self.thread_alive.clone();
        alive.store(true, Ordering::SeqCst);

        let handle = std::thread::spawn(move || {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all().build().expect("runtime");
            rt.block_on(async {
                let mut current_word: String;
                let mut current_voice: String;
                let mut need_retry = false;

                loop {
                    if need_retry {
                        tokio::select! {
                            cmd = rx.recv() => {
                                match cmd {
                                    Some(WakeWordCmd::Start { app_handle, word, voice }) => {
                                        current_word = word;
                                        current_voice = voice;
                                        let ok = run_detector(app_handle, &current_word, &current_voice, &paths, &stop).await;
                                        if ok { need_retry = false; }
                                    }
                                    None => break,
                                }
                            }
                            _ = tokio::time::sleep(Duration::from_secs(2)) => {
                                if RETRY_NOW.swap(false, Ordering::SeqCst) || cpal::default_host().default_input_device().is_some() {
                                info!("[wake] mic re-detected, retrying");
                                need_retry = false;
                            }
                            }
                        }
                    } else {
                        tokio::select! {
                            cmd = rx.recv() => {
                                match cmd {
                                    Some(WakeWordCmd::Start { app_handle, word, voice }) => {
                                        current_word = word;
                                        current_voice = voice;
                                        let ok = run_detector(app_handle, &current_word, &current_voice, &paths, &stop).await;
                                        if !ok { need_retry = true; }
                                    }
                                    None => break,
                                }
                            }
                        }
                    }
                }
            });
            alive.store(false, Ordering::SeqCst);
        });
        self.thread_handle = Some(handle);

        let _ = self.cmd_tx.as_ref().unwrap()
            .try_send(WakeWordCmd::Start { app_handle, word, voice });
        Ok(())
    }

    pub fn stop(&mut self) {
        self.stop_flag.store(true, Ordering::SeqCst);
        self.cmd_tx.take();
        if let Some(h) = self.thread_handle.take() {
            let _ = h.join();
        }
        if let Ok(mut p) = self.last_params.lock() {
            *p = None;
        }
    }

    pub fn set_wake_word(&self, _word: String) {
    }

    pub fn is_running(&self) -> bool {
        self.thread_alive.load(Ordering::SeqCst)
    }

    /// Stop the detector (called when voice session starts).
    pub fn pause(&mut self) {
        self.stop_flag.store(true, Ordering::SeqCst);
        self.cmd_tx.take();
        if let Some(h) = self.thread_handle.take() {
            let _ = h.join();
        }
    }

    /// Resume the detector with last known params (voice session ended).
    pub fn resume(&mut self) -> Result<(), String> {
        let params = self.last_params.lock().ok().and_then(|p| p.clone());
        if let Some((app_handle, word, voice)) = params {
            if let Err(e) = self.start(app_handle.clone(), word, voice) {
                error!("[wake] resume failed: {}", e);
                let _ = app_handle.emit(
                    "wake:error",
                    serde_json::json!({
                        "code": "resume_failed",
                        "message": format!("唤醒词监听恢复失败: {}", e),
                    }),
                );
                return Err(e);
            }
        }
        Ok(())
    }
}

fn to_keyword_line(word: &str) -> String {
    let mut parts: Vec<String> = Vec::new();
    for ch in word.chars() {
        if let Some(kws) = pinyin_kws(ch) {
            for token in kws.split(' ') {
                parts.push(token.to_string());
            }
        } else if ch.is_ascii_alphabetic() {
            parts.push(ch.to_lowercase().to_string());
        } else if ch.is_ascii_digit() {
            parts.push(ch.to_string());
        }
    }
    if parts.is_empty() {
        return format!("{} @{}", word, word);
    }
    format!("{} @{}", parts.join(" "), word)
}

async fn run_detector(
    app_handle: tauri::AppHandle,
    word: &str,
    _voice: &str,
    paths: &KwsPaths,
    stop: &AtomicBool,
) -> bool {
    let keyword_line = to_keyword_line(word);
    info!("[wake] keyword: {}, line: {}", word, keyword_line);

    let mut config = KeywordSpotterConfig::default();
    config.model_config.transducer.encoder = Some(paths.encoder.clone());
    config.model_config.transducer.decoder = Some(paths.decoder.clone());
    config.model_config.transducer.joiner = Some(paths.joiner.clone());
    config.model_config.tokens = Some(paths.tokens.clone());
    config.keywords_threshold = 0.25;
    config.keywords_buf = Some(keyword_line.clone());

    let kws = match KeywordSpotter::create(&config) {
        Some(k) => Arc::new(k),
        None => { error!("[wake] KeywordSpotter::create failed"); return false; }
    };

    let stream = Arc::new(kws.create_stream_with_keywords(&keyword_line));
    let (detect_tx, mut detect_rx) = mpsc::channel::<String>(8);

    let d_kws = kws.clone();
    let d_stream = stream.clone();

    let mut mic = MicCapture::new();
    if let Err(e) = mic.start(move |samples: &[f32]| {
        d_stream.accept_waveform(SAMPLE_RATE as i32, samples);
        while d_kws.is_ready(&d_stream) {
            d_kws.decode(&d_stream);
        }

        if let Some(result) = d_kws.get_result(&d_stream) {
            if result.keyword.is_empty() { return; }
            info!("[wake] matched: keyword={}, json={}", result.keyword, result.json);
            d_kws.reset(&d_stream);
            let keyword = result.keyword.clone();
            let _ = detect_tx.try_send(keyword);
        }
    }) {
        error!("[wake] mic start failed: {}", e);
        let _ = app_handle.emit("wake:error",
            serde_json::json!({"code": "mic_unavailable", "message": e}));
        return false;
    }

    info!("[wake] detector started, keyword={}", word);

    loop {
        tokio::select! {
            detected = detect_rx.recv() => {
                match detected {
                    Some(kw) => {
                        info!("[wake] detected: {}", kw);
                        // Use timestamp-based pseudo-random to pick reply
                        let idx = (std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_millis() as usize) % WAKE_REPLIES.len();
                        let reply = WAKE_REPLIES[idx];
                        let _ = app_handle.emit("wake-word-detected",
                            serde_json::json!({"word": word, "reply": reply}));
                        play_wake_reply(reply).await;
                    }
                    None => break,
                }
            }
            _ = tokio::time::sleep(Duration::from_millis(500)) => {
                if stop.load(Ordering::SeqCst) { break; }
                if !mic.is_live() {
                    error!("[wake] mic stream lost (BT disconnected?)");
                    let _ = app_handle.emit("wake:error",
                        serde_json::json!({"code": "mic_lost", "message": "麦克风连接断开"}));
                    mic.stop();
                    return false;
                }
            }
        }
    }

    mic.stop();
    true
}
