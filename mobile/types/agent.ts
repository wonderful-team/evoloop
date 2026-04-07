// Agent 执行状态类型定义

import { SkillMatchThought } from './skill';

/**
 * Agent 执行状态
 */
export type AgentStatus = 
  | 'idle'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'stopped'
  | 'interrupted'
  | 'summarizing'
  | 'indexing'
  | 'quota_exhausted';

/**
 * 步骤类型
 */
export type StepType = 'node' | 'tool' | 'ai' | 'skill';

/**
 * 步骤状态
 */
export type StepStatus = 
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'cancelled'
  | 'success';

/**
 * Agent 执行步骤
 */
export interface AgentStep {
  id: number;
  name: string;
  tool?: string;
  tool_name?: string;
  input?: Record<string, any>;
  output?: string;
  status: StepStatus;
  type: StepType;
  parent_id?: number;
  time?: string;
  duration?: number;
  details?: string;
  started_at?: string;
  completed_at?: string;
}

/**
 * 工具调用
 */
export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
  result?: any;
  error?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
}

/**
 * Agent 思考类型
 */
export type ThoughtType = 
  | 'intent'
  | 'skill_match'
  | 'optimization'
  | 'planning'
  | 'reflection'
  | 'generic';

/**
 * Agent 思考
 */
export interface AgentThought {
  id: string;
  type: 'thought';
  thought_type: ThoughtType;
  title: string;
  content: string | Record<string, any>;
  confidence?: number;
  timestamp: number;
}

/**
 * Agent 状态信息
 */
export interface AgentState {
  mode: string;
  task_name: string;
  task_status: string;
  details?: Record<string, any>;
}

/**
 * 流式事件
 */
export interface StreamEvent {
  type: 'token' | 'step' | 'thought' | 'tool_call' | 'artifact' | 'status' | 'complete' | 'error';
  data: any;
  timestamp: number;
}

/**
 * 流式状态
 */
export interface StreamState {
  events: StreamEvent[];
  currentThinking: AgentThought | null;
  currentTool: ToolCall | null;
  overallProgress: number;
  currentStep?: AgentStep;
}

/**
 * 节点信息
 */
export interface NodeInfo {
  id: string;
  name: string;
  type: string;
  status: StepStatus;
  input?: any;
  output?: any;
  started_at?: string;
  completed_at?: string;
  children?: NodeInfo[];
}

/**
 * 执行上下文
 */
export interface ExecutionContext {
  conversation_id: string;
  project_id?: number;
  thread_id?: string;
  parent_message_id?: string;
  skills_available?: string[];
  memories_loaded?: string[];
  files_accessed?: string[];
}

/**
 * Quota 耗尽信息
 */
export interface QuotaExhaustedInfo {
  title: string;
  message: string;
  hint: string;
  actionText: string;
}

/**
 * 引用项
 */
export interface QuoteItem {
  type: 'message' | 'file' | 'memory';
  id: string;
  name: string;
  detail?: string;
  content?: string;
}

// 导出联合类型
export type AnyThought = AgentThought | SkillMatchThought;
