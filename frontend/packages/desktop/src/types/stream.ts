/**
 * Stream Output Types for real-time UI updates
 * 
 * Enhanced streaming state for transparent agent execution.
 */

export type StreamEventType =
  | 'thinking'
  | 'tool_start'
  | 'tool_progress'
  | 'tool_complete'
  | 'tool_error'
  | 'checkpoint'
  | 'progress'
  | 'complete'
  | 'llm_auth_error'
  | 'quota_exhausted';

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
  currentTool: ToolExecutionStatus | null;
  overallProgress: number;
}

// Thinking content for display
export interface ThinkingContent {
  id: string;
  content: string;
  timestamp: number;
}

// Tool execution status
export interface ToolExecutionStatus {
  id: string;
  toolName: string;
  displayName: string;
  status: 'pending' | 'running' | 'complete' | 'error';
  progress: number;  // 0-100
  message: string;
  startTime: number;
  endTime?: number;
  params?: Record<string, any>;
  result?: any;
  error?: string;
}

// Checkpoint event data
export interface CheckpointEventData {
  checkpointId: string;
  name: string;
  fileCount: number;
  autoCreated: boolean;
}

// Progress event data
export interface ProgressEventData {
  phase: string;
  current: number;
  total: number;
  message: string;
}
