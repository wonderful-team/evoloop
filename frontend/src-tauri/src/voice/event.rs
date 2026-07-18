use serde_json::Value;

pub trait VoiceEventBus: Send + Sync {
    fn emit(&self, event: &str, payload: Value);
}
