// LLM 模型类型定义

/**
 * 模型信息
 */
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description?: string;
  capabilities: ModelCapability[];
  max_tokens: number;
  context_window: number;
  pricing: {
    input: number;
    output: number;
    unit: 'per_1k_tokens';
  };
  features: {
    streaming: boolean;
    function_calling: boolean;
    vision: boolean;
    json_mode: boolean;
  };
  status: 'active' | 'deprecated' | 'beta';
}

/**
 * 模型能力
 */
export type ModelCapability = 
  | 'chat'
  | 'completion'
  | 'embedding'
  | 'image_generation'
  | 'vision'
  | 'code'
  | 'reasoning';

/**
 * 模型列表响应
 */
export interface ModelListResponse {
  models: ModelInfo[];
  default_model: string;
}

/**
 * 用户使用量
 */
export interface UsageQuota {
  total_quota: number;
  used_quota: number;
  remaining_quota: number;
  unit: 'tokens' | 'credits';
  reset_date?: string;
  unlimited: boolean;
}

/**
 * Token 使用量
 */
export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost?: number;
}

/**
 * 对话 Token 统计
 */
export interface ConversationTokenStats {
  conversation_id: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  message_count: number;
  avg_tokens_per_message: number;
}
