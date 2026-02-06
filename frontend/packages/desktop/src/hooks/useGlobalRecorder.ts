import { useCallback, useEffect, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import { listen, UnlistenFn } from "@tauri-apps/api/event"
import { LearningService } from "@/client/sdk.gen"

interface GlobalEvent {
    timestamp: number
    event_type: string
    key?: string
    mouse_button?: string
    position?: [number, number]
    window_title?: string
    app_name?: string
    process_id?: number
}

interface UseGlobalRecorderOptions {
    threadId: string
    sessionId?: string | null
    enabled?: boolean
    autoFlushInterval?: number
}

export function useGlobalRecorder(options: UseGlobalRecorderOptions) {
    const {
        threadId,
        sessionId,
        enabled = false,
        autoFlushInterval = 2000
    } = options

    const [isRecording, setIsRecording] = useState(false)
    const [eventCount, setEventCount] = useState(0)
    const sessionIdRef = useRef(sessionId)
    useEffect(() => {
        sessionIdRef.current = sessionId
    }, [sessionId])

    const eventsBuffer = useRef<GlobalEvent[]>([])
    const flushTimerRef = useRef<number | null>(null)

    // Flush events to backend
    const flushEvents = useCallback(async () => {
        if (eventsBuffer.current.length === 0) return

        const events = [...eventsBuffer.current]
        eventsBuffer.current = []

        try {
            await LearningService.recordGlobalEvents({
                requestBody: {
                    thread_id: threadId,
                    session_id: sessionIdRef.current || undefined,
                    events: events
                }
            })
            setEventCount(prev => prev + events.length)
        } catch (error) {
            console.error("[GlobalRecorder] Failed to flush events:", error)
            // Re-add to buffer
            eventsBuffer.current = [...events, ...eventsBuffer.current]
        }
    }, [threadId])

    // Start/Stop recording via Rust
    const startRecording = useCallback(async () => {
        try {
            await invoke("start_global_recording")
            setEventCount(0)
            eventsBuffer.current = []
            setIsRecording(true)

            // Start flush timer
            flushTimerRef.current = window.setInterval(flushEvents, autoFlushInterval)
        } catch (err) {
            console.error("Failed to start global recording (likely not in Tauri):", err)
        }
    }, [autoFlushInterval, flushEvents])

    const stopRecording = useCallback(async () => {
        try {
            await invoke("stop_global_recording")
            setIsRecording(false)
            console.log("Stopped global recording")

            if (flushTimerRef.current) {
                clearInterval(flushTimerRef.current)
                flushTimerRef.current = null
            }
            // Final flush
            await flushEvents()
        } catch (err) {
            console.error("Failed to stop global recording:", err)
        }
    }, [flushEvents])

    // Listen to Rust events
    useEffect(() => {
        let unlisten: UnlistenFn | undefined

        const setupListener = async () => {
            if (!enabled) return

            try {
                unlisten = await listen<GlobalEvent>("global-event", (event) => {
                    if (isRecording) {
                        // Normalize timestamp if needed or rely on Rust's
                        eventsBuffer.current.push(event.payload)
                    }
                })
            } catch (err) {
                // Not in Tauri or listen failed
                console.warn("Failed to listen to global events (are you in a browser?)", err)
            }
        }

        setupListener()

        return () => {
            if (unlisten) unlisten()
        }
    }, [enabled, isRecording])

    // Cleanup
    useEffect(() => {
        return () => {
            if (flushTimerRef.current) clearInterval(flushTimerRef.current)
        }
    }, [])

    return {
        isRecording,
        startRecording,
        stopRecording,
        eventCount
    }
}
