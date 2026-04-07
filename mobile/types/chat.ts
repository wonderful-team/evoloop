// 聊天/语音相关类型

export type MessageRole = 'user' | 'assistant' | 'system';
export type MessageType = 'text' | 'command' | 'error';
export type VoiceSessionState = 'idle' | 'listening' | 'processing' | 'responding';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  type: MessageType;
  timestamp: number;
  metadata?: {
    command?: TaskCommand;
    audioUrl?: string;
    [key: string]: any;
  };
}

export interface TaskCommand {
  id: string;
  type: 'analyze' | 'edit' | 'run' | 'debug' | 'general';
  target?: string;
  description: string;
  parameters?: Record<string, any>;
  status: 'pending' | 'confirmed' | 'executing' | 'completed' | 'failed';
}

export interface VoiceSession {
  id: string;
  state: VoiceSessionState;
  messages: ChatMessage[];
  currentCommand?: TaskCommand;
  startTime: number;
  endTime?: number;
}

// Gateway WebSocket 消息类型
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
}

export interface GatewayMessage {
  type: GatewayMessageType | string;
  payload?: any;
  timestamp?: number;
}
