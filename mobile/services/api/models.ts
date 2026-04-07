// 模型管理 API

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
 */
export async function getModels(): Promise<ModelListResponse> {
  const response = await api.get(MEMBER_API.MODELS);
  return response.data;
}

/**
 * 获取模型详情
 */
export async function getModel(modelId: string): Promise<ModelInfo> {
  const response = await api.get(`${MEMBER_API.MODELS}/${modelId}`);
  return response.data;
}

/**
 * 获取用户配额信息
 */
export async function getUsageQuota(): Promise<UsageQuota> {
  const response = await api.get(`${MEMBER_API.USAGE}/quota`);
  return response.data;
}

/**
 * 获取 Token 使用量
 */
export async function getTokenUsage(
  period: 'day' | 'week' | 'month' = 'day'
): Promise<{
  period: string;
  usage: TokenUsage;
  cost: number;
}> {
  const response = await api.get(`${MEMBER_API.USAGE}/tokens?period=${period}`);
  return response.data;
}

/**
 * 获取对话的 Token 统计
 */
export async function getConversationTokenStats(
  conversationId: string
): Promise<ConversationTokenStats> {
  const response = await api.get(
    `${MEMBER_API.CONVERSATIONS}/${conversationId}/token-stats`
  );
  return response.data;
}

/**
 * 设置默认模型
 */
export async function setDefaultModel(modelId: string): Promise<void> {
  await api.post(`${MEMBER_API.MODELS}/default`, { model_id: modelId });
}

/**
 * 检查模型可用性
 */
export async function checkModelAvailability(modelId: string): Promise<{
  available: boolean;
  reason?: string;
  alternative_models?: string[];
}> {
  const response = await api.get(`${MEMBER_API.MODELS}/${modelId}/check`);
  return response.data;
}
