import { OpenAPI } from "@/client/core/OpenAPI"

export interface SystemEvent {
  type: string
  event: string
  thread_id?: string | null
  timestamp: string
  source: string
  data: any
}

type EventHandler = (event: SystemEvent) => void

class SystemSSEClient {
  private static instance: SystemSSEClient
  private eventSource: EventSource | null = null
  private listeners: Map<string, Set<EventHandler>> = new Map()
  private esListeners: Map<string, (e: MessageEvent) => void> = new Map()
  private reconnectAttempts = 0
  private maxReconnectAttempts = 10
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private isDisposed = false
  private lastEventId: string | null = null
  private connecting = false

  private constructor() {
    this.connect()
  }

  public static getInstance(): SystemSSEClient {
    if (!SystemSSEClient.instance) {
      SystemSSEClient.instance = new SystemSSEClient()
    }
    return SystemSSEClient.instance
  }

  private async connect() {
    if (this.isDisposed || this.connecting) return
    this.connecting = true

    this.disconnect(false)

    let token: string | undefined
    try {
      token =
        typeof OpenAPI.TOKEN === "function"
          ? await (OpenAPI.TOKEN as any)()
          : OpenAPI.TOKEN
    } catch (e) {
      console.warn("[SystemSSE] Failed to retrieve auth token", e)
    }

    let url = `${OpenAPI.BASE}/api/v1/stream/system`
    const params = new URLSearchParams()
    if (token) {
      params.append("token", token)
    }

    const guestId = localStorage.getItem("evoloop-guest-id")
    if (guestId) {
      params.append("guest_id", guestId)
    }

    // Manual reconnect / page remount: resume from the last seen event id so
    // the server only replays events after the disconnect window.
    if (this.lastEventId) {
      params.append("last_event_id", this.lastEventId)
    }

    const queryString = params.toString()
    if (queryString) {
      url += `?${queryString}`
    }

    console.log(`[SystemSSE] Connecting to ${url}`)

    try {
      this.eventSource = new EventSource(url, { withCredentials: true })
      this.setupListeners(this.eventSource)
    } catch (e) {
      console.error("[SystemSSE] Failed to create EventSource", e)
      this.scheduleReconnect()
    } finally {
      this.connecting = false
    }
  }

  private setupListeners(sse: EventSource) {
    sse.onopen = () => {
      console.log("[SystemSSE] Connected")
      this.reconnectAttempts = 0
    }

    sse.onerror = (e) => {
      console.warn(
        "[SystemSSE] Connection error",
        e,
        "readyState:",
        sse.readyState,
      )

      if (sse.readyState === EventSource.CLOSED) {
        this.scheduleReconnect()
      }
    }

    // Backend sends named events (event: <type>). Register a listener for each
    // event type that currently has subscribers; new subscribers are wired
    // dynamically in on().
    this.esListeners.forEach((listener, eventType) => {
      sse.addEventListener(eventType, listener)
    })

    // Legacy fallback: unnamed events (no event: field) go through onmessage.
    sse.onmessage = (e) => {
      this.handleEventData(e.data, (e as any).lastEventId)
    }
  }

  private handleEventData(rawData: string, lastEventId?: string) {
    try {
      const event: SystemEvent = JSON.parse(rawData)
      if (lastEventId) {
        this.lastEventId = lastEventId
      }
      // Route by the semantic event name; fall back to type for direct payloads.
      const eventType = event.event || event.type
      if (eventType) {
        this.emit(eventType, event)
      }
    } catch (err) {
      console.error("[SystemSSE] Failed to parse event", err)
    }
  }

  private scheduleReconnect() {
    if (this.isDisposed) return
    if (this.reconnectTimer) return
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error("[SystemSSE] Max reconnect attempts reached")
      return
    }

    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000)
    console.log(`[SystemSSE] Reconnecting in ${delay}ms`)

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.reconnectAttempts++
      this.connect()
    }, delay)
  }

  public on(eventType: string, handler: EventHandler) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set())
    }
    this.listeners.get(eventType)!.add(handler)

    // Wire a named EventSource listener the first time this event type is used.
    if (!this.esListeners.has(eventType)) {
      const listener = (e: MessageEvent) => {
        this.handleEventData(e.data, (e as any).lastEventId)
      }
      this.esListeners.set(eventType, listener)
      this.eventSource?.addEventListener(eventType, listener)
    }
  }

  public off(eventType: string, handler: EventHandler) {
    this.listeners.get(eventType)?.delete(handler)
    if (!this.listeners.get(eventType)?.size) {
      this.listeners.delete(eventType)
      const listener = this.esListeners.get(eventType)
      if (listener) {
        this.eventSource?.removeEventListener(eventType, listener)
        this.esListeners.delete(eventType)
      }
    }
  }

  private emit(eventType: string, event: SystemEvent) {
    this.listeners.get(eventType)?.forEach((handler) => {
      try {
        handler(event)
      } catch (err) {
        console.error(`[SystemSSE] Handler error for ${eventType}:`, err)
      }
    })
  }

  public disconnect(permanent = false) {
    if (permanent) {
      this.isDisposed = true
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
  }
}

export const systemSSEClient = SystemSSEClient.getInstance()
