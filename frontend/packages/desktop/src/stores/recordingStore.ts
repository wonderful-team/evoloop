import { create } from "zustand"

interface RecordingState {
    isRecording: boolean
    isGlobalMode: boolean
    activeThreadId: string | null
    eventCount: number
    sessionId: string | null

    // Actions
    startRecording: (threadId: string) => void
    stopRecording: () => void
    setEventCount: (count: number) => void
    setSessionId: (id: string | null) => void
    setIsGlobalMode: (isGlobal: boolean) => void
    reset: () => void
}

export const useRecordingStore = create<RecordingState>((set) => ({
    isRecording: false,
    isGlobalMode: false,
    activeThreadId: null,
    eventCount: 0,
    sessionId: null,

    startRecording: (threadId) => set({ isRecording: true, activeThreadId: threadId, eventCount: 0, sessionId: null }),
    stopRecording: () => set({ isRecording: false }), // Manager will clear activeThreadId after cleanup if needed
    setEventCount: (count) => set({ eventCount: count }),
    setSessionId: (id) => set({ sessionId: id }),
    setIsGlobalMode: (isGlobal) => set({ isGlobalMode: isGlobal }),
    reset: () => set({ isRecording: false, activeThreadId: null, eventCount: 0, sessionId: null })
}))
