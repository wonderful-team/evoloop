/**
 * useActionRecorder - Hook for recording user actions for imitation learning.
 *
 * Captures UI events (clicks, inputs, etc.) and sends them to the backend
 * for storage as TraceEvent records (unified with Android mirror recording).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { LearningService } from "@/client/sdk.gen"
import type { DomEventData } from "@/client/types.gen"
import { useRecordingStore } from "@/stores/recordingStore"

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
  autoFlushInterval?: number // ms, default 500
  batchSize?: number         // max events per batch, default 50
  enabled?: boolean
  scope?: "dom" | "global" | "both"
}

interface UseActionRecorderReturn {
  isRecording: boolean
  startRecording: () => Promise<string | null>
  stopRecording: () => Promise<{ sessionId: string | null; eventCount: number } | undefined>
  recordEvent: (event: Omit<RecordedEvent, "timestamp">) => void
  eventCount: number
  sessionId: string | null
  persistEvents: () => Promise<boolean> // Final flush of remaining events
  getBufferedEvents: () => RecordedEvent[] // Get local buffer (for debugging)
  clearBufferedEvents: () => void
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
    autoFlushInterval = 500,  // 500ms batch flush
    batchSize = 50,           // Max 50 events per batch
    enabled = true,
    scope = "dom",
  } = options

  const [isRecording, setIsRecording] = useState(false)
  const [sessionId, setSessionIdState] = useState<string | null>(null)
  const [eventCount, setEventCount] = useState(0)
  const eventCountRef = useRef(0)

  const recordingStartTime = useRecordingStore(state => state.recordingStartTime)
  const recordingStartTimeRef = useRef<number | null>(null)

  // Sync recordingStartTime to ref for async access
  useEffect(() => {
    recordingStartTimeRef.current = recordingStartTime
  }, [recordingStartTime])

  const isRecordingRef = useRef(false)
  const eventsBuffer = useRef<RecordedEvent[]>([])
  const pendingQueue = useRef<RecordedEvent[]>([])
  const flushTimerRef = useRef<number | null>(null)
  const isFlushingRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)

  // Sync state to ref for async access
  const setSessionId = useCallback((id: string | null) => {
    sessionIdRef.current = id
    setSessionIdState(id)
  }, [])

  // Send events batch to backend
  const sendEventsBatch = useCallback(async (events: RecordedEvent[]): Promise<boolean> => {
    const currentSessionId = sessionIdRef.current
    if (!currentSessionId) {
      console.error("[ActionRecorder] No sessionId available")
      return false
    }

    try {
      // Convert events to API format
      const eventData: DomEventData[] = events.map(e => {
        const payload = e.payload || {}
        return {
          timestamp: e.timestamp,
          event_type: e.event_type,
          selector: e.target_selector,
          target_text: e.target_text,
          value: payload.value as string || payload.input_value as string,
          url: payload.url as string || window.location.href,
          xpath: payload.xpath as string,
          coordinates: payload.x !== undefined ? {
            x: payload.x as number,
            y: payload.y as number,
            width: payload.width as number,
            height: payload.height as number,
          } : undefined,
        }
      })

      const response = await LearningService.persistDomEvents({
        requestBody: {
          session_id: currentSessionId,
          thread_id: threadId,
          events: eventData
        }
      })

      if (response.success) {
        console.log(`[ActionRecorder] Persisted ${response.count} events`)
        return true
      } else {
        console.warn("[ActionRecorder] Failed to persist events:", response.message)
        return false
      }
    } catch (err) {
      console.error("[ActionRecorder] Error sending events:", err)
      return false
    }
  }, [sessionId, threadId])

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

  // Start recording
  const startRecording = useCallback(async (): Promise<string | null> => {
    if (isRecording) return null

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
      pendingQueue.current = []

      // Start batch flush timer
      flushTimerRef.current = window.setInterval(flushEvents, autoFlushInterval)

      console.log("[ActionRecorder] Started recording with batch persistence, sessionId:", response.session_id)
      return response.session_id
    } catch (error) {
      console.error("[ActionRecorder] Failed to start recording:", error)
      setIsRecording(false)
      isRecordingRef.current = false
      return null
    }
  }, [threadId, taskName, isRecording, autoFlushInterval, flushEvents])

  // Stop recording
  const stopRecording = useCallback(async () => {
    if (!isRecordingRef.current) return undefined

    // Clear auto-flush timer
    if (flushTimerRef.current) {
      clearInterval(flushTimerRef.current)
      flushTimerRef.current = null
    }

    // Final flush of remaining events
    if (eventsBuffer.current.length > 0 || pendingQueue.current.length > 0) {
      await flushEvents()
    }

    const finalSessionId = sessionId
    const finalCount = eventCountRef.current

    // Call stopRecording on backend
    if (sessionId) {
      try {
        await LearningService.stopRecording({ sessionId })
      } catch (error) {
        console.error("[ActionRecorder] Failed to stop recording:", error)
      }
    }

    setIsRecording(false)
    isRecordingRef.current = false

    return { sessionId: finalSessionId, eventCount: finalCount }
  }, [sessionId, flushEvents])

  // Record a single event
  const recordEvent = useCallback(
    (event: Omit<RecordedEvent, "timestamp">) => {
      if (!isRecordingRef.current) return

      const now = Date.now()
      const startTime = recordingStartTimeRef.current || now
      const relativeTimestamp = now - startTime

      eventsBuffer.current.push({
        ...event,
        timestamp: relativeTimestamp,  // Relative milliseconds from recording start
      })
    },
    [],
  )

  // Get buffered events (for debugging)
  const getBufferedEvents = useCallback(() => {
    return [...eventsBuffer.current, ...pendingQueue.current]
  }, [])

  // Clear buffered events
  const clearBufferedEvents = useCallback(() => {
    eventsBuffer.current = []
    pendingQueue.current = []
    eventCountRef.current = 0
    setEventCount(0)
  }, [])

  // Persist remaining events (explicit flush)
  const persistEvents = useCallback(async () => {
    console.log("[ActionRecorder] Explicit persistEvents() called")
    await flushEvents()
    return true
  }, [flushEvents])

  // Auto-capture click events when recording
  useEffect(() => {
    if (!isRecording || !enabled || scope === "global") return

    const handleClick = async (e: MouseEvent) => {
      const target = e.target as Element
      if (!target) return

      let screenshotBase64: string | undefined

      // Capture screenshot via Tauri if available
      try {
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
          url: window.location.href,
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
          input_value: target.value?.slice(0, 100),
          url: window.location.href,
        },
      })
    }

    document.addEventListener("click", handleClick, true)
    document.addEventListener("input", handleInput, true)

    return () => {
      document.removeEventListener("click", handleClick, true)
      document.removeEventListener("input", handleInput, true)
    }
  }, [isRecording, enabled, recordEvent, scope])

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
