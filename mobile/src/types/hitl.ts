// HITL (Human-in-the-Loop) 类型定义

export type HumanRequestType = 'text' | 'choice' | 'confirmation' | 'approval';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface HumanRequest {
  id: string;
  type: HumanRequestType;
  prompt: string;
  options?: string[];
  default_value?: string;
  context?: string;
  risk_level?: RiskLevel;
  timestamp: number;
  timeout?: number;
}

export interface HumanResponse {
  requestId: string;
  value: string;
  timestamp: number;
}

export interface HITLOptions {
  defaultTimeout: number;
  autoShowUI: boolean;
  forceConfirmHighRisk: boolean;
}

export interface HITLState {
  currentRequest: HumanRequest | null;
  requestHistory: HumanRequest[];
  responseHistory: HumanResponse[];
  isWaiting: boolean;
  waitStartTime: number | null;
}

export interface HITLStats {
  total: number;
  responded: number;
  cancelled: number;
  timeout: number;
  averageResponseTime: number;
}
