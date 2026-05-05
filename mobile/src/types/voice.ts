// 语音会话相关类型定义
// 从 VoiceSessionManager 提取，避免依赖 Expo 相关代码

export type VoiceSessionState = 'idle' | 'connecting' | 'listening' | 'recognizing' | 'thinking' | 'speaking';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
}

export interface TaskCommand {
  id: string;
  type: string;
  description: string;
  params?: Record<string, any>;
  status: 'pending' | 'confirmed' | 'cancelled';
}

export interface VoiceSession {
  id: string;
  state: VoiceSessionState;
  messages: ChatMessage[];
  startTime: number;
  endTime?: number;
}
