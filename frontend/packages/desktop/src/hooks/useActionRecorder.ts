/**
 * useActionRecorder - Hook for recording user actions for imitation learning.
 *
 * Captures UI events (clicks, inputs, etc.) and sends them to the backend
 * for storage as TraceEvent records.
 */

import { useCallback, useEffect, useRef, useState } from "react"
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
}

interface UseActionRecorderReturn {
  isRecording: boolean
  startRecording: () => Promise<void>
  stopRecording: () => Promise<string | undefined>
  recordEvent: (event: Omit<RecordedEvent, "timestamp">) => void
  eventCount: number
  sessionId: string | null
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
  } = options

  const [isRecording, setIsRecording] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [eventCount, setEventCount] = useState(0)

  const eventsBuffer = useRef<RecordedEvent[]>([])
  const flushTimerRef = useRef<number | null>(null)

  // Flush events to backend
  const flushEvents = useCallback(async () => {
    if (!sessionId || eventsBuffer.current.length === 0) return

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
      setEventCount((prev) => prev + events.length)
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
      setEventCount(0)
      eventsBuffer.current = []

      // Start auto-flush timer
      flushTimerRef.current = window.setInterval(flushEvents, autoFlushInterval)
    } catch (error) {
      console.error("[ActionRecorder] Failed to start recording:", error)
    }
  }, [threadId, taskName, isRecording, autoFlushInterval, flushEvents])

  // Stop recording
  const stopRecording = useCallback(async () => {
    if (!isRecording || !sessionId) return undefined

    // Clear auto-flush timer
    if (flushTimerRef.current) {
      clearInterval(flushTimerRef.current)
      flushTimerRef.current = null
    }

    // Flush remaining events
    await flushEvents()

    const currentSessionId = sessionId

    try {
      await LearningService.stopRecording({ sessionId })
    } catch (error) {
      console.error("[ActionRecorder] Failed to stop recording:", error)
    }

    setIsRecording(false)
    setSessionId(null)

    return currentSessionId
  }, [isRecording, sessionId, flushEvents])

  // Record a single event
  const recordEvent = useCallback(
    (event: Omit<RecordedEvent, "timestamp">) => {
      if (!isRecording) return

      eventsBuffer.current.push({
        ...event,
        timestamp: Date.now(),
      })
    },
    [isRecording],
  )

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

  return {
    isRecording,
    startRecording,
    stopRecording,
    recordEvent,
    eventCount,
    sessionId,
  }
}
