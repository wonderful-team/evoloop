// 会话管理 API
// 混合架构：
// - 查询类 (列表、详情、历史): Mobile → MC
// - 指令类 (停止、回退、重试): Mobile → Gateway → Desktop

import { api } from './client';
import {
  Conversation,
  ConversationListResponse,
  CreateConversationRequest,
  CreateConversationResponse,
  ConversationHistoryResponse,
  RewindRequest,
  RewindResponse,
  RetryRequest,
  RetryResponse,
  AddMemoryRequest,
  MemoryConcept,
} from '@/types/conversation';

/**
 * 获取会话列表
 * GET /evolooplink/api/conversation/list (MC 存储)
 * 
 * MC 响应格式: { code: 0, data: { list: [...], total: 10 }, message: 'success' }
 */
export async function getConversations(
  projectId?: number,
  page = 1,
  pageSize = 20,
  deviceKey?: string
): Promise<ConversationListResponse> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId.toString());
  if (deviceKey) params.append('device_key', deviceKey);
  params.append('page', page.toString());
  params.append('page_size', pageSize.toString());
  
  const response = await api.get(`/member/evolooplink/api/conversation/list?${params.toString()}`);
  
  // MC 返回格式处理
  if (response.code !== 0) {
    throw new Error(response.message || '获取会话列表失败');
  }
  
  const data = response.data || {};
  return {
    conversations: data.list || [],
    total: data.total || 0,
    page: data.page || page,
    page_size: data.page_size || pageSize,
  };
}

/**
 * 创建新会话
 * POST /member/api/conversations (MC 存储)
 * 
 * 注意: 实际创建会话通常在 Desktop 端完成，Mobile 端主要是查询
 * 此方法用于 Mobile 端主动创建会话的场景
 */
export async function createConversation(
  data: CreateConversationRequest
): Promise<CreateConversationResponse> {
  const response = await api.post(`/member/evolooplink/api/conversation/list`, data);
  
  if (response.code !== 0) {
    throw new Error(response.message || '创建会话失败');
  }
  
  return response.data;
}

/**
 * 获取会话详情
 * GET /evolooplink/api/conversation/detail (MC 存储)
 * 
 * MC 响应格式: { code: 0, data: {...}, message: 'success' }
 */
export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await api.get(`/member/evolooplink/api/conversation/detail?conversation_id=${conversationId}`);
  
  if (response.code !== 0) {
    throw new Error(response.message || '获取会话详情失败');
  }
  
  return response.data;
}

/**
 * 删除会话
 * POST /evolooplink/api/conversation/delete (MC 存储)
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await api.post(`/member/evolooplink/api/conversation/delete`, {
    conversation_id: conversationId 
  });
  
  if (response.code !== 0) {
    throw new Error(response.message || '删除会话失败');
  }
}

/**
 * 获取会话历史消息
 * GET /evolooplink/api/conversation/messages (MC 存储)
 * 
 * MC 响应格式: { code: 0, data: { conversation: {...}, messages: [...] }, message: 'success' }
 */
export async function getConversationHistory(
  conversationId: string,
  beforeMessageId?: string,
  limit = 20
): Promise<ConversationHistoryResponse> {
  const params = new URLSearchParams();
  params.append('conversation_id', conversationId);
  if (beforeMessageId) params.append('before_message_id', beforeMessageId);
  params.append('limit', limit.toString());
  
  const response = await api.get(`/member/evolooplink/api/conversation/messages?${params.toString()}`);
  
  if (response.code !== 0) {
    throw new Error(response.message || '获取消息历史失败');
  }
  
  const data = response.data || {};
  return {
    messages: data.messages || [],
    has_more: (data.messages || []).length === limit,
    first_message_id: data.messages?.[0]?.id,
    total_count: data.total || 0,
  };
}

/**
 * 停止 Agent (指令类 → Gateway → Desktop)
 * POST /gateway/api/v1/conversations/:id/stop
 */
export async function stopAgent(conversationId: string): Promise<void> {
  const response = await api.post(`/gateway/api/v1/conversations/${conversationId}/stop`, {});
  
  if (response.code !== 0) {
    throw new Error(response.message || '停止失败');
  }
}

/**
 * Rewind - 回退到指定消息 (指令类 → Gateway → Desktop)
 * POST /gateway/api/v1/conversations/:id/rewind
 */
export async function rewindConversation(
  conversationId: string,
  request: RewindRequest
): Promise<RewindResponse> {
  const response = await api.post(
    `/gateway/api/v1/conversations/${conversationId}/rewind`,
    request
  );
  
  if (response.code !== 0) {
    throw new Error(response.message || '回退失败');
  }
  
  return response.data;
}

/**
 * Retry - 从指定消息重试 (指令类 → Gateway → Desktop)
 * POST /gateway/api/v1/conversations/:id/retry
 */
export async function retryConversation(
  conversationId: string,
  request: RetryRequest
): Promise<RetryResponse> {
  const response = await api.post(
    `/gateway/api/v1/conversations/${conversationId}/retry`,
    request
  );
  
  if (response.code !== 0) {
    throw new Error(response.message || '重试失败');
  }
  
  return response.data;
}

/**
 * 添加消息到记忆 (MC 存储)
 * POST /member/api/projects/:id/memory
 */
export async function addToMemory(
  projectId: number,
  request: AddMemoryRequest
): Promise<MemoryConcept> {
  const response = await api.post(
    `/member/api/projects/${projectId}/memory`,
    request
  );
  
  if (response.code !== 0) {
    throw new Error(response.message || '添加记忆失败');
  }
  
  return response.data;
}

/**
 * 获取项目记忆列表 (MC 存储)
 * GET /member/api/projects/:id/memory
 */
export async function getMemories(projectId: number): Promise<MemoryConcept[]> {
  const response = await api.get(`/member/api/projects/${projectId}/memory`);
  
  if (response.code !== 0) {
    throw new Error(response.message || '获取记忆失败');
  }
  
  return response.data || [];
}

/**
 * 发送消息 (HTTP 方式，非 WebSocket) (MC 存储)
 * POST /member/api/conversations/:id/messages
 * 
 * 注意: 实际消息发送通常通过 Gateway → Desktop 执行
 * 此方法用于 Mobile 端直接向 MC 保存消息的场景
 */
export async function sendMessage(
  conversationId: string,
  content: string,
  attachments?: any[],
  options?: {
    model?: string;
    references?: any[];
  }
): Promise<{ message_id: string }> {
  const response = await api.post(
    `/member/evolooplink/api/conversation/detail?conversation_id=${conversationId}/messages`,
    {
      content,
      attachments,
      ...options,
    }
  );
  
  if (response.code !== 0) {
    throw new Error(response.message || '发送消息失败');
  }
  
  return response.data;
}
