import { useEffect, useRef } from "react"
import { useRecordingStore } from "@/stores/recordingStore"
import { useActionRecorder } from "@/hooks/useActionRecorder"
import { useGlobalRecorder } from "@/hooks/useGlobalRecorder"
import { useScreenRecordingPermission } from "@/hooks/useScreenRecordingPermission"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import { listen } from "@tauri-apps/api/event"
import { invoke } from "@tauri-apps/api/core"
import { useNavigate } from "@tanstack/react-router"

export function GlobalRecorderManager() {
    const { t, i18n } = useTranslation()
    const navigate = useNavigate()
    const {
        isRecording: shouldRecord,
        activeThreadId,
        isGlobalMode,
        setEventCount,
        setSessionId,
        setVideoPath,
        postRecordingAction,
        stopRecording // to sync back if error
    } = useRecordingStore()

    const busyRef = useRef(false)

    // Sync static translations to tray
    useEffect(() => {
        invoke("sync_tray_translations", {
            showText: t("learning.tray.show", "Show Main Interface"),
            quitText: t("learning.tray.quit", "Quit")
        })
    }, [i18n.language, t])

    // Sync state to tray
    useEffect(() => {
        invoke("sync_tray_recording_state", {
            isRecording: shouldRecord,
            startText: t("learning.tray.startRecording", "Start Recording (⌘R)"),
            stopText: t("learning.tray.stopRecording", "Stop Recording (⌘R)")
        })
    }, [shouldRecord, i18n.language, t])

    // Listen for tray events
    useEffect(() => {
        console.log("[GlobalRecorderManager] Setting up tray listener")
        const unlisten = listen("tray-record-toggle", () => {
            console.log("[GlobalRecorderManager] Tray toggle received")
            const state = useRecordingStore.getState()
            if (state.isRecording) {
                state.setPostRecordingAction('synthesize')
                state.stopRecording()
            } else {
                state.startRecording("global")
            }
        })
        return () => {
            unlisten.then(f => f())
        }
    }, [])

    // Listen for watchdog auto-stop (timeout / size limit)
    useEffect(() => {
        const unlisten = listen<string>("recording-auto-stopped", (event) => {
            const reason = event.payload
            console.warn("[GlobalRecorderManager] Recording auto-stopped by watchdog:", reason)

            const state = useRecordingStore.getState()
            if (!state.isRecording) return

            // Show appropriate toast
            if (reason === "timeout") {
                toast.warning(t("learning.recordingAutoStoppedTimeout", "Recording stopped automatically: 10-minute limit reached."))
            } else if (reason === "size_limit") {
                toast.warning(t("learning.recordingAutoStoppedSize", "Recording stopped automatically: file size limit (500MB) reached."))
            } else {
                toast.warning(t("learning.recordingAutoStopped", "Recording was stopped automatically."))
            }

            // Trigger the same graceful stop flow as a manual tray stop
            state.setPostRecordingAction('synthesize')
            state.stopRecording()
        })
        return () => {
            unlisten.then(f => f())
        }
    }, [t])

    // We use the hooks here, but control them via the store's state
    const { hasPermission: hasVideoPermission, requestPermission: requestVideoPermission } = useScreenRecordingPermission()

    const domRecorder = useActionRecorder({
        threadId: activeThreadId || "",
        enabled: !!activeThreadId,
        scope: isGlobalMode ? "both" : "dom"
    })

    const globalRecorder = useGlobalRecorder({
        threadId: activeThreadId || "",
        sessionId: domRecorder.sessionId,
        enabled: isGlobalMode
    })

    // Sync event count to store
    useEffect(() => {
        setEventCount(domRecorder.eventCount + globalRecorder.eventCount)
    }, [domRecorder.eventCount, globalRecorder.eventCount, setEventCount])

    // Sync session ID to store (for dialogs)
    useEffect(() => {
        if (domRecorder.sessionId) {
            setSessionId(domRecorder.sessionId)
        }
    }, [domRecorder.sessionId, setSessionId])

    // Effect to Start/Stop based on store state
    useEffect(() => {
        const manageRecording = async () => {
            console.log("[GlobalRecorderManager] manageRecording triggered", { shouldRecord, isGlobalMode, activeThreadId, domRecIsRec: domRecorder.isRecording })
            // START
            if (shouldRecord) {
                if (!domRecorder.isRecording && !busyRef.current) {
                    busyRef.current = true
                    try {
                        // Permission is now handled at the Button level OR as a final safeguard here
                        if (hasVideoPermission === false) {
                            console.error("[GlobalRecorderManager] Final safeguard: screen recording permission missing")
                            // Button should have handled this, but if tray or other trigger hit:
                            requestVideoPermission()
                            stopRecording()
                            busyRef.current = false
                            return
                        }

                        console.log("[GlobalRecorderManager] Starting recorders...")
                        await domRecorder.startRecording()
                        if (isGlobalMode) {
                            await globalRecorder.startRecording()
                        }

                        // Start screen video recording
                        try {
                            const path = await invoke<string>("start_screen_recording")
                            setVideoPath(path)
                            console.log("[GlobalRecorderManager] Screen recording started:", path)
                        } catch (videoErr) {
                            console.error("[GlobalRecorderManager] Screen recording failed:", videoErr)
                            toast.error(t("learning.videoRecordingFailed", { error: videoErr }))
                        }

                        toast.info(t("learning.recordingStarted", "Recording started"))
                    } catch (e) {
                        console.error("Failed to start recording", e)
                        toast.error(t("learning.recordingFailed", "Failed to start"))
                        stopRecording()
                    } finally {
                        busyRef.current = false
                    }
                }
            }
            // STOP
            else {
                if (domRecorder.isRecording && !busyRef.current) {
                    busyRef.current = true
                    console.log("[GlobalRecorderManager] Stopping recorders...")
                    try {
                        let totalEventsCount = 0
                        if (isGlobalMode) {
                            const res = await globalRecorder.stopRecording()
                            if (res) totalEventsCount += res.eventCount
                        }
                        const domRes = await domRecorder.stopRecording()
                        if (domRes) totalEventsCount += domRes.eventCount

                        // Stop screen recording
                        let vPath: string | null = null
                        try {
                            vPath = await invoke<string>("stop_screen_recording")
                            console.log("[GlobalRecorderManager] Screen recording stopped:", vPath)
                        } catch (videoErr) {
                            console.warn("[GlobalRecorderManager] Screen recording stop failed:", videoErr)
                        }

                        if (totalEventsCount === 0) {
                            // If video exists but no events, or video is tiny, it's likely a permission issue
                            toast.warning(t("learning.noEvents", "No events captured, skipping skill creation."))
                            setSessionId(null)
                            setVideoPath(null)
                            busyRef.current = false
                            return
                        }

                        // Trigger backend extraction if we have a video and session
                        if (vPath && domRes?.sessionId) {
                            // Check if video is suspiciously small - usually indicates permission issue on Mac
                            // We can't check size easily via JS here, but we've added Rust logs.
                            // If it fails often, warn about Screen Recording perm.
                            fetch("/api/v1/learning/traces/extract-keyframes", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    session_id: domRes.sessionId,
                                    video_path: vPath,
                                    thread_id: activeThreadId,
                                }),
                            }).then(() => console.log("[GlobalRecorderManager] Keyframe extraction triggered"))
                                .catch(err => console.error("[GlobalRecorderManager] Failed to trigger extraction:", err))
                        }

                        toast.success(t("learning.recordingStopped", { count: totalEventsCount }))
                        if (domRes?.sessionId) setSessionId(domRes.sessionId)

                        // If it was triggered from tray, navigate to learning center
                        if (postRecordingAction === 'synthesize') {
                            navigate({ to: '/learning' })
                        }

                    } catch (e) {
                        console.error("Failed to stop recording", e)
                    } finally {
                        setVideoPath(null)
                        busyRef.current = false
                    }
                }
            }
        }

        manageRecording()
    }, [shouldRecord, isGlobalMode, activeThreadId, postRecordingAction, navigate]) // eslint-disable-line

    return null // Headless
}
