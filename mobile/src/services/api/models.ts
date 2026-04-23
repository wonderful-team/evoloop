// 模型管理 API
// 架构：Mobile → MC (Member Center)

import { api } from './client';
import { MEMBER_API } from '@/constants/api';
import {
  ModelInfo,
  ModelListResponse,
  UsageQuota,
  TokenUsage,
  ConversationTokenStats,
} from '@/types/model';

/**
 * 获取可用模型列表
 * GET /member/api/models
 */
export async function getModels(): Promise<ModelListResponse> {
  const response = await api.get(`${MEMBER_API.BASE}/models`);
  return response.data;
}

/**
 * 获取模型详情
 * GET /member/api/models/:id
 */
export async function getModel(modelId: string): Promise<ModelInfo> {
  const response = await api.get(`${MEMBER_API.BASE}/models/${modelId}`);
  return response.data;
}

/**
 * 获取用户配额信息
 * GET /member/subscription/api/aiQuota
 */
export async function getUsageQuota(): Promise<UsageQuota> {
  const response = await api.get(MEMBER_API.AI_QUOTA);
  return response.data;
}

/**
 * 获取对话的 Token 统计
 * GET /member/api/conversations/:id/token-stats
 */
export async function getConversationTokenStats(
  conversationId: string
): Promise<ConversationTokenStats> {
  const response = await api.get(
    `${MEMBER_API.CONVERSATION_DETAIL(conversationId)}/token-stats`
  );
  return response.data;
}

/**
 * 设置默认模型
 * POST /member/api/models/default
 */
export async function setDefaultModel(modelId: string): Promise<void> {
  await api.post(`${MEMBER_API.BASE}/models/default`, { model_id: modelId });
}

/**
 * 检查模型可用性
 * GET /member/api/models/:id/check
 */
export async function checkModelAvailability(modelId: string): Promise<{
  available: boolean;
  reason?: string;
  alternative_models?: string[];
}> {
  const response = await api.get(`${MEMBER_API.BASE}/models/${modelId}/check`);
  return response.data;
}
