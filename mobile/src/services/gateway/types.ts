// Gateway WebSocket 消息类型定义

export enum GatewayMessageType {
  // 连接管理
  AUTH = 'auth',
  AUTH_RESULT = 'auth_result',
  PING = 'ping',
  PONG = 'pong',

  // ASR 相关
  ASR_START = 'asr_start',
  ASR_STOP = 'asr_stop',
  ASR_CHUNK = 'asr_chunk',
  ASR_RESULT = 'asr_result',
  ASR_ERROR = 'asr_error',

  // LLM 对话
  CHAT_START = 'chat_start',
  CHAT_MESSAGE = 'chat_message',
  CHAT_STREAM = 'chat_stream',
  CHAT_DONE = 'chat_done',
  CHAT_INTERRUPT = 'chat_interrupt',

  // 指令生成
  COMMAND_BUILD = 'command_build',
  COMMAND_READY = 'command_ready',
  COMMAND_CONFIRM = 'command_confirm',
  COMMAND_SEND = 'command_send',

  // Desktop 指令通道
  DEVICE_COMMAND = 'device_command',
  DEVICE_RESPONSE = 'device_response',

  // 历史留存
  HISTORY_SYNC = 'history_sync',

  // 状态广播
  STATUS_UPDATE = 'status_update',

  // HITL (Human-in-the-Loop)
  HUMAN_REQUEST = 'human_request',
  HUMAN_RESPONSE = 'human_response',
  HUMAN_TIMEOUT = 'human_timeout',
  HUMAN_CANCEL = 'human_cancel',
}

// 基础消息接口
export interface GatewayMessage {
  type: GatewayMessageType | string;
  payload?: any;
  timestamp?: number;
  requestId?: string;
}

// 认证消息
export interface AuthMessage extends GatewayMessage {
  type: GatewayMessageType.AUTH;
  payload: {
    token: string;
    deviceKey?: string;
  };
}

// 认证结果
export interface AuthResultMessage extends GatewayMessage {
  type: GatewayMessageType.AUTH_RESULT;
  payload: {
    success: boolean;
    error?: string;
  };
}

// ASR 开始
export interface ASRStartMessage extends GatewayMessage {
  type: GatewayMessageType.ASR_START;
  payload: {
    sessionId: string;
    config?: {
      sampleRate?: number;
      language?: string;
    };
  };
}

// ASR 音频数据块
export interface ASRChunkMessage extends GatewayMessage {
  type: GatewayMessageType.ASR_CHUNK;
  payload: {
    sessionId: string;
    audioData: ArrayBuffer | string; // base64
    isFinal: boolean;
  };
}

// ASR 结果
export interface ASRResultMessage extends GatewayMessage {
  type: GatewayMessageType.ASR_RESULT;
  payload: {
    sessionId: string;
    text: string;
    isFinal: boolean;
    confidence: number;
  };
}

// 聊天消息
export interface ChatMessage extends GatewayMessage {
  type: GatewayMessageType.CHAT_MESSAGE;
  payload: {
    sessionId: string;
    message: string;
    context?: any;
  };
}

// 聊天流式响应
export interface ChatStreamMessage extends GatewayMessage {
  type: GatewayMessageType.CHAT_STREAM;
  payload: {
    sessionId: string;
    chunk: string;
    isDone: boolean;
  };
}

// 指令就绪
export interface CommandReadyMessage extends GatewayMessage {
  type: GatewayMessageType.COMMAND_READY;
  payload: {
    sessionId: string;
    command: {
      type: string;
      target?: string;
      description: string;
      parameters?: Record<string, any>;
    };
    preview: string;
  };
}

// 设备指令
export interface DeviceCommandMessage extends GatewayMessage {
  type: GatewayMessageType.DEVICE_COMMAND;
  payload: {
    deviceKey: string;
    command: {
      type: string;
      params: any;
    };
    source: 'voice_chat';
    sessionId: string;
  };
}

// 连接状态
export enum ConnectionState {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
}

// HITL 请求消息
export interface HumanRequestMessage extends GatewayMessage {
  type: GatewayMessageType.HUMAN_REQUEST;
  payload: {
    sessionId: string;
    request: {
      id: string;
      type: 'text' | 'choice' | 'confirmation' | 'approval';
      prompt: string;
      options?: string[];
      default_value?: string;
      context?: any;
      timeout?: number;
    };
  };
}

// HITL 响应消息
export interface HumanResponseMessage extends GatewayMessage {
  type: GatewayMessageType.HUMAN_RESPONSE;
  payload: {
    sessionId: string;
    requestId: string;
    value: string;
  };
}

// HITL 超时消息
export interface HumanTimeoutMessage extends GatewayMessage {
  type: GatewayMessageType.HUMAN_TIMEOUT;
  payload: {
    sessionId: string;
    requestId: string;
  };
}

// HITL 取消消息
export interface HumanCancelMessage extends GatewayMessage {
  type: GatewayMessageType.HUMAN_CANCEL;
  payload: {
    sessionId: string;
    requestId: string;
    reason?: string;
  };
}

// 事件处理器类型
export type MessageHandler = (message: GatewayMessage) => void;
export type ConnectionHandler = (state: ConnectionState) => void;
export type HITLRequestHandler = (request: HumanRequestMessage['payload']['request']) => void;
