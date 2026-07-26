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
  routeResult: Record<string, unknown> | null
  ttsSentence: string
  tokenBuffer: string
  dictationResult: string
  isDictating: boolean
  ttsSpeaking: boolean
  ttsLoading: boolean

  setVoiceMode: (mode: VoiceMode) => void
  cycleVoiceMode: () => void
  setVoiceState: (state: VoiceState) => void
  setPartialText: (text: string) => void
  setRouteResult: (result: Record<string, unknown>) => void
  setTtsSentence: (sentence: string) => void
  appendToken: (token: string) => void
  clearTokenBuffer: () => void
  setDictationResult: (text: string) => void
  setIsDictating: (v: boolean) => void
  setTtsSpeaking: (v: boolean) => void
  setTtsLoading: (v: boolean) => void
}

export const useVoiceStore = create<VoiceStoreState>((set) => ({
  voiceMode: "off",
  voiceState: "idle",
  partialText: "",
  routeResult: null,
  ttsSentence: "",
  tokenBuffer: "",
  dictationResult: "",
  isDictating: false,
  ttsSpeaking: false,
  ttsLoading: false,

  setVoiceMode: (voiceMode) => {
    if (voiceMode !== "off" && typeof window !== "undefined") {
      localStorage.setItem("evoloop_preferred_voice_mode", voiceMode)
    }
    set({ voiceMode })
  },
  cycleVoiceMode: () =>
    set((s) => {
      if (s.voiceMode !== "off") {
        return { voiceMode: "off" }
      } else {
        let preferred: VoiceMode = "dialogue"
        if (typeof window !== "undefined") {
          const stored = localStorage.getItem("evoloop_preferred_voice_mode")
          if (stored === "dictation" || stored === "dialogue") {
            preferred = stored
          }
        }
        return { voiceMode: preferred }
      }
    }),
  setVoiceState: (voiceState) => set({ voiceState }),
  setPartialText: (partialText) => set({ partialText }),
  setRouteResult: (routeResult) => set({ routeResult }),
  setTtsSentence: (ttsSentence) => set({ ttsSentence }),
  appendToken: (token) => set((s) => ({ tokenBuffer: s.tokenBuffer + token })),
  clearTokenBuffer: () => set({ tokenBuffer: "" }),
  setDictationResult: (dictationResult) => set({ dictationResult }),
  setIsDictating: (isDictating) => set({ isDictating }),
  setTtsSpeaking: (ttsSpeaking) => set({ ttsSpeaking }),
  setTtsLoading: (ttsLoading) => set({ ttsLoading }),
}))
