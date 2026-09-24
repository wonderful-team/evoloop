import {OpenAPI} from "@/client/core/OpenAPI"

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
  private reconnectAttempts = 0
  private maxReconnectAttempts = 10
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private isDisposed = false

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
    if (this.isDisposed) return

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

    sse.onmessage = (e) => {
      try {
        const event: SystemEvent = JSON.parse(e.data)
        this.emit(event.event, event)
      } catch (err) {
        console.error("[SystemSSE] Failed to parse event", err)
      }
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
  }

  public off(eventType: string, handler: EventHandler) {
    this.listeners.get(eventType)?.delete(handler)
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
