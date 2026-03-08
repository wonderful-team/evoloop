import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import { listen, UnlistenFn } from "@tauri-apps/api/event"
import { LearningService } from "@/client/sdk.gen"

interface Modifiers {
    alt: boolean
    ctrl: boolean
    meta: boolean
    shift: boolean
}

interface GlobalEvent {
    timestamp: number
    event_type: string  // "mouse_click" | "mouse_click_extract" | "key_press"
    key?: string
    mouse_button?: string
    position?: [number, number]
    window_title?: string
    app_name?: string
    process_id?: number
    modifiers?: Modifiers
}

interface UseGlobalRecorderOptions {
    threadId: string
    sessionId?: string | null
    enabled?: boolean
    autoFlushInterval?: number
    persistToBackend?: boolean // NEW: if false, events stay local until persistEvents() is called
}

export function useGlobalRecorder(options: UseGlobalRecorderOptions) {
    const {
        threadId,
        sessionId,
        enabled = false,
        autoFlushInterval = 2000,
        persistToBackend = true
    } = options

    const [isRecording, setIsRecording] = useState(false)
    const isRecordingRef = useRef(false)
    const [eventCount, setEventCount] = useState(0)
    const eventCountRef = useRef(0)
    const sessionIdRef = useRef(sessionId)
    useEffect(() => {
        sessionIdRef.current = sessionId
    }, [sessionId])

    const eventsBuffer = useRef<GlobalEvent[]>([])
    const flushTimerRef = useRef<number | null>(null)
    const persistToBackendRef = useRef(persistToBackend)

    // Keep ref in sync with prop
    useEffect(() => {
        persistToBackendRef.current = persistToBackend
    }, [persistToBackend])

    // Flush events to backend
    const flushEvents = useCallback(async () => {
        if (eventsBuffer.current.length === 0) return

        // If not persisting to backend, just count locally
        if (!persistToBackendRef.current) {
            eventCountRef.current = eventsBuffer.current.length
            setEventCount(eventCountRef.current)
            return
        }

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
            eventCountRef.current += events.length
            setEventCount(eventCountRef.current)
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
            eventCountRef.current = 0
            eventsBuffer.current = []
            setIsRecording(true)
            isRecordingRef.current = true

            // Start flush timer only if persisting to backend
            if (persistToBackendRef.current) {
                flushTimerRef.current = window.setInterval(flushEvents, autoFlushInterval)
            }
        } catch (err) {
            console.error("Failed to start global recording (likely not in Tauri):", err)
        }
    }, [autoFlushInterval, flushEvents])

    const stopRecording = useCallback(async () => {
        try {
            await invoke("stop_global_recording")
            setIsRecording(false)
            isRecordingRef.current = false
            console.log("Stopped global recording")

            if (flushTimerRef.current) {
                clearInterval(flushTimerRef.current)
                flushTimerRef.current = null
            }

            // Only flush if persisting to backend
            if (persistToBackendRef.current) {
                await flushEvents()
            } else {
                // Update count to reflect buffered events
                eventCountRef.current = eventsBuffer.current.length
                setEventCount(eventCountRef.current)
            }

            return { eventCount: eventCountRef.current }
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
                    if (isRecordingRef.current) {
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

    // NEW: Get buffered events without clearing
    const getBufferedEvents = useCallback(() => {
        return [...eventsBuffer.current]
    }, [])

    // NEW: Clear buffered events
    const clearBufferedEvents = useCallback(() => {
        eventsBuffer.current = []
        eventCountRef.current = 0
        setEventCount(0)
    }, [])

    // NEW: Manually persist events to backend
    const persistEvents = useCallback(async () => {
        if (!sessionIdRef.current || eventsBuffer.current.length === 0) {
            console.log("[GlobalRecorder] No events to persist")
            return false
        }

        const events = [...eventsBuffer.current]
        eventsBuffer.current = []

        try {
            await LearningService.recordGlobalEvents({
                requestBody: {
                    thread_id: threadId,
                    session_id: sessionIdRef.current,
                    events: events
                }
            })
            eventCountRef.current += events.length
            setEventCount(eventCountRef.current)
            console.log(`[GlobalRecorder] Persisted ${events.length} events to backend`)
            return true
        } catch (error) {
            console.error("[GlobalRecorder] Failed to persist events:", error)
            // Re-add to buffer
            eventsBuffer.current = [...events, ...eventsBuffer.current]
            return false
        }
    }, [threadId])

    return useMemo(() => ({
        isRecording,
        startRecording,
        stopRecording,
        eventCount,
        persistEvents,
        getBufferedEvents,
        clearBufferedEvents
    }), [isRecording, startRecording, stopRecording, eventCount, persistEvents, getBufferedEvents, clearBufferedEvents])
}
