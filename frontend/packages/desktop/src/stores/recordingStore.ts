import { create } from "zustand"

interface RecordingState {
    isRecording: boolean
    isGlobalMode: boolean
    activeThreadId: string | null
    eventCount: number
    sessionId: string | null
    videoPath: string | null  // Screen recording video path (Two-Track Architecture)
    postRecordingAction: 'synthesize' | null

    // Actions
    startRecording: (threadId: string) => void
    stopRecording: () => void
    setEventCount: (count: number) => void
    setSessionId: (id: string | null) => void
    setIsGlobalMode: (isGlobal: boolean) => void
    setVideoPath: (path: string | null) => void
    setPostRecordingAction: (action: 'synthesize' | null) => void
    reset: () => void
}

export const useRecordingStore = create<RecordingState>((set) => ({
    isRecording: false,
    isGlobalMode: false,
    activeThreadId: null,
    eventCount: 0,
    sessionId: null,
    videoPath: null,
    postRecordingAction: null,

    startRecording: (threadId) => set({ isRecording: true, activeThreadId: threadId, eventCount: 0, sessionId: null, videoPath: null, postRecordingAction: null }),
    stopRecording: () => set({ isRecording: false }), // Manager will clear activeThreadId after cleanup if needed
    setEventCount: (count) => set({ eventCount: count }),
    setSessionId: (id) => set({ sessionId: id }),
    setIsGlobalMode: (isGlobal) => set({ isGlobalMode: isGlobal }),
    setVideoPath: (path) => set({ videoPath: path }),
    setPostRecordingAction: (action) => set({ postRecordingAction: action }),
    reset: () => set({ isRecording: false, activeThreadId: null, eventCount: 0, sessionId: null, videoPath: null, postRecordingAction: null })
}))
