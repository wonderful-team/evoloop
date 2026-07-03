// HITL (Human-in-the-Loop) 状态管理

import { create } from 'zustand';
import {
  HumanRequest,
  HumanResponse,
  HITLState,
  HITLOptions,
  HITLStats,
  HumanRequestType,
} from '@/types/hitl';

interface HITLStore extends HITLState {
  // 配置
  options: HITLOptions;
  
  // Actions
  setOptions: (options: Partial<HITLOptions>) => void;
  setCurrentRequest: (request: HumanRequest | null) => void;
  addRequest: (request: HumanRequest) => void;
  addResponse: (response: HumanResponse) => void;
  respondToCurrent: (value: string) => void;
  cancelCurrent: (reason?: string) => void;
  timeoutCurrent: () => void;
  clearHistory: () => void;
  
  // 计算属性
  getStats: () => HITLStats;
  isHighRisk: () => boolean;
  getElapsedTime: () => number;
}

const defaultOptions: HITLOptions = {
  defaultTimeout: 5 * 60 * 1000, // 5分钟
  autoShowUI: true,
  forceConfirmHighRisk: true,
};

const initialState: HITLState = {
  currentRequest: null,
  requestHistory: [],
  responseHistory: [],
  isWaiting: false,
  waitStartTime: null,
};

export const useHITLStore = create<HITLStore>((set, get) => ({
  ...initialState,
  options: defaultOptions,

  // 设置配置
  setOptions: (options) => {
    set((state) => ({
      options: { ...state.options, ...options },
    }));
  },

  // 设置当前请求
  setCurrentRequest: (request) => {
    set({
      currentRequest: request,
      isWaiting: request !== null,
      waitStartTime: request !== null ? Date.now() : null,
    });
  },

  // 添加新请求
  addRequest: (request) => {
    const { requestHistory } = get();
    set({
      currentRequest: request,
      requestHistory: [...requestHistory, request],
      isWaiting: true,
      waitStartTime: Date.now(),
    });
  },

  // 添加响应
  addResponse: (response) => {
    const { responseHistory } = get();
    set({
      responseHistory: [...responseHistory, response],
    });
  },

  // 响应当前请求
  respondToCurrent: (value) => {
    const { currentRequest, addResponse, setCurrentRequest } = get();
    if (!currentRequest) return;

    const response: HumanResponse = {
      requestId: currentRequest.id,
      value,
      timestamp: Date.now(),
    };

    addResponse(response);
    setCurrentRequest(null);
  },

  // 取消当前请求
  cancelCurrent: (reason) => {
    const { currentRequest, setCurrentRequest } = get();
    if (!currentRequest) return;

    console.log(`[HITL] 请求已取消: ${currentRequest.id}, 原因: ${reason || '未知'}`);
    setCurrentRequest(null);
  },

  // 当前请求超时
  timeoutCurrent: () => {
    const { currentRequest, setCurrentRequest } = get();
    if (!currentRequest) return;

    console.log(`[HITL] 请求已超时: ${currentRequest.id}`);
    setCurrentRequest(null);
  },

  // 清空历史
  clearHistory: () => {
    set({
      requestHistory: [],
      responseHistory: [],
    });
  },

  // 获取统计信息
  getStats: () => {
    const { requestHistory, responseHistory } = get();
    
    const totalRequests = requestHistory.length;
    const respondedCount = responseHistory.length;
    const timeoutCount = requestHistory.filter(
      (req) => !responseHistory.some((resp) => resp.requestId === req.id)
    ).length;

    // 计算平均响应时间
    let totalResponseTime = 0;
    let validResponseCount = 0;
    responseHistory.forEach((resp) => {
      const req = requestHistory.find((r) => r.id === resp.requestId);
      if (req && req.timestamp) {
        totalResponseTime += resp.timestamp - req.timestamp;
        validResponseCount++;
      }
    });

    const averageResponseTime = validResponseCount > 0 
      ? totalResponseTime / validResponseCount 
      : 0;

    // 各类型分布
    const typeDistribution: Record<HumanRequestType, number> = {
      text: 0,
      choice: 0,
      confirmation: 0,
      approval: 0,
      project_switch: 0,
      file_select: 0,
    };
    requestHistory.forEach((req) => {
      typeDistribution[req.type]++;
    });

    return {
      totalRequests,
      respondedCount,
      timeoutCount,
      averageResponseTime,
      typeDistribution,
    };
  },

  // 判断当前请求是否为高风险
  isHighRisk: () => {
    const { currentRequest } = get();
    if (!currentRequest) return false;

    const context = currentRequest.context;
    if (typeof context === 'object' && context !== null) {
      return context.risk_level === 'high' || context.risk_level === 'critical';
    }
    return false;
  },

  // 获取已等待时间
  getElapsedTime: () => {
    const { waitStartTime } = get();
    if (!waitStartTime) return 0;
    return Date.now() - waitStartTime;
  },
}));
