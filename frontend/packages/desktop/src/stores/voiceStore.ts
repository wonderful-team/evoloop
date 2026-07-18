import { create } from "zustand"

export type VoiceState = "idle" | "listening" | "processing" | "speaking" | "interrupted"

export interface VoiceStoreState {
  voiceState: VoiceState
  partialText: string
  routeResult: Record<string, unknown> | null
  ttsSentence: string
  tokenBuffer: string
  dictationResult: string
  isDictating: boolean

  setVoiceState: (state: VoiceState) => void
  setPartialText: (text: string) => void
  setRouteResult: (result: Record<string, unknown>) => void
  setTtsSentence: (sentence: string) => void
  appendToken: (token: string) => void
  clearTokenBuffer: () => void
  setDictationResult: (text: string) => void
  setIsDictating: (v: boolean) => void
}

export const useVoiceStore = create<VoiceStoreState>((set) => ({
  voiceState: "idle",
  partialText: "",
  routeResult: null,
  ttsSentence: "",
  tokenBuffer: "",
  dictationResult: "",
  isDictating: false,

  setVoiceState: (voiceState) => set({ voiceState }),
  setPartialText: (partialText) => set({ partialText }),
  setRouteResult: (routeResult) => set({ routeResult }),
  setTtsSentence: (ttsSentence) => set({ ttsSentence }),
  appendToken: (token) =>
    set((s) => ({ tokenBuffer: s.tokenBuffer + token })),
  clearTokenBuffer: () => set({ tokenBuffer: "" }),
  setDictationResult: (dictationResult) => set({ dictationResult }),
  setIsDictating: (isDictating) => set({ isDictating }),
}))
