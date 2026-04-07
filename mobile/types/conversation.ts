// 会话/对话类型定义

import { ChatMessage } from './chat';

/**
 * 会话信息
 */
export interface Conversation {
  id: string;
  thread_id: string;
  title: string;
  project_id?: number;
  status: 'active' | 'archived' | 'deleted';
  message_count: number;
  created_at: string;
  updated_at: string;
}

/**
 * 会话列表响应
 */
export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * 创建会话请求
 */
export interface CreateConversationRequest {
  project_id?: number;
  title?: string;
  initial_message?: string;
}

/**
 * 创建会话响应
 */
export interface CreateConversationResponse {
  conversation_id: string;
  thread_id: string;
  title: string;
}

/**
 * 会话历史消息响应
 */
export interface ConversationHistoryResponse {
  messages: ChatMessage[];
  has_more: boolean;
  first_message_id?: string;
  total_count: number;
}

/**
 * Rewind 请求
 */
export interface RewindRequest {
  message_id: string;
  revert_files?: boolean;
}

/**
 * Rewind 响应
 */
export interface RewindResponse {
  success: boolean;
  message: string;
  files_reverted?: number;
  conversation_id: string;
}

/**
 * Retry 请求
 */
export interface RetryRequest {
  message_id: string;
  revert_files?: boolean;
}

/**
 * Retry 响应
 */
export interface RetryResponse {
  success: boolean;
  message: string;
  files_reverted?: number;
  conversation_id: string;
}

/**
 * 添加记忆请求
 */
export interface AddMemoryRequest {
  name: string;
  description: string;
  related_files?: string[];
}

/**
 * 记忆概念
 */
export interface MemoryConcept {
  id: string;
  name: string;
  description: string;
  related_files: string[];
  created_at: string;
  updated_at: string;
}
