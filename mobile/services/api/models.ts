// 模型管理 API - 通过 Gateway 访问
// 链路: Mobile → Gateway (evoloop/backend) → 模型服务

import { api } from './client';
import { GATEWAY_API } from '@/constants/api';
import {
  ModelInfo,
  ModelListResponse,
  UsageQuota,
  TokenUsage,
  ConversationTokenStats,
} from '@/types/model';

/**
 * 获取可用模型列表
 * GET /gateway/api/v1/models
 */
export async function getModels(): Promise<ModelListResponse> {
  const response = await api.get(GATEWAY_API.MODELS);
  return response.data;
}

/**
 * 获取模型详情
 * GET /gateway/api/v1/models/:id
 */
export async function getModel(modelId: string): Promise<ModelInfo> {
  const response = await api.get(`${GATEWAY_API.MODELS}/${modelId}`);
  return response.data;
}

/**
 * 获取用户配额信息
 * GET /gateway/api/v1/usage/quota
 */
export async function getUsageQuota(): Promise<UsageQuota> {
  const response = await api.get(GATEWAY_API.USAGE_QUOTA);
  return response.data;
}

/**
 * 获取 Token 使用量
 * GET /gateway/api/v1/usage/tokens
 */
export async function getTokenUsage(
  period: 'day' | 'week' | 'month' = 'day'
): Promise<{
  period: string;
  usage: TokenUsage;
  cost: number;
}> {
  const response = await api.get(`${GATEWAY_API.USAGE_TOKENS}?period=${period}`);
  return response.data;
}

/**
 * 获取对话的 Token 统计
 * GET /gateway/api/v1/conversations/:id/token-stats
 */
export async function getConversationTokenStats(
  conversationId: string
): Promise<ConversationTokenStats> {
  const response = await api.get(
    `${GATEWAY_API.CONVERSATION_DETAIL(conversationId)}/token-stats`
  );
  return response.data;
}

/**
 * 设置默认模型
 * POST /gateway/api/v1/models/default
 */
export async function setDefaultModel(modelId: string): Promise<void> {
  await api.post(`${GATEWAY_API.MODELS}/default`, { model_id: modelId });
}

/**
 * 检查模型可用性
 * GET /gateway/api/v1/models/:id/check
 */
export async function checkModelAvailability(modelId: string): Promise<{
  available: boolean;
  reason?: string;
  alternative_models?: string[];
}> {
  const response = await api.get(`${GATEWAY_API.MODELS}/${modelId}/check`);
  return response.data;
}
