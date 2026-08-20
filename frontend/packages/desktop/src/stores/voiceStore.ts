import { create } from "zustand"

export type VoiceMode = "off" | "dictation" | "dialogue"
export type VoiceState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "interrupted"

export interface VoiceStoreState {
  voiceMode: VoiceMode
  voiceState: VoiceState
  partialText: string
  ttsSentence: string
  tokenBuffer: string
  ttsSpeaking: boolean
  ttsLoading: boolean

  setVoiceMode: (mode: VoiceMode) => void
  setVoiceState: (state: VoiceState) => void
  setPartialText: (text: string) => void
  setTtsSentence: (sentence: string) => void
  appendToken: (token: string) => void
  clearTokenBuffer: () => void
  setTtsSpeaking: (v: boolean) => void
  setTtsLoading: (v: boolean) => void
}

export const useVoiceStore = create<VoiceStoreState>((set) => ({
  voiceMode: "off",
  voiceState: "idle",
  partialText: "",
  ttsSentence: "",
  tokenBuffer: "",
  ttsSpeaking: false,
  ttsLoading: false,

  setVoiceMode: (voiceMode) => {
    if (voiceMode !== "off" && typeof window !== "undefined") {
      localStorage.setItem("evoloop_preferred_voice_mode", voiceMode)
    }
    set({ voiceMode })
  },
  setVoiceState: (voiceState) => set({ voiceState }),
  setPartialText: (partialText) => set({ partialText }),
  setTtsSentence: (ttsSentence) => set({ ttsSentence }),
  appendToken: (token) => set((s) => ({ tokenBuffer: s.tokenBuffer + token })),
  clearTokenBuffer: () => set({ tokenBuffer: "" }),
  setTtsSpeaking: (ttsSpeaking) => set({ ttsSpeaking }),
  setTtsLoading: (ttsLoading) => set({ ttsLoading }),
}))
