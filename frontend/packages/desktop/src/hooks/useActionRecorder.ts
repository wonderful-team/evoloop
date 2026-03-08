/**
 * useActionRecorder - Hook for recording user actions for imitation learning.
 *
 * Captures UI events (clicks, inputs, etc.) and sends them to the backend
 * for storage as TraceEvent records.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { LearningService } from "@/client/sdk.gen"

declare global {
  interface Window {
    __TAURI__?: Record<string, unknown>
  }
}

interface RecordedEvent {
  timestamp: number
  event_type: string
  target_selector?: string
  target_text?: string
  payload?: Record<string, unknown>
  screenshot_base64?: string
}

interface UseActionRecorderOptions {
  threadId: string
  taskName?: string
  autoFlushInterval?: number // ms, default 5000
  enabled?: boolean
  scope?: "dom" | "global" | "both" // NEW: scope selection
  persistToBackend?: boolean // NEW: if false, events stay local until persistEvents() is called
}

interface UseActionRecorderReturn {
  isRecording: boolean
  startRecording: () => Promise<void>
  stopRecording: () => Promise<{ sessionId: string | null; eventCount: number } | undefined>
  recordEvent: (event: Omit<RecordedEvent, "timestamp">) => void
  eventCount: number
  sessionId: string | null
  persistEvents: () => Promise<boolean> // NEW: manually persist buffered events to backend
  getBufferedEvents: () => RecordedEvent[] // NEW: get local events without persisting
  clearBufferedEvents: () => void // NEW: clear local buffer
}

// Helper to get a CSS selector for an element
function getSelector(element: Element): string {
  if (element.id) return `#${element.id}`

  let path = ""
  let current: Element | null = element

  while (current && current !== document.body) {
    let selector = current.tagName.toLowerCase()

    if (current.id) {
      selector = `#${current.id}`
      path = selector + (path ? ` > ${path}` : "")
      break
    }

    if (current.className && typeof current.className === "string") {
      const classes = current.className.trim().split(/\s+/).slice(0, 2)
      if (classes.length > 0 && classes[0]) {
        selector += `.${classes.join(".")}`
      }
    }

    const parent: Element | null = current.parentElement
    if (parent) {
      const siblings = Array.from(parent.children).filter(
        (c: Element) => c.tagName === current?.tagName,
      )
      if (siblings.length > 1) {
        const index = siblings.indexOf(current) + 1
        selector += `:nth-of-type(${index})`
      }
    }

    path = selector + (path ? ` > ${path}` : "")
    current = parent
  }

  return path
}

export function useActionRecorder(
  options: UseActionRecorderOptions,
): UseActionRecorderReturn {
  const {
    threadId,
    taskName,
    autoFlushInterval = 5000,
    enabled = true,
    scope = "dom", // Default to DOM only
    persistToBackend = true, // Default to immediate persistence for backward compatibility
  } = options

  const [isRecording, setIsRecording] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [eventCount, setEventCount] = useState(0)
  const eventCountRef = useRef(0)

  const isRecordingRef = useRef(false)
  const eventsBuffer = useRef<RecordedEvent[]>([])
  const flushTimerRef = useRef<number | null>(null)
  const persistToBackendRef = useRef(persistToBackend)

  // Keep ref in sync with prop
  useEffect(() => {
    persistToBackendRef.current = persistToBackend
  }, [persistToBackend])

  // Flush events to backend
  const flushEvents = useCallback(async () => {
    if (!sessionId || eventsBuffer.current.length === 0) return

    // If not persisting to backend, just count locally
    if (!persistToBackendRef.current) {
      eventCountRef.current = eventsBuffer.current.length
      setEventCount(eventCountRef.current)
      return
    }

    const events = [...eventsBuffer.current]
    eventsBuffer.current = []

    try {
      await LearningService.recordEvents({
        requestBody: {
          session_id: sessionId,
          thread_id: threadId,
          events,
        },
      })
      eventCountRef.current += events.length
      setEventCount(eventCountRef.current)
    } catch (error) {
      console.error("[ActionRecorder] Failed to flush events:", error)
      // Re-add events to buffer on failure
      eventsBuffer.current = [...events, ...eventsBuffer.current]
    }
  }, [sessionId, threadId])

  // Start recording
  const startRecording = useCallback(async () => {
    if (isRecording) return

    try {
      const response = await LearningService.startRecording({
        requestBody: {
          thread_id: threadId,
          task_name: taskName,
        },
      })
      setSessionId(response.session_id)
      setIsRecording(true)
      isRecordingRef.current = true
      setEventCount(0)
      eventCountRef.current = 0
      eventsBuffer.current = []

      // Start auto-flush timer only if persisting to backend
      if (persistToBackendRef.current) {
        flushTimerRef.current = window.setInterval(flushEvents, autoFlushInterval)
      }
    } catch (error) {
      console.error("[ActionRecorder] Failed to start recording:", error)
      setIsRecording(false)
      isRecordingRef.current = false
    }
  }, [threadId, taskName, isRecording, autoFlushInterval, flushEvents])

  // Stop recording
  const stopRecording = useCallback(async () => {
    if (!isRecording) return undefined

    // Clear auto-flush timer
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

    const finalSessionId = sessionId
    const finalCount = eventCountRef.current

    // Only call stopRecording on backend if we were persisting
    if (persistToBackendRef.current && sessionId) {
      try {
        await LearningService.stopRecording({ sessionId })
      } catch (error) {
        console.error("[ActionRecorder] Failed to stop recording:", error)
      }
    }

    setIsRecording(false)
    isRecordingRef.current = false
    // Don't clear sessionId here - needed for persistEvents() later

    return { sessionId: finalSessionId, eventCount: finalCount }
  }, [isRecording, sessionId, flushEvents])

  // Record a single event
  const recordEvent = useCallback(
    (event: Omit<RecordedEvent, "timestamp">) => {
      if (!isRecordingRef.current) return

      eventsBuffer.current.push({
        ...event,
        timestamp: Date.now(),
      })
    },
    [],
  )

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
    if (!sessionId || eventsBuffer.current.length === 0) {
      console.log("[ActionRecorder] No events to persist")
      return false
    }

    const events = [...eventsBuffer.current]
    eventsBuffer.current = []

    try {
      await LearningService.recordEvents({
        requestBody: {
          session_id: sessionId,
          thread_id: threadId,
          events,
        },
      })
      eventCountRef.current += events.length
      setEventCount(eventCountRef.current)
      console.log(`[ActionRecorder] Persisted ${events.length} events to backend`)
      return true
    } catch (error) {
      console.error("[ActionRecorder] Failed to persist events:", error)
      // Re-add events to buffer on failure
      eventsBuffer.current = [...events, ...eventsBuffer.current]
      return false
    }
  }, [sessionId, threadId])

  // Auto-capture click events when recording
  useEffect(() => {
    if (!isRecording || !enabled || scope === "global") return

    const handleClick = async (e: MouseEvent) => {
      const target = e.target as Element
      if (!target) return

      let screenshotBase64: string | undefined

      // Capture screenshot via Tauri if available
      try {
        // Determine if running in Tauri environment (simple check)
        if (window.__TAURI__) {
          const { invoke } = await import("@tauri-apps/api/core")
          screenshotBase64 = await invoke<string>("capture_screenshot")
        }
      } catch (err) {
        console.warn("[ActionRecorder] Failed to capture screenshot:", err)
      }

      recordEvent({
        event_type: "click",
        target_selector: getSelector(target),
        target_text: target.textContent?.slice(0, 100),
        payload: {
          x: e.clientX,
          y: e.clientY,
          button: e.button,
        },
        screenshot_base64: screenshotBase64,
      })
    }

    const handleInput = (e: Event) => {
      const target = e.target as HTMLInputElement | HTMLTextAreaElement
      if (!target) return

      recordEvent({
        event_type: "input",
        target_selector: getSelector(target),
        payload: {
          value_length: target.value?.length,
          input_type: target.type,
        },
      })
    }

    document.addEventListener("click", handleClick, true)
    document.addEventListener("input", handleInput, true)

    return () => {
      document.removeEventListener("click", handleClick, true)
      document.removeEventListener("input", handleInput, true)
    }
  }, [isRecording, enabled, recordEvent])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (flushTimerRef.current) {
        clearInterval(flushTimerRef.current)
      }
    }
  }, [])

  return useMemo(() => ({
    isRecording,
    startRecording,
    stopRecording,
    recordEvent,
    eventCount,
    sessionId,
    persistEvents,
    getBufferedEvents,
    clearBufferedEvents,
  }), [isRecording, startRecording, stopRecording, recordEvent, eventCount, sessionId, persistEvents, getBufferedEvents, clearBufferedEvents])
}
