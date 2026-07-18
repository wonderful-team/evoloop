use std::sync::Arc;
use tokio::sync::RwLock;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoiceState {
    Idle,
    Listening,
    Processing,
    Speaking,
    Interrupted,
}

impl VoiceState {
    pub fn as_str(&self) -> &'static str {
        match self {
            VoiceState::Idle => "idle",
            VoiceState::Listening => "listening",
            VoiceState::Processing => "processing",
            VoiceState::Speaking => "speaking",
            VoiceState::Interrupted => "interrupted",
        }
    }
}

pub struct VoiceStateMachine {
    state: Arc<RwLock<VoiceState>>,
}

impl VoiceStateMachine {
    pub fn new() -> Self {
        Self {
            state: Arc::new(RwLock::new(VoiceState::Idle)),
        }
    }

    pub async fn get(&self) -> VoiceState {
        *self.state.read().await
    }

    pub async fn set(&self, new_state: VoiceState) -> bool {
        let mut current = self.state.write().await;
        let allowed = match *current {
            VoiceState::Idle => matches!(new_state, VoiceState::Listening),
            VoiceState::Listening => matches!(new_state, VoiceState::Processing | VoiceState::Idle),
            VoiceState::Processing => matches!(new_state, VoiceState::Speaking | VoiceState::Idle),
            VoiceState::Speaking => matches!(new_state, VoiceState::Idle | VoiceState::Interrupted),
            VoiceState::Interrupted => matches!(new_state, VoiceState::Listening | VoiceState::Idle),
        };
        if allowed {
            log::debug!(
                "[voice-sm] {} → {}",
                current.as_str(),
                new_state.as_str()
            );
            *current = new_state;
            true
        } else {
            log::warn!(
                "[voice-sm] illegal transition {} → {}",
                current.as_str(),
                new_state.as_str()
            );
            false
        }
    }

    pub async fn force_set(&self, new_state: VoiceState) {
        *self.state.write().await = new_state;
    }

    pub async fn is_speaking(&self) -> bool {
        *self.state.read().await == VoiceState::Speaking
    }

    pub async fn can_accept_route(&self) -> bool {
        let s = *self.state.read().await;
        matches!(s, VoiceState::Idle | VoiceState::Listening | VoiceState::Interrupted)
    }
}
