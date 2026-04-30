/**
 * Stream Output Types for real-time UI updates
 * 
 * Enhanced streaming state for transparent agent execution.
 */

export type StreamEventType =
  | 'thinking'
  | 'progress'
  | 'complete'
  | 'llm_auth_error'
  | 'quota_exhausted'
  | 'auth_expired';

export interface StreamEvent {
  type: StreamEventType;
  message: string;
  data?: Record<string, any>;
  progress?: number;  // 0-100
  timestamp: number;
  // Quota exhausted specific fields
  title?: string;
  hint?: string;
  action_text?: string;
}

export interface StreamState {
  events: StreamEvent[];
  currentThinking: string | null;
  overallProgress: number;
}

// Thinking content for display
export interface ThinkingContent {
  id: string;
  content: string;
  timestamp: number;
}


