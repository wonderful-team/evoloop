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

    recordingSource: 'desktop' | 'mobile'
    recordingSourceDeviceId: string | null
    recordingSourceSessionId: string | null

    // Actions
    initiateRecording: (threadId: string, source?: 'desktop' | 'mobile', deviceId?: string, sessionId?: string, onBeforeStart?: () => Promise<void>) => void  // Start countdown
    startRecording: (threadId: string, source?: 'desktop' | 'mobile', deviceId?: string, sessionId?: string) => void     // Actually start (after countdown)
    setRecordingSource: (source: 'desktop' | 'mobile', deviceId?: string | null) => void
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
    recordingSource: 'desktop',
    recordingSourceDeviceId: null,
    recordingSourceSessionId: null,

    // Initiate recording with countdown
    initiateRecording: (threadId, source = 'desktop', deviceId = undefined, sessionId = undefined, onBeforeStart = undefined) => {
        set({ isPreparing: true, countdown: COUNTDOWN_SECONDS, activeThreadId: threadId, recordingSource: source, recordingSourceDeviceId: deviceId, recordingSourceSessionId: sessionId })

        const runCountdown = async () => {
            const state = get()
            if (!state.isPreparing) return // Cancelled

            if (state.countdown <= 1) {
                // Countdown complete, call onBeforeStart if provided (e.g., to start backend recording)
                if (onBeforeStart) {
                    try {
                        console.log("[RecordingStore] Calling onBeforeStart...")
                        await onBeforeStart()
                        console.log("[RecordingStore] onBeforeStart completed successfully")
                    } catch (e) {
                        console.error("[RecordingStore] onBeforeStart failed:", e)
                        set({ isPreparing: false, countdown: 0 })
                        return
                    }
                }
                // Actually start recording
                console.log("[RecordingStore] Starting recording...")
                get().startRecording(threadId)
                console.log("[RecordingStore] Recording started, isRecording:", get().isRecording)
            } else {
                // Continue countdown
                set({ countdown: state.countdown - 1 })
                setTimeout(runCountdown, 1000)
            }
        }

        setTimeout(runCountdown, 1000)
    },

    // Actually start recording (called after countdown)
    startRecording: (threadId, source, deviceId, sessionId) => {
        const currentSource = source || get().recordingSource
        const currentDeviceId = deviceId || get().recordingSourceDeviceId
        const currentSessionId = sessionId || get().recordingSourceSessionId
        set({
            isRecording: true,
            isPreparing: false,
            countdown: 0,
            activeThreadId: threadId,
            eventCount: 0,
            sessionId: null,
            videoPath: null,
            postRecordingAction: null,
            localEvents: { domEvents: [], globalEvents: [] },
            recordingSource: currentSource,
            recordingSourceDeviceId: currentDeviceId,
            recordingSourceSessionId: currentSessionId
        })
    },

    stopRecording: () => set({ isRecording: false, isPreparing: false, countdown: 0 }), // Manager will clear activeThreadId after cleanup if needed
    setEventCount: (count) => set({ eventCount: count }),
    setSessionId: (id) => set({ sessionId: id }),
    setRecordingSource: (source, deviceId = null) => set({ recordingSource: source, recordingSourceDeviceId: deviceId }),
    setIsGlobalMode: (isGlobal) => set({ isGlobalMode: isGlobal }),
    setVideoPath: (path) => set({ videoPath: path }),
    setPostRecordingAction: (action) => set({ postRecordingAction: action }),
    setLocalEvents: (domEvents, globalEvents) => set({ localEvents: { domEvents, globalEvents } }),
    clearLocalEvents: () => set({ localEvents: { domEvents: [], globalEvents: [] } }),
    setIsPreparing: (isPreparing) => set({ isPreparing }),
    setCountdown: (countdown) => set({ countdown }),
    reset: () => set({ isRecording: false, activeThreadId: null, eventCount: 0, sessionId: null, videoPath: null, postRecordingAction: null, localEvents: { domEvents: [], globalEvents: [] }, isPreparing: false, countdown: 0, recordingSource: 'desktop', recordingSourceDeviceId: null, recordingSourceSessionId: null })
}))
