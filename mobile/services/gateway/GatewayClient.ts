// Gateway WebSocket 客户端

import { EventEmitter } from 'eventemitter3';
import { WS_CONFIG } from '@/constants/config';
import { tokenStorage } from '@/services/storage/mmkv';
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

  constructor(url: string = 'wss://evoloop.develop-assistant.cn/gateway/ws') {
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

    return new Promise((resolve, reject) => {
      try {
        const token = tokenStorage.getToken();
        if (!token) {
          reject(new Error('未登录'));
          return;
        }

        // 构建 WebSocket URL（带 token）
        const url = `${this.url}?token=${encodeURIComponent(token)}`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('Gateway WebSocket 已连接');
          this.setState(ConnectionState.CONNECTED);
          this.reconnectAttempts = 0;
          this.startHeartbeat();
          this.emit('connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          console.error('Gateway WebSocket 错误:', error);
          this.setState(ConnectionState.ERROR);
          this.emit('error', error);
          reject(error);
        };

        this.ws.onclose = (event) => {
          console.log('Gateway WebSocket 已关闭:', event.code, event.reason);
          this.stopHeartbeat();
          this.setState(ConnectionState.DISCONNECTED);
          this.emit('disconnected', event);

          // 自动重连
          if (!event.wasClean) {
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
      console.warn('WebSocket 未连接，无法发送消息');
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
      console.error('解析消息失败:', error);
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

  // 安排重连
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= WS_CONFIG.maxReconnectAttempts) {
      console.error('重连次数已达上限');
      this.emit('maxReconnectReached');
      return;
    }

    this.reconnectAttempts++;
    this.setState(ConnectionState.RECONNECTING);

    console.log(`计划重连... 尝试次数: ${this.reconnectAttempts}`);

    this.reconnectTimer = setTimeout(() => {
      this.connect().catch((error) => {
        console.error('重连失败:', error);
      });
    }, WS_CONFIG.reconnectInterval);
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
