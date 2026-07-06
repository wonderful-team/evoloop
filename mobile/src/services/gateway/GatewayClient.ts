// Gateway WebSocket 客户端

import { EventEmitter } from 'eventemitter3';
import { AppState } from 'react-native';
import {WS_BASE_URL, WS_CONFIG} from '@/constants/config';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  GatewayMessage,
  GatewayMessageType,
  ConnectionState,
} from './types';
import {
  isCanonicalEnvelope,
  createEnvelope,
  CanonicalEnvelope,
  CanonicalMessageType,
  messageTypeRequiresAck,
} from './canonical';

export class GatewayClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private state: ConnectionState = ConnectionState.DISCONNECTED;
  private readonly GRACE_PERIOD_MS = 30000; // 静默重连缓冲期 30s，期间不通知 UI
  private isInGracePeriod = false;
  private graceTimer: NodeJS.Timeout | null = null;
  private static instance: GatewayClient | null = null;

  constructor(url: string = WS_BASE_URL || 'ws://127.0.0.1') {
    super();
    this.url = url;

    // 监听 App 前后台切换以触发静默重连
    let currentAppState = AppState.currentState;
    AppState.addEventListener('change', (nextAppState) => {
      if (
        (currentAppState === 'background' || currentAppState === 'inactive') &&
        nextAppState === 'active'
      ) {
        console.log('[GatewayClient] App 回到前台，触发静默重连缓冲期');
        this.handleAppForeground();
      }
      currentAppState = nextAppState;
    });
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
      let initResolved = false;
      let initTimeout: NodeJS.Timeout | null = null;

      const cleanupInit = () => {
        if (initTimeout) {
          clearTimeout(initTimeout);
          initTimeout = null;
        }
        this.off('message', onSystemInit);
      };

      const onSystemInit = (message: GatewayMessage) => {
        if (message.type === CanonicalMessageType.SystemInit) {
          initResolved = true;
          cleanupInit();
          this.emit('connected');
          resolve();
        }
      };

      this.on('message', onSystemInit);

      initTimeout = setTimeout(() => {
        if (!initResolved) {
          cleanupInit();
          reject(new Error('Gateway system.init timeout'));
        }
      }, 10000);

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
          this.cancelGracePeriod();
          this.setState(ConnectionState.CONNECTED);
          this.reconnectAttempts = 0;
          this.startHeartbeat();

          // 发送连接识别消息（token 已在 query 中，body 仅传设备类型）
          this.sendEnvelope(CanonicalMessageType.Connect, { device_type: 'mobile' });
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          this.setState(ConnectionState.ERROR);
          this.emit('error', error);
          cleanupInit();
          reject(error);
        };

        this.ws.onclose = (event) => {
          console.log('Gateway WebSocket 已关闭:', event.code, event.reason);
          this.stopHeartbeat();
          this.emit('disconnected', event);
          cleanupInit();

          if (!initResolved) {
            this.state = ConnectionState.DISCONNECTED;
            this.scheduleReconnect();
            reject(new Error(`WebSocket closed before handshake: ${event.code}`));
            return;
          }

          // 正常关闭 (1000) 或 端点离开 (1001) 不重连，其余异常都自动重连
          if (event.code !== 1000 && event.code !== 1001) {
            // 异常断开：先设内部状态，由 scheduleReconnect 决定是否通知 UI
            this.state = ConnectionState.DISCONNECTED;
            this.scheduleReconnect();
          } else {
            // 主动断开：正常通知 UI
            this.setState(ConnectionState.DISCONNECTED);
          }
        };
      } catch (error) {
        cleanupInit();
        this.setState(ConnectionState.ERROR);
        reject(error);
      }
    });
  }

  // 断开连接
  disconnect(): void {
    this.cancelGracePeriod();
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

  // 发送规范 Envelope
  sendEnvelope(type: CanonicalMessageType | string, body: Record<string, unknown> = {}): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return;
    }
    const env = createEnvelope(type, body);
    this.ws.send(JSON.stringify(env));
  }

  // 发送规范 Envelope（自动包装为规范格式）
  send(message: GatewayMessage): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return;
    }

    const env = createEnvelope(message.type, message.data || {});
    this.ws.send(JSON.stringify(env));
  }

  // 发送 ping
  ping(): void {
    this.send({ type: GatewayMessageType.PING });
  }

  // ASR 相关方法
  startASR(sessionId: string, config?: { sampleRate?: number; language?: string }): void {
    this.send({
      type: GatewayMessageType.ASR_START,
      data: {
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
      data: { sessionId },
    });
  }

  sendAudioChunk(sessionId: string, audioData: ArrayBuffer | string, isFinal: boolean = false): void {
    this.send({
      type: GatewayMessageType.ASR_CHUNK,
      data: {
        sessionId,
        audioData,
        isFinal,
      },
    });
  }

  // 聊天相关方法（仅用于 ASR/语音会话，不涉及 Desktop 命令发送）
  // 命令发送统一走 HTTP POST /gateway/api/v1/message/send
  sendChatMessage(sessionId: string, message: string, context?: any): void {
    this.send({
      type: GatewayMessageType.CHAT_MESSAGE,
      data: {
        sessionId,
        message,
        context,
      },
    });
  }

  interruptChat(sessionId: string): void {
    this.send({
      type: GatewayMessageType.CHAT_INTERRUPT,
      data: { sessionId },
    });
  }

  // 处理收到的消息
  private handleMessage(data: string): void {
    try {
      const parsed = JSON.parse(data);

      // 仅接受规范 Envelope 格式
      if (!isCanonicalEnvelope(parsed)) {
        console.warn('[GatewayClient] Non-canonical message dropped:', (parsed as any).type);
        return;
      }

      const env = parsed as CanonicalEnvelope;

      this.emit('canonical_message', env);
      this.emit('message', {
        type: env.type,
        data: env.body,
        timestamp: env.timestamp,
      });

      // 对需要确认的消息自动回复 message.ack
      if (messageTypeRequiresAck(env.type)) {
        this.sendEnvelope(CanonicalMessageType.MessageAck, {
          ack_id: env.message_id,
        });
      }

      // HITL 请求特殊处理
      if (env.type === CanonicalMessageType.HITLRequest) {
        const body = env.body as any;
        this.emit('hitl_request', {
          sessionId: body.request_id,
          request: {
            id: body.request_id,
            type: body.request_type,
            prompt: body.prompt,
            options: body.options,
            default_value: body.default_value,
            context: body.context,
            timeout: undefined,
          },
        });
      }
    } catch (error) {
      // 解析错误静默处理
    }
  }

  // 设置状态
  private setState(state: ConnectionState): void {
    if (this.state !== state) {
      this.state = state;
      // 静默重连期间只通知 CONNECTED，其余状态不通知 UI（用户无感知）
      if (!this.isInGracePeriod || state === ConnectionState.CONNECTED) {
        this.emit('stateChange', state);
      }
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

  // 安排重连（无限重连 + 指数退避 + 缓冲期）
  private scheduleReconnect(): void {
    this.reconnectAttempts++;

    // 首次异常断开时启动缓冲期：期间静默重连，不通知 UI
    if (this.reconnectAttempts === 1) {
      this.startGracePeriod();
    }

    // 缓冲期内不通知 UI 重连中状态
    if (!this.isInGracePeriod) {
      this.setState(ConnectionState.RECONNECTING);
    }

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
    this.cancelGracePeriod();
    this.clearReconnectTimer();
    if (!this.isConnected() && this.state !== ConnectionState.CONNECTING) {
      this.connect().catch(() => {
        // 错误通过 stateChange + error 事件通知，不在控制台打印
      });
    }
  }

  // 当 App 从后台/锁屏回到前台时，立即重连并拉起一个静默缓冲期
  handleAppForeground(): void {
    this.reconnectAttempts = 0;
    // 重新启动静默缓冲期，给重连一些缓冲时间，避免立刻在 UI 上显示“连接失败”
    this.startGracePeriod();
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

  // 启动静默重连缓冲期：不通知 UI，APP 端不显示“重连中”
  private startGracePeriod(): void {
    this.isInGracePeriod = true;
    this.graceTimer = setTimeout(() => {
      this.isInGracePeriod = false;
      // 缓冲期结束仍未连上，通知 UI 显示重连提示
      if (!this.isConnected()) {
        this.setState(ConnectionState.RECONNECTING);
      }
    }, this.GRACE_PERIOD_MS);
  }

  // 取消缓冲期（连接成功或主动断开时调用）
  private cancelGracePeriod(): void {
    this.isInGracePeriod = false;
    if (this.graceTimer) {
      clearTimeout(this.graceTimer);
      this.graceTimer = null;
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
