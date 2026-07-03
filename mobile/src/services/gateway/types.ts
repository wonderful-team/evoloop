// Gateway WebSocket 消息类型定义（协议层控制消息，与业务 Envelope 无关）
// 业务消息统一使用规范 Envelope 格式（见 canonical.ts）

export enum GatewayMessageType {
  // 连接管理（WS 握手 query token 已完成认证，此处发送 connect 元数据）
  CONNECT = 'connect',
  PING = 'ping',

  // ASR 相关（私有协议，暂不改造）
  ASR_START = 'asr_start',
  ASR_STOP = 'asr_stop',
  ASR_CHUNK = 'asr_chunk',

  // LLM 对话（仅用于 ASR/语音会话，不经过规范 Envelope）
  CHAT_MESSAGE = 'chat_message',
  CHAT_INTERRUPT = 'chat_interrupt',

  // 旧协议消息（用于 event listener 兼容，参见 useChatGateway）
  MESSAGE_SYNC = 'message_sync',
  MESSAGES_DELETED = 'messages_deleted',
  THREAD_REWIND = 'thread_rewind',
  AGENT_RUN_COMPLETED = 'agent_run_completed',
  DEVICE_STATUS_UPDATE = 'device_status_update',
}

// 基础消息接口（仅用于协议层：connect/ping/ASR，业务消息使用 CanonicalEnvelope）
export interface GatewayMessage {
  type: string;
  data?: any;
  timestamp?: number;
  requestId?: string;
}

// 连接状态
export enum ConnectionState {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
}

// 事件处理器类型
export type MessageHandler = (message: GatewayMessage) => void;
export type ConnectionHandler = (state: ConnectionState) => void;
