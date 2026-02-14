import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { DevicesService } from "../client"

const WS_URL = import.meta.env.VITE_EVOLOOP_WS_URL || "wss://mall.imagicbox.cn/wss/"

// Debug/Trace Log (for expandable thought/tool views)
export interface LogMessage {
  type: "ai" | "thought" | "tool" | "output" | "error" | "user" | "hitl_request" | "model"
  role?: "user" | "assistant" | "model"
  content: any
  thread_id?: string
  project_id?: number
  log_id?: number
  timestamp: number
}

// Helper to normalize message timestamps and roles
export const normalizeLogMessage = (m: any): LogMessage => {
  let type = m.type
  let role = m.role

  if (m.role) {
    type = m.role === 'user' ? 'user' : 'ai'
    role = m.role
  }

  if (m.type === 'model') {
    role = 'assistant'
    type = 'ai'
  }

  // Robust timestamp normalization
  let timestamp = Date.now()
  if (m.timestamp) {
    timestamp = m.timestamp > 1e11 ? m.timestamp : m.timestamp * 1000
  } else if (m.create_time) {
    const ct = m.create_time
    timestamp = ct > 1e11 ? ct : ct * 1000
  } else if (m.created_at) {
    const d = new Date(m.created_at)
    if (!isNaN(d.getTime())) {
      timestamp = d.getTime()
    }
  }

  return {
    ...m,
    type,
    role,
    timestamp
  }
}

