// 订阅/权益错误处理工具
// 统一处理 403 BENEFIT_REQUIRED 错误，显示升级提示

import { AxiosError } from 'axios';
import { AppError, ErrorCode } from './error';
import { router } from 'expo-router';

// 权益名称映射
export const BENEFIT_NAMES: Record<string, string> = {
  ai_quota: 'AI 调用额度',
  ai_advanced: '高级模型',
  voice: '语音交互',
  project_limit: '项目数量',
  gantt: '甘特图',
  timesheet: '工时表',
  desktop_control: '桌面控制',
  browser_control: '浏览器控制',
  mobile_control: '手机控制',
  skill_learning: '技能学习',
  wiki_generation: 'Wiki 生成',
  knowledge_base: '知识库',
};

// 订阅方案映射
export const PLAN_NAMES: Record<string, string> = {
  '创作者版': '创作者版',
  '极客版': '极客版',
  '专家版': '专家版',
  '企业版': '企业版',
  '免费版': '免费版',
};

// 权益错误信息接口
export interface BenefitErrorInfo {
  code: string;
  feature?: string;
  featureName?: string;
  requiredPlan?: string;
  message?: string;
  upgradeUrl?: string;
}

// 权益错误类
export class BenefitRequiredError extends AppError {
  public info: BenefitErrorInfo;
  
  constructor(info: BenefitErrorInfo) {
    super(
      info.message || `需要${info.requiredPlan || '订阅'}才能使用「${info.featureName || info.feature || '此功能'}」`,
      ErrorCode.BENEFIT_REQUIRED,
      403
    );
    this.info = info;
    this.name = 'BenefitRequiredError';
  }
}

/**
 * 检查是否为权益错误
 */
export function isBenefitError(data: any): boolean {
  if (!data) return false;
  
  // PHP 后端返回格式
  if (data.code === 'BENEFIT_REQUIRED' || data.code === 'SUBSCRIPTION_REQUIRED') {
    return true;
  }
  
  // detail 格式
  if (data.detail?.code === 'BENEFIT_REQUIRED' || data.detail?.code === 'SUBSCRIPTION_REQUIRED') {
    return true;
  }
  
  // message 包含关键词
  if (typeof data.message === 'string') {
    const msg = data.message.toLowerCase();
    return msg.includes('benefit') || msg.includes('subscription') || msg.includes('权益') || msg.includes('订阅');
  }
  
  return false;
}

/**
 * 从错误数据中提取权益信息
 */
export function extractBenefitInfo(data: any): BenefitErrorInfo {
  // PHP 后端格式
  if (data?.code === 'BENEFIT_REQUIRED') {
    return {
      code: 'BENEFIT_REQUIRED',
      feature: data.feature || data.data?.feature,
      featureName: data.feature_name || data.data?.feature_name || BENEFIT_NAMES[data.feature || data.data?.feature],
      requiredPlan: data.required_plan || data.data?.required_plan,
      message: data.message,
    };
  }
  
  // detail 格式
  if (data?.detail?.code === 'BENEFIT_REQUIRED') {
    return {
      code: 'BENEFIT_REQUIRED',
      feature: data.detail.feature,
      featureName: data.detail.feature_name || BENEFIT_NAMES[data.detail.feature],
      requiredPlan: data.detail.required_plan,
      message: data.detail.message,
    };
  }
  
  // SUBSCRIPTION_REQUIRED 格式
  if (data?.code === 'SUBSCRIPTION_REQUIRED' || data?.detail?.code === 'SUBSCRIPTION_REQUIRED') {
    const source = data.code === 'SUBSCRIPTION_REQUIRED' ? data : data.detail;
    return {
      code: 'SUBSCRIPTION_REQUIRED',
      feature: source.feature,
      featureName: BENEFIT_NAMES[source.feature],
      requiredPlan: source.required_plan,
      message: source.message,
    };
  }
  
  // 降级购买错误
  if (data?.message?.includes('降级') || data?.message?.includes('到期')) {
    return {
      code: 'DOWNGRADE_NOT_ALLOWED',
      message: data.message,
    };
  }
  
  return { code: 'UNKNOWN' };
}

/**
 * 处理权益错误
 * 返回错误信息对象，可用于显示 Toast 或 Alert
 */
export function handleBenefitError(data: any): {
  isBenefitError: boolean;
  title: string;
  message: string;
  action?: {
    label: string;
    onPress: () => void;
  };
} {
  if (!isBenefitError(data)) {
    return {
      isBenefitError: false,
      title: '错误',
      message: data?.message || '操作失败',
    };
  }
  
  const info = extractBenefitInfo(data);
  
  // 降级购买错误特殊处理
  if (info.code === 'DOWNGRADE_NOT_ALLOWED') {
    return {
      isBenefitError: true,
      title: '无法购买',
      message: info.message || '当前等级更高，到期后可购买此方案',
    };
  }
  
  const benefitName = info.featureName || BENEFIT_NAMES[info.feature || ''] || info.feature || '此功能';
  const planName = PLAN_NAMES[info.requiredPlan || ''] || info.requiredPlan || '更高等级';
  
  return {
    isBenefitError: true,
    title: `需要${planName}订阅`,
    message: `「${benefitName}」功能需要升级订阅才能使用`,
    action: {
      label: '立即升级',
      onPress: () => {
        router.push('/(subscription)/plans');
      },
    },
  };
}

/**
 * 检查 API 错误是否为权益错误
 * 用于响应拦截器
 */
export function checkIsBenefitError(error: unknown): boolean {
  if (error instanceof BenefitRequiredError) {
    return true;
  }
  
  if (error instanceof AxiosError && error.response?.status === 403) {
    return isBenefitError(error.response.data);
  }
  
  if (typeof error === 'object' && error !== null) {
    const err = error as any;
    if (err.statusCode === 403 || err.status === 403) {
      return isBenefitError(err.data) || isBenefitError(err);
    }
  }
  
  return false;
}

/**
 * 转换错误为 BenefitRequiredError
 */
export function convertToBenefitError(error: unknown): BenefitRequiredError | null {
  if (error instanceof BenefitRequiredError) {
    return error;
  }
  
  if (error instanceof AxiosError && error.response?.status === 403) {
    const info = extractBenefitInfo(error.response.data);
    if (info.code !== 'UNKNOWN') {
      return new BenefitRequiredError(info);
    }
  }
  
  return null;
}

// 导出统一处理函数
export const SubscriptionErrors = {
  isBenefitError,
  extractBenefitInfo,
  handleBenefitError,
  checkIsBenefitError,
  convertToBenefitError,
  BENEFIT_NAMES,
  PLAN_NAMES,
};
