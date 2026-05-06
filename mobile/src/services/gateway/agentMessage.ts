/**
 * AgentMessage Schema — Agent → Mobile 统一消息协议 TypeScript 定义。
 *
 * 以 Python Backend 的 MessageBlock (message/schemas.py) 为权威定义，
 * 确保 WS 推送结构与 Python 发送的 MessageBlock 完全对齐。
 */

export type AgentRole = 'human' | 'ai' | 'tool' | 'system';

/**
 * 消息状态 — 对齐 Python MessageBlock.status
 * Python 原文："pending"|"running"|"streaming"|"completed"|"failed"|"waiting_human"
 */
export type AgentMessageStatus =
  | 'pending'
  | 'running'
  | 'streaming'
  | 'completed'
  | 'failed'
  | 'waiting_human';

/**
 * 工具调用 — 对齐 Python ToolCall
 */
export interface AgentToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  type: 'tool_call';
  index?: number;
}

/**
 * 工具元信息 — 对齐 Python MessageBlock.tool_meta
 */
export interface AgentToolMeta {
  display_name?: string;
  affected_path_keys?: string[];
}

/**
 * Agent 通过 message_sync 推送给 Mobile 的单条消息
 * 字段与 Python MessageBlock 严格对齐。
 */
export interface AgentSyncMessage {
  // === 核心标识 ===
  id: string;                      // "msg-{thread_id}-{sequence_number}"
  thread_id: string;
  run_id?: string | null;

  // === 角色与分类 ===
  role: AgentRole;
  category?: string;               // MessageCategory.value

  // === 内容 ===
  content: string;
  content_type?: 'text' | 'markdown' | 'json' | 'multipart';

  // === 思考过程 ===
  thinking?: string | null;

  // === 工具调用与执行 (role='tool' 时使用) ===
  tool_calls?: AgentToolCall[];
  tool_name?: string;
  tool_call_id?: string;
  input?: Record<string, any> | null;
  tool_meta?: AgentToolMeta | null;

  // === 状态与可见性 ===
  status?: AgentMessageStatus;
  is_visible?: number;             // 1=可见, 0=隐藏 (对齐 Python bool→int)
  action_type?: string;

  // === 时间戳 (ISO 8601 字符串, 对齐 Python MessageBlock.created_at) ===
  created_at: string;              // e.g. "2024-01-15T10:30:00+08:00"
  updated_at?: string | null;

  // === 关联与元数据 ===
  sequence_number: number;
  parent_id?: string | null;
  meta_data?: Record<string, any>; // 扩展元数据 (含 tool_meta, input, output 等)

  // === 引用 (知识/记忆/文件) ===
  references?: Array<Record<string, any>> | null;

  // 兼容旧协议字段
  project_id?: number;
}

/**
 * Agent 运行完成信号 — 对齐 sync_coordinator.py command_complete
 */
export interface AgentCommandComplete {
  thread_id: string;
  command_id?: number | string;
  status?: 'done' | 'failed' | 'cancelled';
}

