import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { DevicesService } from "../client"

const WS_URL = import.meta.env.VITE_EVOLOOP_WS_URL || "wss://mall.imagicbox.cn/wss/"

export interface LogMessage {
  type: "thought" | "tool" | "output" | "error" | "user" | "hitl_request"
  content: any
  thread_id?: string
  project_id?: number
  log_id?: number
  timestamp: number
}

export function useEvoLoopWebSocket(deviceId: number | null) {
  const { t } = useTranslation()
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<LogMessage[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<any>(null)
  const retryCountRef = useRef(0)

  const addMessage = useCallback((msg: LogMessage) => {
    setMessages((prev) => [...prev, msg])
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
                const newMsgs = logs.map((log: any) => ({
                  type: log.type,
                  content: log.content,
                  thread_id: log.thread_id,
                  project_id: log.project_id || batchProjectId,
                  timestamp: Date.now(),
                }))
                return [...prev, ...newMsgs]
              })
            }
          } else if (
            ["thought", "tool", "output", "error", "hitl_request"].includes(data.type)
          ) {
            setMessages((prev) => [
              ...prev,
              {
                type: data.type,
                content: data.content,
                thread_id: data.thread_id,
                project_id: data.project_id,
                timestamp: Date.now(),
              },
            ])
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
    }
  }, [])

  return {
    isConnected,
    messages,
    sendMessage,
    addMessage,
    setMessages,
    clearMessages: () => setMessages([]),
  }
}
