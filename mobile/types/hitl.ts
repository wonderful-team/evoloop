// HITL (Human-in-the-Loop) 类型定义
// 对应 Desktop 端的 humanRequest 机制

/**
 * HITL 请求类型
 * - text: 需要用户输入文本回答
 * - choice: 需要用户从选项中选择
 * - confirmation: 需要用户确认/取消 (是/否)
 * - approval: 需要用户批准/拒绝 (通过/不通过)
 */
export type HumanRequestType = 'text' | 'choice' | 'confirmation' | 'approval';

/**
 * 风险等级
 */
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

/**
 * HITL 请求上下文
 */
export interface HumanRequestContext {
  /** 风险等级 */
  risk_level?: RiskLevel;
  /** 操作描述 */
  action_description?: string;
  /** 详细内容 (支持 Markdown) */
  details?: string;
  /** 后果警告 */
  consequences?: string;
}

/**
 * HITL 人类请求
 * 对应 Desktop 端的 HumanRequest
 */
export interface HumanRequest {
  /** 请求唯一 ID */
  id: string;
  /** 请求类型 */
  type: HumanRequestType;
  /** 提示/问题 */
  prompt: string;
  /** 选项列表 (用于 choice 类型) */
  options?: string[];
  /** 默认值 */
  default_value?: string;
  /** 上下文信息 */
  context?: string | HumanRequestContext;
  /** 创建时间 */
  timestamp?: number;
  /** 超时时间 (毫秒) */
  timeout?: number;
}

/**
 * HITL 响应
 */
export interface HumanResponse {
  /** 对应请求的 ID */
  requestId: string;
  /** 响应值 */
  value: string;
  /** 响应时间 */
  timestamp: number;
}

/**
 * HITL 状态
 */
export interface HITLState {
  /** 当前待处理的请求 */
  currentRequest: HumanRequest | null;
  /** 请求历史 */
  requestHistory: HumanRequest[];
  /** 响应历史 */
  responseHistory: HumanResponse[];
  /** 是否正在等待用户输入 */
  isWaiting: boolean;
  /** 等待开始时间 */
  waitStartTime: number | null;
}

/**
 * HITL 配置选项
 */
export interface HITLOptions {
  /** 默认超时时间 (毫秒) */
  defaultTimeout?: number;
  /** 是否自动显示 HITL UI */
  autoShowUI?: boolean;
  /** 高风险操作是否强制确认 */
  forceConfirmHighRisk?: boolean;
}

/**
 * HITL 事件处理器
 */
export interface HITLHandlers {
  /** 收到新的 HITL 请求 */
  onRequest?: (request: HumanRequest) => void;
  /** 请求超时 */
  onTimeout?: (request: HumanRequest) => void;
  /** 用户提交响应 */
  onRespond?: (response: HumanResponse) => void;
  /** 请求被取消 */
  onCancel?: (requestId: string) => void;
}

/**
 * HITL 统计信息
 */
export interface HITLStats {
  /** 总请求数 */
  totalRequests: number;
  /** 已响应数 */
  respondedCount: number;
  /** 超时数 */
  timeoutCount: number;
  /** 平均响应时间 (毫秒) */
  averageResponseTime: number;
  /** 各类型请求分布 */
  typeDistribution: Record<HumanRequestType, number>;
}
