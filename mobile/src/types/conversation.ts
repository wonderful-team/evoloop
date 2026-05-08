// 会话相关类型定义

export interface Conversation {
  id: string;
  title: string;
  project_id?: number;
  status: 'active' | 'stopped' | 'completed' | 'error';
  created_at: string;
  updated_at: string;
  message_count?: number;
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

// 消息引用类型
export interface MessageReference {
  type: 'message' | 'file' | 'skill' | 'memory';
  id: string;
  name: string;
  detail?: string;
}

// 消息附件类型
export interface MessageAttachment {
  id: string;
  type: 'image' | 'audio' | 'file' | 'reference' | 'skill' | 'message';
  url: string;
  name: string;
  metadata?: {
    duration?: number;
    waveform?: number[];
    skill_id?: string;
    skill_name?: string;
  };
}

export interface ChatMessage {
  id: string;
  role: 'human' | 'ai' | 'tool' | 'system';
  content: string;
  timestamp: number;
  isComplete?: boolean;
  isFinal?: boolean;
  attachments?: MessageAttachment[];
  references?: Array<Record<string, any>>;
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
