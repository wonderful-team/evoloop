import { useEffect } from "react"
import { useRecordingStore } from "@/stores/recordingStore"
import { useActionRecorder } from "@/hooks/useActionRecorder"
import { useGlobalRecorder } from "@/hooks/useGlobalRecorder"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import { listen } from "@tauri-apps/api/event"
import { invoke } from "@tauri-apps/api/core"

export function GlobalRecorderManager() {
    const { t, i18n } = useTranslation()
    const {
        isRecording: shouldRecord,
        activeThreadId,
        isGlobalMode,
        setEventCount,
        setSessionId,
        stopRecording // to sync back if error
    } = useRecordingStore()

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
                state.stopRecording()
            } else {
                state.startRecording("global")
            }
        })
        return () => {
            unlisten.then(f => f())
        }
    }, [])

    // We use the hooks here, but control them via the store's state
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
                if (!domRecorder.isRecording) {
                    try {
                        console.log("[GlobalRecorderManager] Starting DOM recorder...")
                        await domRecorder.startRecording()
                        if (isGlobalMode) {
                            console.log("[GlobalRecorderManager] Starting Global recorder...")
                            await globalRecorder.startRecording()
                        }
                        toast.info(t("learning.recordingStarted", "Recording started"))
                    } catch (e) {
                        console.error("Failed to start recording", e)
                        toast.error(t("learning.recordingFailed", "Failed to start"))
                        stopRecording()
                    }
                }
            }
            // STOP
            else {
                if (domRecorder.isRecording) {
                    console.log("[GlobalRecorderManager] Stopping recorders...")
                    try {
                        if (isGlobalMode) {
                            await globalRecorder.stopRecording()
                        }
                        const sid = await domRecorder.stopRecording()

                        const totalEvents = domRecorder.eventCount + globalRecorder.eventCount
                        if (totalEvents === 0) {
                            toast.warning(t("learning.noEvents", "No events captured, skipping skill creation."))
                            // Stop but don't set sessionId (so no dialog)
                            setSessionId(null)
                            return
                        }

                        toast.success(t("learning.recordingStopped", { count: totalEvents }))

                        if (sid) setSessionId(sid)

                    } catch (e) {
                        console.error("Failed to stop recording", e)
                    }
                }
            }
        }

        manageRecording()
    }, [shouldRecord, isGlobalMode, activeThreadId, /* deps for refs are stable */]) // eslint-disable-line

    return null // Headless
}
