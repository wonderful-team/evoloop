import { useCallback, useEffect, useRef, useState } from "react"

const CLOUD_WS_URL = import.meta.env.VITE_EVOLOOP_WS_URL || "wss://api.evoloop.cn/ws/evoloop"
const LOCAL_PORT = 8766

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
  const [isConnected, setIsConnected] = useState(false)
  const [isLocal, setIsLocal] = useState(false)
  const [messages, setMessages] = useState<LogMessage[]>([])
  
  const cloudWsRef = useRef<WebSocket | null>(null)
  const localWsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<any>(null)
  const [localIp, setLocalIp] = useState<string | null>(localStorage.getItem("evoloop_last_local_ip"))

  const addMessage = useCallback((msg: LogMessage) => {
    setMessages((prev) => {
      if (msg.type === 'user') {
        const isDup = prev.some(m => m.type === 'user' && m.content === msg.content && Math.abs(m.timestamp - msg.timestamp) < 10000)
        if (isDup) return prev
      }
      return [...prev, msg]
    })
  }, [])

  const handleIncomingMessage = useCallback((data: any) => {
    try {
      if (data.type === "connect_ok") {
        console.log("[EvoLoop] Cloud Handshake Success")
        return
      }

      if (data.type === "new_logs") {
        const logs = data.data.logs || []
        const batchProjectId = data.data.project_id
        if (Array.isArray(logs)) {
          setMessages((prev) => {
            const formattedLogs = logs.map((log: any) => {
              const normalized = normalizeLogMessage(log)
              if (!normalized.project_id && batchProjectId) {
                normalized.project_id = batchProjectId
              }
              return normalized
            })

            const newLogs = formattedLogs.filter((nl) => {
              if (nl.log_id && prev.some((pl) => pl.log_id && pl.log_id === nl.log_id)) return false
              if (nl.type === 'user' || nl.role === 'user') {
                const matchIdx = prev.findIndex(pl =>
                  !pl.log_id &&
                  pl.role === nl.role &&
                  pl.content === nl.content &&
                  Math.abs(pl.timestamp - nl.timestamp) < 30000
                )
                if (matchIdx !== -1) {
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
          if (normalized.log_id && prev.some(pl => pl.log_id === normalized.log_id)) return prev
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
  }, [])

  const connectCloud = useCallback(() => {
    if (!deviceId || (localWsRef.current && localWsRef.current.readyState === WebSocket.OPEN)) return

    try {
      const ws = new WebSocket(CLOUD_WS_URL)
      cloudWsRef.current = ws

      ws.onopen = () => {
        console.log("[EvoLoop] Cloud WS Connected. Handshaking...")
        const token = localStorage.getItem("evoloop_token") || localStorage.getItem("access_token")
        if (token) {
          ws.send(JSON.stringify({
            type: "connect",
            payload: {
              device_type: "mobile",
              token: token
            }
          }))
        }
        setIsConnected(true)
        setIsLocal(false)
      }

      ws.onmessage = (event) => {
        handleIncomingMessage(JSON.parse(event.data))
      }

      ws.onclose = () => {
        console.log("[EvoLoop] Cloud WS Closed")
        if (!isLocal) setIsConnected(false)
        reconnectTimeoutRef.current = setTimeout(connectCloud, 5000)
      }
    } catch (e) {
      console.error("[EvoLoop] Cloud Connection failed", e)
    }
  }, [deviceId, isLocal, handleIncomingMessage])

  const connectLocal = useCallback((ip: string) => {
    if (localWsRef.current) localWsRef.current.close()

    try {
      const ws = new WebSocket(`ws://${ip}:${LOCAL_PORT}`)
      localWsRef.current = ws

      ws.onopen = () => {
        console.log("[EvoLoop] Local P2P Connected!")
        setIsConnected(true)
        setIsLocal(true)
        localStorage.setItem("evoloop_last_local_ip", ip)
      }

      ws.onmessage = (event) => {
        handleIncomingMessage(JSON.parse(event.data))
      }

      ws.onclose = () => {
        console.log("[EvoLoop] Local WS Closed. Falling back to Cloud...")
        setIsLocal(false)
        setIsConnected(false)
        connectCloud()
      }
    } catch (e) {
      console.error("[EvoLoop] Local Connection failed", e)
    }
  }, [connectCloud, handleIncomingMessage])

  const sendMessage = useCallback((msg: any) => {
    const ws = (localWsRef.current?.readyState === WebSocket.OPEN) ? localWsRef.current : cloudWsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg))
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
    if (!isConnected || !deviceId) return false

    const payload = isLocal ? {
      type: "new_command",
      data: { ...data }
    } : {
      type: "command_relay",
      payload: {
        ...data,
        target_device_id: deviceId
      }
    }

    return sendMessage(payload)
  }, [isConnected, deviceId, sendMessage, isLocal])

  useEffect(() => {
    if (deviceId) {
      if (localIp) {
        connectLocal(localIp)
      } else {
        connectCloud()
      }
    }
    return () => {
      if (cloudWsRef.current) cloudWsRef.current.close()
      if (localWsRef.current) localWsRef.current.close()
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
    }
  }, [deviceId, localIp, connectLocal, connectCloud])

  const unifiedMessages = [...messages].sort((a, b) => a.timestamp - b.timestamp)

  return {
    isConnected,
    isLocal,
    messages,
    unifiedMessages,
    sendMessage,
    sendCommand,
    addMessage,
    setMessages,
    setLocalIp,
    clearMessages: () => setMessages([]),
  }
}
