// 语音会话统一状态管理

import { create } from 'zustand';

export type VoiceSessionState =
  | 'idle'
  | 'listening'
  | 'speaking'
  | 'recognizing'
  | 'sending'
  | 'waiting'
  | 'playing'
  | 'error';

export interface VoiceSession {
  state: VoiceSessionState;
  partialText: string;
  finalText: string;
  volume: number;
  error: string | null;
  isWakeWordMode: boolean;
  isContinuousMode: boolean;
  isPressed: boolean;
}

interface VoiceSessionActions {
  reset: () => void;
  setState: (state: VoiceSessionState) => void;
  setPartialText: (text: string) => void;
  appendFinalText: (text: string) => void;
  clearFinalText: () => void;
  setVolume: (volume: number) => void;
  setError: (error: string | null) => void;
  setWakeWordMode: (enabled: boolean) => void;
  setContinuousMode: (enabled: boolean) => void;
  setPressed: (pressed: boolean) => void;
}

const initialState: VoiceSession = {
  state: 'idle',
  partialText: '',
  finalText: '',
  volume: 0,
  error: null,
  isWakeWordMode: false,
  isContinuousMode: false,
  isPressed: false,
};

export const useVoiceSessionStore = create<VoiceSession & VoiceSessionActions>((set) => ({
  ...initialState,

  reset: () => set(initialState),

  setState: (state) => set({ state }),

  setPartialText: (partialText) => set({ partialText }),

  appendFinalText: (text) => set((prev) => ({
    finalText: prev.finalText ? `${prev.finalText} ${text}` : text,
    partialText: '',
  })),

  clearFinalText: () => set({ finalText: '' }),

  setVolume: (volume) => set({ volume }),

  setError: (error) => set({ error }),

  setWakeWordMode: (isWakeWordMode) => set({ isWakeWordMode }),

  setContinuousMode: (isContinuousMode) => set({ isContinuousMode }),

  setPressed: (isPressed) => set({ isPressed }),
}));
