import { create } from "zustand"

interface RecordingState {
    isRecording: boolean
    isGlobalMode: boolean
    activeThreadId: string | null
    eventCount: number
    sessionId: string | null
    videoPath: string | null  // Screen recording video path (Two-Track Architecture)
    postRecordingAction: 'synthesize' | null
    // Local buffered events (for delayed persistence)
    localEvents: { domEvents: unknown[]; globalEvents: unknown[] }
    // Countdown state
    isPreparing: boolean
    countdown: number

    // Actions
    initiateRecording: (threadId: string) => void  // Start countdown
    startRecording: (threadId: string) => void     // Actually start (after countdown)
    stopRecording: () => void
    setEventCount: (count: number) => void
    setSessionId: (id: string | null) => void
    setIsGlobalMode: (isGlobal: boolean) => void
    setVideoPath: (path: string | null) => void
    setPostRecordingAction: (action: 'synthesize' | null) => void
    setLocalEvents: (domEvents: unknown[], globalEvents: unknown[]) => void
    clearLocalEvents: () => void
    setIsPreparing: (isPreparing: boolean) => void
    setCountdown: (countdown: number) => void
    reset: () => void
}

const COUNTDOWN_SECONDS = 3

export const useRecordingStore = create<RecordingState>((set, get) => ({
    isRecording: false,
    isGlobalMode: true,
    activeThreadId: null,
    eventCount: 0,
    sessionId: null,
    videoPath: null,
    postRecordingAction: null,
    localEvents: { domEvents: [], globalEvents: [] },
    isPreparing: false,
    countdown: 0,

    // Initiate recording with countdown
    initiateRecording: (threadId) => {
        set({ isPreparing: true, countdown: COUNTDOWN_SECONDS, activeThreadId: threadId })

        const runCountdown = () => {
            const state = get()
            if (!state.isPreparing) return // Cancelled

            if (state.countdown <= 1) {
                // Countdown complete, actually start recording
                get().startRecording(threadId)
            } else {
                // Continue countdown
                set({ countdown: state.countdown - 1 })
                setTimeout(runCountdown, 1000)
            }
        }

        setTimeout(runCountdown, 1000)
    },

    // Actually start recording (called after countdown)
    startRecording: (threadId) => set({
        isRecording: true,
        isPreparing: false,
        countdown: 0,
        activeThreadId: threadId,
        eventCount: 0,
        sessionId: null,
        videoPath: null,
        postRecordingAction: null,
        localEvents: { domEvents: [], globalEvents: [] }
    }),

    stopRecording: () => set({ isRecording: false, isPreparing: false, countdown: 0 }), // Manager will clear activeThreadId after cleanup if needed
    setEventCount: (count) => set({ eventCount: count }),
    setSessionId: (id) => set({ sessionId: id }),
    setIsGlobalMode: (isGlobal) => set({ isGlobalMode: isGlobal }),
    setVideoPath: (path) => set({ videoPath: path }),
    setPostRecordingAction: (action) => set({ postRecordingAction: action }),
    setLocalEvents: (domEvents, globalEvents) => set({ localEvents: { domEvents, globalEvents } }),
    clearLocalEvents: () => set({ localEvents: { domEvents: [], globalEvents: [] } }),
    setIsPreparing: (isPreparing) => set({ isPreparing }),
    setCountdown: (countdown) => set({ countdown }),
    reset: () => set({ isRecording: false, activeThreadId: null, eventCount: 0, sessionId: null, videoPath: null, postRecordingAction: null, localEvents: { domEvents: [], globalEvents: [] }, isPreparing: false, countdown: 0 })
}))
