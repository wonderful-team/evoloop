// 语音对话相关类型定义

// 语音会话状态
export type VoiceSessionState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'recognizing'
  | 'thinking'
  | 'speaking';

// 语音会话
export interface VoiceSession {
  id: string;
  state: VoiceSessionState;
  messages: ChatMessage[];
  currentCommand?: TaskCommand;
  startTime: number;
  endTime?: number;
}

// 聊天消息
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  isFinal?: boolean; // ASR 是否完成
  isComplete?: boolean; // 流式消息是否完成
  type?: 'text' | 'command' | 'image';
  metadata?: Record<string, any>;
}

// 设备指令
export interface TaskCommand {
  id: string;
  deviceId: string;
  deviceName?: string;
  deviceType?: string;
  action: string;
  parameters?: Record<string, any>;
  status: 'pending' | 'confirmed' | 'cancelled' | 'executing' | 'completed' | 'failed';
  description?: string;
}

// ASR 结果
export interface ASRResult {
  text: string;
  isFinal: boolean;
  confidence?: number;
  language?: string;
}

// 语音配置
export interface VoiceConfig {
  sampleRate: number;
  channels: number;
  bitDepth: number;
  maxDuration: number;
}

// VAD 配置
export interface VADConfiguration {
  threshold: number;
  silenceTimeout: number;
  minSpeechDuration: number;
  maxSpeechDuration: number;
}