export function useEvoLoopWebSocket(deviceId: number | null) {
  const { t } = useTranslation()
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<LogMessage[]>([])  // Unified logs
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<any>(null)
  const retryCountRef = useRef(0)

  const addMessage = useCallback((msg: LogMessage) => {
    setMessages((prev) => {
      if (msg.type === 'user') {
        const isDup = prev.some(m => m.type === 'user' && m.content === msg.content && Math.abs(m.timestamp - msg.timestamp) < 10000)
        if (isDup) return prev
      }
      return [...prev, msg]
    })
  }, [])

  const connect = useCallback(() => {
    if (!deviceId) return

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }

    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        console.log("[EvoLoop] WS Connected")
        setIsConnected(true)
        retryCountRef.current = 0
      }

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === "init") {
            const clientId = data.data.client_id
            console.log("[EvoLoop] Got client_id:", clientId)
            try {
              await DevicesService.bindMobile(clientId)
              console.log("[EvoLoop] Mobile Bound")
            } catch (e) {
              console.error("[EvoLoop] Bind failed", e)
              toast.error(t("toast.bindFailed"))
            }
          } else if (data.type === "ping") {
            // ignore
          } else if (data.type === "new_logs") {
            const logs = data.data.logs || []
            const batchProjectId = data.data.project_id
            if (Array.isArray(logs)) {
              setMessages((prev) => {
                const formattedLogs = logs.map((log: any) => {
                  const normalized = normalizeLogMessage(log)
                  // Apply batchProjectId if individual log doesn't have one
                  if (!normalized.project_id && batchProjectId) {
                    normalized.project_id = batchProjectId
                  }
                  return normalized
                })

                // Deduplicate incoming logs against existing
                // 1. By log_id (Priority)
                // 2. By content + role if log_id is missing (To catch matched optimistic user messages)
                const newLogs = formattedLogs.filter((nl) => {
                  // Check if log_id already exists
                  if (nl.log_id && prev.some((pl) => pl.log_id && pl.log_id === nl.log_id)) return false

                  // If it's a user message from server, check if we have a matching optimistic message (no log_id)
                  // We allow a small time window for matching
                  if (nl.type === 'user' || nl.role === 'user') {
                    const matchIdx = prev.findIndex(pl =>
                      !pl.log_id &&
                      pl.role === nl.role &&
                      pl.content === nl.content &&
                      Math.abs(pl.timestamp - nl.timestamp) < 30000 // 30s window
                    )
                    if (matchIdx !== -1) {
                      // Replace the optimistic message with the server one to get the log_id
                      prev[matchIdx] = nl
                      return false
                    }
                  }

                  return true
                })
                return [...prev, ...newLogs]
              })
            }
          } else if (
            ["thought", "tool", "output", "error", "hitl_request", "model"].includes(data.type)
          ) {
            setMessages((prev) => {
              const normalized = normalizeLogMessage(data)

              // Deduplicate single incoming log
              if (normalized.log_id && prev.some(pl => pl.log_id === normalized.log_id)) return prev

              // Check for matching optimistic
              if (normalized.role === 'user') {
                const matchIdx = prev.findIndex(pl =>
                  !pl.log_id &&
                  pl.role === normalized.role &&
                  pl.content === normalized.content &&
                  Math.abs(pl.timestamp - normalized.timestamp) < 30000
                )
                if (matchIdx !== -1) {
                  const updated = [...prev]
                  updated[matchIdx] = normalized
                  return updated
                }
              }

              return [...prev, normalized]
            })
          }
        } catch (e) {
          console.error("[EvoLoop] WS Parse Error", e)
        }
      }

      ws.onclose = () => {
        console.log("[EvoLoop] WS Closed")
        setIsConnected(false)

        // Exponential backoff
        const delay = Math.min(30000, 1000 * Math.pow(2, retryCountRef.current))
        console.log(`[EvoLoop] Reconnecting in ${delay}ms (attempt ${retryCountRef.current + 1})`)
        retryCountRef.current += 1
        reconnectTimeoutRef.current = setTimeout(connect, delay)
      }

      ws.onerror = (e) => {
        console.error("[EvoLoop] WS Error", e)
      }
    } catch (e) {
      console.error("[EvoLoop] Connection failed", e)
    }
  }, [deviceId, t])

  useEffect(() => {
    if (deviceId) {
      connect()
    }
    return () => {
      if (wsRef.current) {
        // Prevent reconnect logic from firing on intentional cleanup
        wsRef.current.onclose = null
        wsRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [deviceId, connect])

  const sendMessage = useCallback((msg: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
      return true
    }
    return false
  }, [])

  const sendCommand = useCallback((data: {
    device_id: number;
    content: any;
    thread_id?: string;
    project_id?: number
  }) => {
    if (!isConnected || !deviceId) {
      return false;
    }

    // Fallback to HTTP if WS not ready? Or return false and let UI decide?
    // Let's try sending via WS
    const payload = {
      type: "send_command",
      data: {
        ...data,
        device_id: deviceId // Force current device context
      }
    }

    return sendMessage(payload)
  }, [isConnected, deviceId, sendMessage])

  // Derived state: Unified Stream
  // Filter out any 'user' type logs just in case they sneak in (actually user logs ARE allowed now for chat history)
  // Wait, if we use LogsService, user messages come as 'user' type logs.
  // We should NOT filter 'user' type if we want them to show up.
  // But previously we filtered them?
  // "messages.filter(m => (m as any).type !== 'user' ...)"
  // If we want unified history, we need user messages.
  // The 'user' type logs from cloud are okay.
  // The 'output' logs (Final Answer) might still duplicate if Assistant message is also generated differently?
  // Let's keep it simple: Just allow all logs, maybe filter 'output' if it's redundant.
  // Actually, 'output' -> Final Answer.
  // 'ai' -> partial streaming? No 'ai' is usually thought/text.
  // Let's keep the filter for now just to be safe based on previous logic, but allow 'user'.
  // Sort unified messages by timestamp
  const unifiedMessages = [...messages].sort((a, b) => a.timestamp - b.timestamp)

  return {
    isConnected,
    messages,
    unifiedMessages,
    sendMessage,
    sendCommand,
    addMessage,
    setMessages,
    clearMessages: () => setMessages([]),
  }
}
