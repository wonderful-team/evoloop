import { toast } from 'sonner'
import { OpenAPI } from '@/client/core/OpenAPI.ts'
import type { AxiosResponse, AxiosError } from 'axios'
import i18n from '@evoloop/shared/i18n'

// 订阅方案映射到 i18n key
const PLAN_KEY_MAP: Record<string, string> = {
  '创作者版': 'creator',
  '极客版': 'geek',
  '专家版': 'expert',
  '企业版': 'enterprise',
}

/**
 * 初始化 API 拦截器
 * 统一处理权限错误（403）并显示友好的升级提示
 */
export function initApiInterceptors() {
  // 请求拦截器
  OpenAPI.interceptors.request.use((request) => {
    return request
  })

  // 响应拦截器 - 处理权限错误
  OpenAPI.interceptors.response.use((response: AxiosResponse) => {
    // 检查 403 状态码
    if (response.status === 403) {
      handleBenefitError(response.data)
    }
    return response
  })
}

/**
 * 检查是否为权益错误（不显示toast，只返回boolean）
 */
function checkIsBenefitError(data: any): boolean {
  return data?.detail?.code === 'BENEFIT_REQUIRED' ||
    data?.code === 'BENEFIT_REQUIRED' ||
    data?.code === 'SUBSCRIPTION_REQUIRED'
}

/**
 * 处理权益错误 - 显示升级提示
 * 注意：此函数只应在拦截器中调用一次
 */
function handleBenefitError(data: any): boolean {
  const isBenefitError = checkIsBenefitError(data)

  if (!isBenefitError) {
    // 处理其他403错误
    if (data?.detail?.message || data?.message) {
      toast.error(i18n.t('subscription.errors.insufficientPermission'), {
        description: data.detail?.message || data.message,
        duration: 3000,
      })
    }
    return false
  }

  // 提取错误信息
  const info = extractBenefitInfo(data)

  // 转换 benefit name
  const benefitName = i18n.t(`subscription.benefits.${info.feature}`, {
    defaultValue: info.featureName || info.feature || i18n.t('subscription.errors.featureFallback', '此功能')
  })

  // 转换 plan name
  const planKey = PLAN_KEY_MAP[info.requiredPlan || ''] || info.requiredPlan
  const planName = i18n.t(`subscription.plans.${planKey}`, {
    defaultValue: info.requiredPlan || i18n.t('subscription.plans.higher', '更高等级')
  })

  // 显示升级提示（只在这里显示一次）
  toast.error(
    i18n.t('subscription.errors.benefitRequired', { plan: planName, defaultValue: `需要${planName}订阅` }),
    {
      description: i18n.t('subscription.errors.benefitDescription', { feature: benefitName, defaultValue: `「${benefitName}」功能需要升级订阅才能使用` }),
      action: {
        label: i18n.t('subscription.errors.upgradeAction', '立即升级'),
        onClick: () => {
          window.location.hash = '#/subscription'
        }
      },
      duration: 5000,
    }
  )

  return true
}

/**
 * 从错误数据中提取权益信息
 */
function extractBenefitInfo(data: any): BenefitErrorInfo {
  // API层格式
  if (data?.detail?.code === 'BENEFIT_REQUIRED') {
    return {
      code: 'BENEFIT_REQUIRED',
      feature: data.detail.feature,
      featureName: data.detail.feature_name,
      requiredPlan: data.detail.required_plan,
      message: data.detail.message,
      upgradeUrl: data.detail.upgrade_url,
    }
  }

  // 工具层格式
  if (data?.code === 'BENEFIT_REQUIRED') {
    return {
      code: 'BENEFIT_REQUIRED',
      feature: data.feature,
      featureName: data.feature_name,
      requiredPlan: data.required_plan,
      message: data.message,
      upgradeUrl: data.upgrade_url,
    }
  }

  // 旧版格式
  if (data?.code === 'SUBSCRIPTION_REQUIRED') {
    return {
      code: 'SUBSCRIPTION_REQUIRED',
      feature: data.feature || data.detail?.feature,
      requiredPlan: data.required_plan || data.detail?.required_plan,
      message: data.message || data.detail?.message,
    }
  }

  return { code: 'UNKNOWN' }
}

// 权益错误信息接口
interface BenefitErrorInfo {
  code: string
  feature?: string
  featureName?: string
  requiredPlan?: string
  message?: string
  upgradeUrl?: string
}

// 自定义权益错误类
export class BenefitRequiredError extends Error {
  public info: BenefitErrorInfo

  constructor(info: BenefitErrorInfo) {
    super(info.message || '需要订阅才能使用此功能')
    this.name = 'BenefitRequiredError'
    this.info = info
  }
}

/**
 * 检查错误是否为权限错误
 */
export function isBenefitRequiredError(error: unknown): boolean {
  if (error instanceof BenefitRequiredError) {
    return true
  }
  if (error instanceof Error) {
    return error.message === 'BENEFIT_REQUIRED' ||
      error.name === 'BenefitRequiredError'
  }
  return false
}

/**
 * 获取权益错误信息
 */
export function getBenefitErrorInfo(error: unknown): BenefitErrorInfo | null {
  if (error instanceof BenefitRequiredError) {
    return error.info
  }
  return null
}

/**
 * 检查 API 错误是否为权益错误（只检查，不显示toast）
 * 用于组件中判断是否需要显示通用错误
 * 返回 true 表示是权益错误（已由拦截器处理），false 表示不是
 */
export function handleApiError(error: unknown): boolean {
  if (typeof error === 'object' && error !== null) {
    const axiosError = error as AxiosError

    if (axiosError.response?.status === 403) {
      return checkIsBenefitError(axiosError.response.data)
    }

    const apiError = error as any
    if (apiError.status === 403 || apiError.result?.status === 403) {
      const data = apiError.result?.body || apiError.body
      return checkIsBenefitError(data)
    }
  }

  return false
}
