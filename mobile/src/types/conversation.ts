// 会话相关类型定义

export interface Conversation {
  id: string;
  title: string;
  project_id?: number;
  status: 'active' | 'stopped' | 'completed' | 'error';
  created_at: string;
  updated_at: string;
  message_count?: number;
  is_pinned?: boolean;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateConversationRequest {
  project_id?: number;
  initial_message?: string;
  title?: string;
}

export interface CreateConversationResponse {
  conversation_id: string;
  title: string;
}

// 消息引用类型 (对齐后端 ReferenceBlock)
export interface MessageReference {
  id: string;
  type: 'file' | 'image' | 'audio' | 'message' | 'artifact' | 'changeset' | 'skill';
  target_id: string;
  target_name: string;
  meta_data?: Record<string, any>;
}



export interface ChatMessage {
  id: string;
  role: 'human' | 'ai' | 'tool' | 'system';
  content: string;
  timestamp: string; // 已从 number 改为 string (ISO 8601)
  isComplete?: boolean;
  isFinal?: boolean;
  references?: MessageReference[]; // 使用强类型
  has_file_operations?: boolean;
  steps?: any[];
  /** 消息状态，对齐后端原始值 */
  status?: 'pending' | 'running' | 'streaming' | 'completed' | 'failed' | 'waiting_human';

  // === 对齐 Python MessageBlock 的扩展字段 ===
  /** AI 思考过程 (extended thinking) */
  thinking?: string;
  /** 工具名称 (role='tool' 时) */
  tool_name?: string;
  /** 工具调用 ID */
  tool_call_id?: string;
  /** 工具元信息：display_name 等前端展示数据 */
  tool_meta?: { display_name?: string; affected_path_keys?: string[] };
  /** AI 发出的工具调用列表 */
  tool_calls?: Array<Record<string, any>>;
  /** 消息分类标签 (MessageCategory.value) */
  category?: string;
  /** 全局序列号，用于去重和排序 */
  sequence_number?: number;
  /** 文件变更数量 */
  changeset_count?: number;
  /** 文件变更详情 */
  changeset_files?: Array<{
    path: string;
    operation: 'added' | 'modified' | 'deleted' | 'renamed';
  }>;
}


export interface ConversationHistoryResponse {
  messages: ChatMessage[];
  has_more: boolean;
  first_message_id: string | null;
  total_count: number;
}

// Rewind 请求
export interface RewindRequest {
  message_id: string;
  revert_files?: boolean;
}

// Rewind 响应
export interface RewindResponse {
  success: boolean;
  message: string;
  files_reverted?: number;
  conversation_id: string;
}

// Retry 请求
export interface RetryRequest {
  message_id: string;
  revert_files?: boolean;
  project_id?: number;
}

// Retry 响应
export interface RetryResponse {
  success: boolean;
  message: string;
  files_reverted?: number;
  conversation_id: string;
}

// 添加到记忆请求
export interface AddMemoryRequest {
  name: string;
  description: string;
  related_files?: string[];
}

// 记忆概念
export interface MemoryConcept {
  id: string;
  name: string;
  description: string;
  related_files: string[];
  created_at: string;
}

// 搜索引用结果
export interface SearchReferenceResult {
  id: string;
  type: 'message' | 'file';
  name: string;
  content: string;
  score: number;
  timestamp?: string;
}

// 额度信息
export interface QuotaInfo {
  total: number;
  used: number;
  remaining: number;
  reset_time?: string;
}

// 额度耗尽响应
export interface QuotaExhaustedResponse {
  exhausted: boolean;
  quota: QuotaInfo;
  upgrade_url?: string;
}
