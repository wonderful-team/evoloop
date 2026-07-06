// 订阅/权益错误处理工具
// 统一处理 403 BENEFIT_REQUIRED 错误，显示升级提示

import { AxiosError } from 'axios';
import { AppError, ErrorCode } from './error';
import { router } from '@/utils/navigation';
import i18n from '@/locales';

// 权益名称映射
export function getBenefitNames(): Record<string, string> {
  return {
    ai_quota: i18n.t('subscription.benefits.aiQuota'),
    ai_advanced: i18n.t('subscription.benefits.aiAdvanced'),
    voice: i18n.t('subscription.benefits.voice'),
    project_limit: i18n.t('subscription.benefits.projectLimit'),
    gantt: i18n.t('subscription.benefits.gantt'),
    timesheet: i18n.t('subscription.benefits.timesheet'),
    desktop_control: i18n.t('subscription.benefits.desktopControl'),
    browser_control: i18n.t('subscription.benefits.browserControl'),
    mobile_control: i18n.t('subscription.benefits.mobileControl'),
    skill_learning: i18n.t('subscription.benefits.skillLearning'),
    wiki_generation: i18n.t('subscription.benefits.wikiGeneration'),
  };
}

// 订阅方案映射
export function getPlanNames(): Record<string, string> {
  return {
    '创作者版': i18n.t('subscription.plans.creator'),
    '极客版': i18n.t('subscription.plans.geek'),
    '专家版': i18n.t('subscription.plans.expert'),
    '企业版': i18n.t('subscription.plans.enterprise'),
    '免费版': i18n.t('subscription.plans.free'),
  };
}

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
    const benefitNames = getBenefitNames();
    const featureName = info.featureName || benefitNames[info.feature || ''] || info.feature || i18n.t('subscription.errors.thisFeature');
    super(
      info.message || i18n.t('subscription.errors.upgradeMessage', { benefitName: featureName }),
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
  if (!data) {
    return false;
  }

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
  const benefitNames = getBenefitNames();

  // PHP 后端格式
  if (data?.code === 'BENEFIT_REQUIRED') {
    return {
      code: 'BENEFIT_REQUIRED',
      feature: data.feature || data.data?.feature,
      featureName: data.feature_name || data.data?.feature_name || benefitNames[data.feature || data.data?.feature],
      requiredPlan: data.required_plan || data.data?.required_plan,
      message: data.message,
    };
  }

  // detail 格式
  if (data?.detail?.code === 'BENEFIT_REQUIRED') {
    return {
      code: 'BENEFIT_REQUIRED',
      feature: data.detail.feature,
      featureName: data.detail.feature_name || benefitNames[data.detail.feature],
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
      featureName: benefitNames[source.feature],
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
      title: i18n.t('subscription.errors.genericTitle'),
      message: data?.message || i18n.t('subscription.errors.genericMessage'),
    };
  }

  const info = extractBenefitInfo(data);

  // 降级购买错误特殊处理
  if (info.code === 'DOWNGRADE_NOT_ALLOWED') {
    return {
      isBenefitError: true,
      title: i18n.t('subscription.errors.downgradeNotAllowed'),
      message: info.message || i18n.t('subscription.errors.downgradeMessage'),
    };
  }

  const benefitNames = getBenefitNames();
  const planNames = getPlanNames();
  const benefitName = info.featureName || benefitNames[info.feature || ''] || info.feature || i18n.t('subscription.errors.thisFeature');
  const planName = planNames[info.requiredPlan || ''] || info.requiredPlan || i18n.t('subscription.errors.higherLevel');

  return {
    isBenefitError: true,
    title: i18n.t('subscription.errors.upgradeRequired', { planName }),
    message: i18n.t('subscription.errors.upgradeMessage', { benefitName }),
    action: {
      label: i18n.t('subscription.errors.upgradeNow'),
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
  getBenefitNames,
  getPlanNames,
};
