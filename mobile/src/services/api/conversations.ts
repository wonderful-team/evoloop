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
import i18n from '@/locales';

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
    throw new Error(response.message || i18n.t('api.errors.getConversationsFailed'));
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
    throw new Error(response.message || i18n.t('api.errors.createConversationFailed'));
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
    throw new Error(response.message || i18n.t('api.errors.getConversationDetailFailed'));
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
    throw new Error(response.message || i18n.t('api.errors.deleteConversationFailed'));
  }
}

/**
 * 获取会话历史消息
 * GET /evolooplink/api/conversation/messages (MC 存储)
 * 
 * MC 响应格式: { code: 0, data: { messages, has_more, first_id, last_id, total_count, conversation } }
 */
export async function getConversationHistory(
  conversationId: string,
  projectId: number = 0,
  beforeMessageId?: string,
  limit = 50
): Promise<ConversationHistoryResponse> {
  const params = new URLSearchParams();
  params.append('conversation_id', conversationId);
  params.append('project_id', projectId.toString());
  if (beforeMessageId) params.append('before_message_id', beforeMessageId);
  params.append('limit', limit.toString());
  
  const response = await api.get(`/member/evolooplink/api/conversation/messages?${params.toString()}`);
  
  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('api.errors.getMessagesFailed'));
  }
  
  const data = response.data || {};
  return {
    messages: data.messages || [],
    has_more: data.has_more ?? false,
    first_message_id: data.first_id ?? null,
    total_count: data.total_count ?? 0,
  };
}

/**
 * 停止 Agent (指令类 → Gateway → Desktop)
 * POST /gateway/api/v1/conversations/:id/stop
 */
export async function stopAgent(conversationId: string, deviceKey?: string): Promise<void> {
  const response = await api.post(`/gateway/api/v1/conversations/${conversationId}/stop`, {}, {
    params: { device_key: deviceKey }
  });
  
  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('api.errors.stopFailed'));
  }
}

/**
 * Rewind - 回退到指定消息 (指令类 → Gateway → Desktop)
 * POST /gateway/api/v1/conversations/:id/rewind
 */
export async function rewindConversation(
  conversationId: string,
  request: RewindRequest,
  deviceKey?: string
): Promise<RewindResponse> {
  const response = await api.post(
    `/gateway/api/v1/conversations/${conversationId}/rewind`,
    request,
    { params: { device_key: deviceKey } }
  );
  
  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('api.errors.rewindFailed'));
  }
  
  return response.data;
}

/**
 * Retry - 从指定消息重试 (指令类 → Gateway → Desktop)
 * POST /gateway/api/v1/conversations/:id/retry
 */
export async function retryConversation(
  conversationId: string,
  request: RetryRequest,
  deviceKey?: string
): Promise<RetryResponse> {
  const response = await api.post(
    `/gateway/api/v1/conversations/${conversationId}/retry`,
    request,
    { params: { device_key: deviceKey } }
  );
  
  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('api.errors.retryFailed'));
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
    throw new Error(response.message || i18n.t('api.errors.addMemoryFailed'));
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
    throw new Error(response.message || i18n.t('api.errors.getMemoryFailed'));
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
  options?: {
    model?: string;
    references?: any[];
  }
): Promise<{ message_id: string }> {
  const response = await api.post(
    `/member/evolooplink/api/conversation/detail?conversation_id=${conversationId}/messages`,
    {
      content,
      ...options,
    }
  );
  
  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('api.errors.sendMessageFailed'));
  }
  
  return response.data;
}

/**
 * 同步新消息 (用于后台轮询)
 * GET /evolooplink/api/conversation/sync
 */
export async function syncMessages(lastTime: number): Promise<{ messages: any[], serverTime: number }> {
  const response = await api.get(`/member/evolooplink/api/conversation/sync?last_time=${lastTime}`);
  
  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('api.errors.syncMessagesFailed'));
  }
  
  return {
    messages: response.data || [],
    serverTime: response.timestamp || Math.floor(Date.now() / 1000)
  };
}

/**
 * 标记会话为已读
 * POST /evolooplink/api/conversation/read
 */
export async function markAsRead(conversationId: string): Promise<void> {
  const response = await api.post(`/member/evolooplink/api/conversation/read`, {
    conversation_id: conversationId
  });
  
  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('api.errors.markAsReadFailed'));
  }
}

/**
 * 更新会话属性 (标题或置顶状态)
 * POST /evolooplink/api/conversation/update
 */
export async function updateConversation(
  conversationId: string,
  updateData: { title?: string; is_pinned?: number }
): Promise<void> {
  const response = await api.post(`/member/evolooplink/api/conversation/update`, {
    conversation_id: conversationId,
    ...updateData,
  });

  if (response.code !== 0) {
    throw new Error(response.message || i18n.t('toast.updateConversationFailed'));
  }
}
