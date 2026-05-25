import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { safeInvoke, safeListen } from "@/lib/tauri"
import type { UnlistenFn } from "@tauri-apps/api/event"
import { LearningService } from "@/client/sdk.gen"
import type { GlobalEventData } from "@/client/types.gen"

interface GlobalEvent {
    timestamp: number
    event_type: string  // "mouse_click" | "key_press"
    key?: string
    mouse_button?: string
    position?: [number, number]
    window_title?: string
    app_name?: string
    process_id?: number
    noPersist?: boolean // [NEW] If true, event increments count but is not sent to backend
    source?: string     // [NEW] Optional source override (e.g. "mobile" for mirror clicks)
}

interface UseGlobalRecorderOptions {
    threadId: string
    sessionId?: string | null
    enabled?: boolean
    autoFlushInterval?: number  // Batch flush interval in ms
    batchSize?: number          // Max events per batch
    transformEvent?: (event: GlobalEvent) => GlobalEvent | null // Optional transformation
    startTime?: number | null   // Optional start time for relative timestamps
}

export function useGlobalRecorder(options: UseGlobalRecorderOptions) {
    const {
        threadId,
        sessionId,
        enabled = false,
        autoFlushInterval = 500,   // 500ms batch flush (faster for real-time feel)
        batchSize = 50,             // Max 50 events per batch
        transformEvent,
        startTime
    } = options

    const transformEventRef = useRef(transformEvent)
    useEffect(() => {
        transformEventRef.current = transformEvent
    }, [transformEvent])

    const startTimeRef = useRef(startTime)
    useEffect(() => {
        startTimeRef.current = startTime
    }, [startTime])

    const [isRecording, setIsRecording] = useState(false)
    const isRecordingRef = useRef(false)
    const [eventCount, setEventCount] = useState(0)
    const eventCountRef = useRef(0)
    const sessionIdRef = useRef(sessionId)
    useEffect(() => {
        sessionIdRef.current = sessionId
    }, [sessionId])

    // Events buffer for batching
    const eventsBuffer = useRef<GlobalEvent[]>([])
    // Pending events queue for retry on failure
    const pendingQueue = useRef<GlobalEvent[]>([])
    const flushTimerRef = useRef<number | null>(null)
    const isFlushingRef = useRef(false)

    // Send events batch to backend
    const sendEventsBatch = useCallback(async (events: GlobalEvent[]): Promise<boolean> => {
        const currentSessionId = sessionIdRef.current
        if (!currentSessionId) {
            console.warn("[GlobalRecorder] No sessionId available yet, buffering events...")
            return false
        }

        try {
            // Convert events to API format
            const eventData: GlobalEventData[] = events.map(e => ({
                timestamp: e.timestamp,
                event_type: e.event_type,
                key: e.key,
                mouse_button: e.mouse_button,
                position: e.position,
                window_title: e.window_title,
                app_name: e.app_name,
                process_id: e.process_id,
                source: e.source
            }))

            const response = await LearningService.persistGlobalEvents({
                requestBody: {
                    session_id: currentSessionId,
                    thread_id: threadId,
                    events: eventData
                }
            })

            if (response.success) {
                console.log(`[GlobalRecorder] Persisted ${response.count} events`)
                return true
            } else {
                console.warn("[GlobalRecorder] Failed to persist events:", response.message)
                return false
            }
        } catch (err) {
            console.error("[GlobalRecorder] Error sending events:", err)
            return false
        }
    }, [threadId])

    // Flush events - sends to backend in batches
    const flushEvents = useCallback(async () => {
        if (isFlushingRef.current) return
        if (eventsBuffer.current.length === 0 && pendingQueue.current.length === 0) return

        isFlushingRef.current = true

        try {
            // First, add pending queue to buffer
            if (pendingQueue.current.length > 0) {
                eventsBuffer.current.unshift(...pendingQueue.current)
                pendingQueue.current = []
            }

            // Process in batches
            while (eventsBuffer.current.length > 0) {
                const batch = eventsBuffer.current.splice(0, batchSize)
                const success = await sendEventsBatch(batch)

                if (!success) {
                    // Put back in pending queue for retry
                    pendingQueue.current.push(...batch)
                    break
                }
            }
        } finally {
            isFlushingRef.current = false
        }
    }, [batchSize, sendEventsBatch])

    // Start/Stop recording via Rust
    const startRecording = useCallback(async () => {
        try {
            await safeInvoke("start_global_recording")
            setEventCount(0)
            eventCountRef.current = 0
            eventsBuffer.current = []
            pendingQueue.current = []
            setIsRecording(true)
            isRecordingRef.current = true

            // Start batch flush timer
            flushTimerRef.current = window.setInterval(flushEvents, autoFlushInterval)

            console.log("[GlobalRecorder] Started recording with batch persistence")
        } catch (err) {
            console.error("Failed to start global recording (likely not in Tauri):", err)
        }
    }, [autoFlushInterval, flushEvents])

    const stopRecording = useCallback(async () => {
        if (!isRecordingRef.current) {
            console.log("[GlobalRecorder] Already stopped, skipping")
            return undefined
        }

        try {
            await safeInvoke("stop_global_recording")
            setIsRecording(false)
            isRecordingRef.current = false
            console.log("[GlobalRecorder] Stopped recording")

            if (flushTimerRef.current) {
                clearInterval(flushTimerRef.current)
                flushTimerRef.current = null
            }

            // Final flush of remaining events
            if (eventsBuffer.current.length > 0 || pendingQueue.current.length > 0) {
                await flushEvents()
            }

            return { eventCount: eventCountRef.current }
        } catch (err) {
            console.error("Failed to stop global recording:", err)
        }
    }, [flushEvents])

    // Listen to Rust events
    useEffect(() => {
        if (!enabled) return

        let unlisten: UnlistenFn | undefined
        let cancelled = false

        const setupListener = async () => {
            try {
                const unlistenFn = await safeListen<GlobalEvent>("global-event", (event) => {
                    // Only buffer events when actually recording
                    if (isRecordingRef.current) {
                        // [v4] Skip events from marker overlay windows
                        const windowTitle = event.payload.window_title
                        if (windowTitle === "" || windowTitle?.includes("Marker Overlay")) {
                            return
                        }

                        let eventToRecord: GlobalEvent | null = event.payload

                        // [v5] Calculate relative timestamp if recording start time is known
                        if (startTimeRef.current) {
                            eventToRecord = {
                                ...eventToRecord,
                                timestamp: eventToRecord.timestamp - startTimeRef.current
                            }
                        }

                        if (transformEventRef.current) {
                            eventToRecord = transformEventRef.current(eventToRecord)
                        }

                        if (eventToRecord) {
                            // [v6] Handle noPersist flag: increments local count (for tray sync) but skips backend
                            if (!eventToRecord.noPersist) {
                                eventsBuffer.current.push(eventToRecord)
                            } else {
                                console.log("[GlobalRecorder] Event counted locally but skipping persistence (noPersist: true)")
                            }

                            eventCountRef.current += 1
                            setEventCount(eventCountRef.current)
                        }
                    }
                })

                if (cancelled) {
                    // Cleanup was called before setup completed, clean up now
                    unlistenFn()
                } else {
                    unlisten = unlistenFn
                }
            } catch (err) {
                console.warn("Failed to listen to global events (are you in a browser?)", err)
            }
        }

        setupListener()

        return () => {
            cancelled = true
            if (unlisten) unlisten()
        }
    }, [enabled])

    // Cleanup
    useEffect(() => {
        return () => {
            if (flushTimerRef.current) clearInterval(flushTimerRef.current)
        }
    }, [])

    // [DEPRECATED] Kept for API compatibility
    const getBufferedEvents = useCallback(() => {
        console.warn("[GlobalRecorder] getBufferedEvents() is deprecated. Events are now persisted automatically.")
        return [...eventsBuffer.current, ...pendingQueue.current]
    }, [])

    // Clear local buffers
    const clearBufferedEvents = useCallback(() => {
        eventsBuffer.current = []
        pendingQueue.current = []
        eventCountRef.current = 0
        setEventCount(0)
    }, [])

    // Persist remaining events (for explicit flush if needed)
    const persistEvents = useCallback(async () => {
        console.log("[GlobalRecorder] Explicit persistEvents() called")
        await flushEvents()
        return true
    }, [flushEvents])

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
