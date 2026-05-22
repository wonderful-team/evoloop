import { create } from "zustand"
import { safeInvoke, isTauri } from "@/lib/tauri"

interface RecordingState {
    isRecording: boolean
    isDesktopRecording: boolean
    activeThreadId: string | null
    eventCount: number
    sessionId: string | null
    videoPath: string | null
    postRecordingAction: 'synthesize' | null
    isPreparing: boolean
    countdown: number

    recordingSource: 'desktop' | 'mobile'
    recordingSourceDeviceId: string | null
    recordingSourceSessionId: string | null
    recordingStartTime: number | null
    deviceResolution: { width: number, height: number } | null

    // Marker overlay state
    isMarkerOverlayOpen: boolean
    isAndroidMarkerOverlayOpen: boolean

    // Actions
    initiateRecording: (threadId: string, source?: 'desktop' | 'mobile', deviceId?: string, sessionId?: string, onBeforeStart?: () => Promise<void>) => void
    startRecording: (threadId: string, source?: 'desktop' | 'mobile', deviceId?: string, sessionId?: string) => void
    setRecordingSource: (source: 'desktop' | 'mobile', deviceId?: string | null) => void
    stopRecording: () => void
    setEventCount: (count: number) => void
    setSessionId: (id: string | null) => void
    setIsDesktopRecording: (enabled: boolean) => void
    setVideoPath: (path: string | null) => void
    setPostRecordingAction: (action: 'synthesize' | null) => void
    setIsPreparing: (isPreparing: boolean) => void
    setCountdown: (countdown: number) => void
    setDeviceResolution: (res: { width: number, height: number } | null) => void
    openMarkerOverlay: () => Promise<void>
    closeMarkerOverlay: () => Promise<void>
    openAndroidMarkerOverlay: () => Promise<void>
    closeAndroidMarkerOverlay: () => Promise<void>
    reset: () => void
}

const COUNTDOWN_SECONDS = 3

export const useRecordingStore = create<RecordingState>((set, get) => ({
    isRecording: false,
    isDesktopRecording: true,
    activeThreadId: null,
    eventCount: 0,
    sessionId: null,
    videoPath: null,
    postRecordingAction: null,
    isPreparing: false,
    countdown: 0,
    recordingSource: 'desktop',
    recordingSourceDeviceId: null,
    recordingSourceSessionId: null,
    recordingStartTime: null,
    deviceResolution: null,
    isMarkerOverlayOpen: false,
    isAndroidMarkerOverlayOpen: false,

    initiateRecording: (threadId, source = 'desktop', deviceId = undefined, sessionId = undefined, onBeforeStart = undefined) => {
        set({ isPreparing: true, countdown: COUNTDOWN_SECONDS, activeThreadId: threadId, recordingSource: source, recordingSourceDeviceId: deviceId, recordingSourceSessionId: sessionId })

        const runCountdown = async () => {
            const state = get()
            if (!state.isPreparing) return

            if (state.countdown <= 1) {
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
                console.log("[RecordingStore] Starting recording...")
                get().startRecording(threadId)
                console.log("[RecordingStore] Recording started, isRecording:", get().isRecording)
            } else {
                set({ countdown: state.countdown - 1 })
                setTimeout(runCountdown, 1000)
            }
        }

        setTimeout(runCountdown, 1000)
    },

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
            recordingSource: currentSource,
            recordingSourceDeviceId: currentDeviceId,
            recordingSourceSessionId: currentSessionId,
            recordingStartTime: Date.now()
        })
    },

    stopRecording: () => set({ isRecording: false, isPreparing: false, countdown: 0, recordingStartTime: null }),
    setEventCount: (count) => set({ eventCount: count }),
    setSessionId: (id) => set({ sessionId: id }),
    setRecordingSource: (source, deviceId = null) => set({ recordingSource: source, recordingSourceDeviceId: deviceId }),
    setIsDesktopRecording: (enabled) => set({ isDesktopRecording: enabled }),
    setVideoPath: (path) => set({ videoPath: path }),
    setPostRecordingAction: (action) => set({ postRecordingAction: action }),
    setIsPreparing: (isPreparing) => set({ isPreparing }),
    setCountdown: (countdown) => set({ countdown }),
    setDeviceResolution: (res) => set({ deviceResolution: res }),

    openMarkerOverlay: async () => {
        if (!isTauri()) return
        try {
            const result = await safeInvoke<string>("create_marker_overlay")
            console.log("[RecordingStore] Marker overlay:", result)
            set({ isMarkerOverlayOpen: true })
        } catch (err) {
            console.error("[RecordingStore] Failed to open marker overlay:", err)
        }
    },

    closeMarkerOverlay: async () => {
        if (!isTauri()) return
        try {
            const result = await safeInvoke<string>("close_marker_overlay")
            console.log("[RecordingStore] Marker overlay:", result)
            set({ isMarkerOverlayOpen: false })
        } catch (err) {
            console.error("[RecordingStore] Failed to close marker overlay:", err)
        }
    },

    openAndroidMarkerOverlay: async () => {
        if (!isTauri()) return
        try {
            const result = await safeInvoke<string>("create_android_marker_overlay")
            console.log("[RecordingStore] Android marker overlay:", result)
            set({ isAndroidMarkerOverlayOpen: true })
        } catch (err) {
            console.error("[RecordingStore] Failed to open Android marker overlay:", err)
        }
    },

    closeAndroidMarkerOverlay: async () => {
        if (!isTauri()) return
        try {
            const result = await safeInvoke<string>("close_android_marker_overlay")
            console.log("[RecordingStore] Android marker overlay:", result)
            set({ isAndroidMarkerOverlayOpen: false })
        } catch (err) {
            console.error("[RecordingStore] Failed to close Android marker overlay:", err)
        }
    },

    reset: () => set({
        isRecording: false,
        activeThreadId: null,
        eventCount: 0,
        sessionId: null,
        videoPath: null,
        postRecordingAction: null,
        isPreparing: false,
        countdown: 0,
        recordingSource: 'desktop',
        recordingSourceDeviceId: null,
        recordingSourceSessionId: null,
        recordingStartTime: null,
        deviceResolution: null,
        isMarkerOverlayOpen: false,
        isAndroidMarkerOverlayOpen: false
    })
}))
