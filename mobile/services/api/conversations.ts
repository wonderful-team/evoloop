// 会话管理 API - 通过 Gateway 访问
// 链路: Mobile → Gateway (evoloop/backend) → 各服务

import { api } from './client';
import { GATEWAY_API } from '@/constants/api';
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
 * GET /gateway/api/v1/conversations
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
  
  const response = await api.get(`${GATEWAY_API.CONVERSATIONS}?${params.toString()}`);
  return response.data;
}

/**
 * 创建新会话
 * POST /gateway/api/v1/conversations
 */
export async function createConversation(
  data: CreateConversationRequest
): Promise<CreateConversationResponse> {
  const response = await api.post(GATEWAY_API.CONVERSATIONS, data);
  return response.data;
}

/**
 * 获取会话详情
 * GET /gateway/api/v1/conversations/:id
 */
export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await api.get(GATEWAY_API.CONVERSATION_DETAIL(conversationId));
  return response.data;
}

/**
 * 删除会话
 * DELETE /gateway/api/v1/conversations/:id
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(GATEWAY_API.CONVERSATION_DETAIL(conversationId));
}

/**
 * 获取会话历史消息
 * GET /gateway/api/v1/conversations/:id/history
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
    `${GATEWAY_API.CONVERSATION_HISTORY(conversationId)}?${params.toString()}`
  );
  return response.data;
}

/**
 * 停止 Agent
 * POST /gateway/api/v1/conversations/:id/stop
 */
export async function stopAgent(conversationId: string): Promise<void> {
  await api.post(GATEWAY_API.CONVERSATION_STOP(conversationId));
}

/**
 * Rewind - 回退到指定消息
 * POST /gateway/api/v1/conversations/:id/rewind
 */
export async function rewindConversation(
  conversationId: string,
  request: RewindRequest
): Promise<RewindResponse> {
  const response = await api.post(
    GATEWAY_API.CONVERSATION_REWIND(conversationId),
    request
  );
  return response.data;
}

/**
 * Retry - 从指定消息重试
 * POST /gateway/api/v1/conversations/:id/retry
 */
export async function retryConversation(
  conversationId: string,
  request: RetryRequest
): Promise<RetryResponse> {
  const response = await api.post(
    GATEWAY_API.CONVERSATION_RETRY(conversationId),
    request
  );
  return response.data;
}

/**
 * 添加消息到记忆
 * POST /member/api/projects/:id/memory (通过 Gateway)
 */
export async function addToMemory(
  projectId: number,
  request: AddMemoryRequest
): Promise<MemoryConcept> {
  const response = await api.post(
    GATEWAY_API.PROJECT_MEMORY(projectId),
    request
  );
  return response.data;
}

/**
 * 获取项目记忆列表
 * GET /member/api/projects/:id/memory (通过 Gateway)
 */
export async function getMemories(projectId: number): Promise<MemoryConcept[]> {
  const response = await api.get(GATEWAY_API.PROJECT_MEMORY(projectId));
  return response.data;
}

/**
 * 发送消息 (HTTP 方式，非 WebSocket)
 * POST /gateway/api/v1/conversations/:id/messages
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
    `${GATEWAY_API.CONVERSATION_DETAIL(conversationId)}/messages`,
    {
      content,
      attachments,
      ...options,
    }
  );
  return response.data;
}
