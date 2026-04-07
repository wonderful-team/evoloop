// 会话管理 API

import { api } from './client';
import { MEMBER_API } from '@/constants/api';
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
 */
export async function getConversations(
  projectId?: number,
  page = 1,
  pageSize = 20
): Promise<ConversationListResponse> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId.toString());
  params.append('page', page.toString());
  params.append('page_size', pageSize.toString());
  
  const response = await api.get(`${MEMBER_API.CONVERSATIONS}?${params.toString()}`);
  return response.data;
}

/**
 * 创建新会话
 */
export async function createConversation(
  data: CreateConversationRequest
): Promise<CreateConversationResponse> {
  const response = await api.post(MEMBER_API.CONVERSATIONS, data);
  return response.data;
}

/**
 * 获取会话详情
 */
export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await api.get(`${MEMBER_API.CONVERSATIONS}/${conversationId}`);
  return response.data;
}

/**
 * 删除会话
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(`${MEMBER_API.CONVERSATIONS}/${conversationId}`);
}

/**
 * 获取会话历史消息
 */
export async function getConversationHistory(
  conversationId: string,
  beforeMessageId?: string,
  limit = 20
): Promise<ConversationHistoryResponse> {
  const params = new URLSearchParams();
  if (beforeMessageId) params.append('before', beforeMessageId);
  params.append('limit', limit.toString());
  
  const response = await api.get(
    `${MEMBER_API.CONVERSATIONS}/${conversationId}/history?${params.toString()}`
  );
  return response.data;
}

/**
 * 停止 Agent
 */
export async function stopAgent(conversationId: string): Promise<void> {
  await api.post(`${MEMBER_API.CONVERSATIONS}/${conversationId}/stop`);
}

/**
 * 暂停 Agent (HITL 等待)
 */
export async function pauseAgent(conversationId: string): Promise<void> {
  await api.post(`${MEMBER_API.CONVERSATIONS}/${conversationId}/pause`);
}

/**
 * Rewind - 回退到指定消息
 */
export async function rewindConversation(
  conversationId: string,
  request: RewindRequest
): Promise<RewindResponse> {
  const response = await api.post(
    `${MEMBER_API.CONVERSATIONS}/${conversationId}/rewind`,
    request
  );
  return response.data;
}

/**
 * Retry - 从指定消息重试
 */
export async function retryConversation(
  conversationId: string,
  request: RetryRequest
): Promise<RetryResponse> {
  const response = await api.post(
    `${MEMBER_API.CONVERSATIONS}/${conversationId}/retry`,
    request
  );
  return response.data;
}

/**
 * 添加消息到记忆
 */
export async function addToMemory(
  projectId: number,
  request: AddMemoryRequest
): Promise<MemoryConcept> {
  const response = await api.post(
    `${MEMBER_API.PROJECTS}/${projectId}/memory`,
    request
  );
  return response.data;
}

/**
 * 获取项目记忆列表
 */
export async function getMemories(projectId: number): Promise<MemoryConcept[]> {
  const response = await api.get(`${MEMBER_API.PROJECTS}/${projectId}/memory`);
  return response.data;
}

/**
 * 发送消息 (HTTP 方式，非 WebSocket)
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
    `${MEMBER_API.CONVERSATIONS}/${conversationId}/messages`,
    {
      content,
      attachments,
      ...options,
    }
  );
  return response.data;
}
