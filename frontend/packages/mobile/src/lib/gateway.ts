/**
 * Gateway WebSocket 连接管理器
 * 用于管理 EvoCloud 的 WebSocket 连接，支持语音聊天功能
 */

const WS_URL = import.meta.env.VITE_EVOLOOP_WS_URL || "wss://api.evoloop.cn/wss/"

type MessageHandler = (data: any) => void

interface GatewayConfig {
  memberId?: string
  token?: string
}

class GatewayManagerClass {
  private ws: WebSocket | null = null
  private isConnected = false
  private reconnectTimer: NodeJS.Timeout | null = null
  private retryCount = 0
  private maxRetries = 10
  private messageHandlers: Map<string, Set<MessageHandler>> = new Map()
  private config: GatewayConfig = {}
  private connectionPromise: Promise<void> | null = null
  private connectionResolve: (() => void) | null = null

  /**
   * 连接到 WebSocket
   */
  connect(config?: GatewayConfig): Promise<void> {
    if (config) {
      this.config = { ...this.config, ...config }
    }

    // 如果已经连接，直接返回
    if (this.isConnected && this.ws?.readyState === WebSocket.OPEN) {
      return Promise.resolve()
    }

    // 如果正在连接，返回现有的 Promise
    if (this.connectionPromise) {
      return this.connectionPromise
    }

    // 创建新的连接 Promise
    this.connectionPromise = new Promise((resolve) => {
      this.connectionResolve = resolve
      this.doConnect()
    })

    return this.connectionPromise
  }

  /**
   * 执行连接
   */
  private doConnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    try {
      this.ws = new WebSocket(WS_URL)

      this.ws.onopen = () => {
        console.log("[Gateway] WebSocket connected")
        this.isConnected = true
        this.retryCount = 0
        this.connectionResolve?.()
        this.connectionPromise = null
      }

      this.ws.onmessage = (event) => {
        this.handleMessage(event.data)
      }

      this.ws.onclose = () => {
        console.log("[Gateway] WebSocket closed")
        this.isConnected = false
        this.handleReconnect()
      }

      this.ws.onerror = (error) => {
        console.error("[Gateway] WebSocket error:", error)
      }
    } catch (error) {
      console.error("[Gateway] Connection failed:", error)
      this.handleReconnect()
    }
  }

  /**
   * 处理重连
   */
  private handleReconnect() {
    if (this.retryCount >= this.maxRetries) {
      console.error("[Gateway] Max retries reached")
      return
    }

    const delay = Math.min(30000, 1000 * Math.pow(2, this.retryCount))
    console.log(`[Gateway] Reconnecting in ${delay}ms (attempt ${this.retryCount + 1})`)

    this.reconnectTimer = setTimeout(() => {
      this.retryCount++
      this.doConnect()
    }, delay)
  }

  /**
   * 处理收到的消息
   */
  private handleMessage(data: string) {
    try {
      const parsed = JSON.parse(data)
      const type = parsed.type || "unknown"

      // 调用该类型的所有处理器
      const handlers = this.messageHandlers.get(type)
      if (handlers) {
        handlers.forEach((handler) => {
          try {
            handler(parsed)
          } catch (err) {
            console.error(`[Gateway] Handler error for type ${type}:`, err)
          }
        })
      }

      // 调用通配符处理器
      const wildcardHandlers = this.messageHandlers.get("*")
      if (wildcardHandlers) {
        wildcardHandlers.forEach((handler) => {
          try {
            handler(parsed)
          } catch (err) {
            console.error("[Gateway] Wildcard handler error:", err)
          }
        })
      }
    } catch (error) {
      console.error("[Gateway] Failed to parse message:", error)
    }
  }

  /**
   * 注册消息处理器
   */
  onMessage(type: string, handler: MessageHandler): () => void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, new Set())
    }
    this.messageHandlers.get(type)!.add(handler)

    // 返回取消订阅函数
    return () => {
      this.messageHandlers.get(type)?.delete(handler)
    }
  }

  /**
   * 发送消息
   */
  send(data: any): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("[Gateway] WebSocket not connected")
      return false
    }

    try {
      this.ws.send(JSON.stringify(data))
      return true
    } catch (error) {
      console.error("[Gateway] Send failed:", error)
      return false
    }
  }

  /**
   * 断开连接
   */
  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }

    this.isConnected = false
    this.messageHandlers.clear()
  }

  /**
   * 获取连接状态
   */
  getIsConnected(): boolean {
    return this.isConnected
  }
}

// 导出单例
export const GatewayManager = new GatewayManagerClass()
