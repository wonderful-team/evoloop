/**
 * AgentMessage Schema — Agent → Mobile 统一消息协议 TypeScript 定义。
 *
 * 对应 Agent 端 mobile_schema.py 的 Pydantic 模型，
 * 替代 ChatScreen.tsx 中 handleMessageSync 的 any 类型。
 */

export type AgentRole = 'human' | 'ai' | 'tool' | 'system';
export type AgentMessageStatus = 'completed' | 'failed' | 'waiting_human';

/**
 * Agent 通过 message_sync 推送给 Mobile 的单条消息
 */
export interface AgentSyncMessage {
  id: string;
  thread_id: string;
  project_id?: number;
  role: AgentRole;
  content: string;
  thinking?: string | null;
  created_at: number;
  sequence_number: number;
  action_type?: string;
  is_visible?: number;
  status?: AgentMessageStatus;
  category?: string;

  // 可选：工具调用相关
  tool_calls?: Array<Record<string, any>>;
  tool_name?: string;
  tool_call_id?: string;
}
