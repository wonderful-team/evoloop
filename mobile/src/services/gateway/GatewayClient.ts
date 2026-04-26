// Gateway WebSocket 客户端

import { EventEmitter } from 'eventemitter3';
import {WS_BASE_URL, WS_CONFIG} from '@/constants/config';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  GatewayMessage,
  GatewayMessageType,
  ConnectionState,
  MessageHandler,
  ConnectionHandler,
} from './types';

export class GatewayClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private state: ConnectionState = ConnectionState.DISCONNECTED;
  private static instance: GatewayClient | null = null;

  constructor(url: string = WS_BASE_URL || 'ws://127.0.0.1') {
    super();
    this.url = url;
  }

  // 获取单例实例
  static getInstance(): GatewayClient {
    if (!GatewayClient.instance) {
      GatewayClient.instance = new GatewayClient();
    }
    return GatewayClient.instance;
  }

  // 获取当前连接状态
  getConnectionState(): ConnectionState {
    return this.state;
  }

  // 是否已连接
  isConnected(): boolean {
    return this.state === ConnectionState.CONNECTED;
  }

  // 连接 WebSocket
  async connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.setState(ConnectionState.CONNECTING);

    // 清理旧的 WebSocket，避免事件处理器泄漏和 Promise 状态混乱
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      this.ws.close(1000);
      this.ws = null;
    }

    return new Promise(async (resolve, reject) => {
      try {
        // 优先使用用户 token，否则使用游客模式
        let token = await AsyncStorage.getItem('token');
        let isGuest = false;

        if (!token) {
          // 游客模式：生成或使用游客 token（7 天过期）
          const GUEST_TOKEN_TTL = 7 * 24 * 60 * 60 * 1000; // 7 天
          let guestToken = await AsyncStorage.getItem('guestToken');
          const guestTokenTime = await AsyncStorage.getItem('guestToken_time');
          const isExpired = guestTokenTime ? Date.now() - parseInt(guestTokenTime, 10) > GUEST_TOKEN_TTL : true;

          if (!guestToken || isExpired) {
            guestToken = `guest_${Date.now()}_${Math.random().toString(36).slice(2)}`;
            await AsyncStorage.setItem('guestToken', guestToken);
            await AsyncStorage.setItem('guestToken_time', Date.now().toString());
          }
          token = `guest:${guestToken}`;
          isGuest = true;
        }

        // 构建 WebSocket URL（带 token 和游客标记）
        const url = `${this.url}?token=${encodeURIComponent(token)}${isGuest ? '&mode=guest' : ''}`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          this.setState(ConnectionState.CONNECTED);
          this.setState(ConnectionState.CONNECTED);
          this.reconnectAttempts = 0;
          this.startHeartbeat();

          // 发送认证消息
          this.send({
            type: GatewayMessageType.AUTH,
            payload: {
              token,
              device_type: 'mobile',
            },
          });

          this.emit('connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          this.setState(ConnectionState.ERROR);
          this.emit('error', error);
          reject(error);
        };

        this.ws.onclose = (event) => {
          console.log('Gateway WebSocket 已关闭:', event.code, event.reason);
          this.stopHeartbeat();
          this.setState(ConnectionState.DISCONNECTED);
          this.emit('disconnected', event);

          // 正常关闭 (1000) 或 端点离开 (1001) 不重连，其余异常都自动重连
          if (event.code !== 1000 && event.code !== 1001) {
            this.scheduleReconnect();
          }
        };
      } catch (error) {
        this.setState(ConnectionState.ERROR);
        reject(error);
      }
    });
  }

  // 断开连接
  disconnect(): void {
    this.stopHeartbeat();
    this.clearReconnectTimer();

    if (this.ws) {
      this.ws.close(1000, '主动断开');
      this.ws = null;
    }

    this.setState(ConnectionState.DISCONNECTED);
  }

  // 重新连接
  async reconnect(): Promise<void> {
    this.disconnect();
    return this.connect();
  }

  // 发送消息
  send(message: GatewayMessage): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return;
    }

    const data = JSON.stringify({
      ...message,
      timestamp: Date.now(),
    });

    this.ws.send(data);
  }

  // 发送 ping
  ping(): void {
    this.send({ type: GatewayMessageType.PING });
  }

  // ASR 相关方法
  startASR(sessionId: string, config?: { sampleRate?: number; language?: string }): void {
    this.send({
      type: GatewayMessageType.ASR_START,
      payload: {
        sessionId,
        config: {
          sampleRate: 16000,
          language: 'zh-CN',
          ...config,
        },
      },
    });
  }

  stopASR(sessionId: string): void {
    this.send({
      type: GatewayMessageType.ASR_STOP,
      payload: { sessionId },
    });
  }

  sendAudioChunk(sessionId: string, audioData: ArrayBuffer | string, isFinal: boolean = false): void {
    this.send({
      type: GatewayMessageType.ASR_CHUNK,
      payload: {
        sessionId,
        audioData,
        isFinal,
      },
    });
  }

  // 聊天相关方法
  sendChatMessage(sessionId: string, message: string, context?: any): void {
    this.send({
      type: GatewayMessageType.CHAT_MESSAGE,
      payload: {
        sessionId,
        message,
        context,
      },
    });
  }

  interruptChat(sessionId: string): void {
    this.send({
      type: GatewayMessageType.CHAT_INTERRUPT,
      payload: { sessionId },
    });
  }

  // 指令确认
  confirmCommand(sessionId: string, confirmed: boolean): void {
    this.send({
      type: GatewayMessageType.COMMAND_CONFIRM,
      payload: {
        sessionId,
        confirmed,
      },
    });
  }

  // 处理收到的消息
  private handleMessage(data: string): void {
    try {
      const message: GatewayMessage = JSON.parse(data);
      
      // 处理 pong
      if (message.type === GatewayMessageType.PONG) {
        return;
      }

      this.emit('message', message);
      this.emit(message.type, message);
    } catch (error) {
      // 解析错误静默处理，避免控制台刷屏
    }
  }

  // 设置状态
  private setState(state: ConnectionState): void {
    if (this.state !== state) {
      this.state = state;
      this.emit('stateChange', state);
    }
  }

  // 启动心跳
  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected()) {
        this.ping();
      }
    }, WS_CONFIG.heartbeatInterval);
  }

  // 停止心跳
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // 计算指数退避延迟（带抖动）
  private getReconnectDelay(): number {
    const base = WS_CONFIG.reconnectBaseInterval;
    const max = WS_CONFIG.reconnectMaxInterval;
    // 指数退避: base * 2^attempts，封顶 max，再加 0~1s 抖动避免惊群
    const delay = Math.min(max, base * Math.pow(2, this.reconnectAttempts));
    const jitter = Math.random() * 1000;
    return delay + jitter;
  }

  // 安排重连（无限重连 + 指数退避）
  private scheduleReconnect(): void {
    this.reconnectAttempts++;
    this.setState(ConnectionState.RECONNECTING);

    const delay = this.getReconnectDelay();
    console.log(`计划重连... 尝试次数: ${this.reconnectAttempts}, 延迟: ${Math.round(delay)}ms`);

    this.reconnectTimer = setTimeout(() => {
      this.connect().catch(() => {
        // 错误通过 stateChange + error 事件通知，不在控制台打印
      });
    }, delay);
  }

  // 重置退避计数（App 回到前台、网络恢复时调用，可立即尝试连接）
  resetBackoff(): void {
    this.reconnectAttempts = 0;
    this.clearReconnectTimer();
    if (!this.isConnected() && this.state !== ConnectionState.CONNECTING) {
      this.connect().catch(() => {
        // 错误通过 stateChange + error 事件通知，不在控制台打印
      });
    }
  }

  // 清除重连定时器
  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

// 获取单例实例（兼容旧代码）
export function getGatewayClient(): GatewayClient {
  return GatewayClient.getInstance();
}

// 重置单例
export function resetGatewayClient(): void {
  const instance = GatewayClient.getInstance();
  instance.disconnect();
  GatewayClient.instance = null;
}
