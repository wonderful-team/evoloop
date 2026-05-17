import { useQuery, useQueryClient } from "@tanstack/react-query"
import { MemberService } from "@/client"

export type FeatureCode =
  | "browser_control"
  | "desktop_control"
  | "mobile_control"
  | "voice"
  | "skill_learning"
  | "wiki_generation"
  | "knowledge_base"
  | "gantt"
  | "timesheet"

const FEATURE_PLAN_MAP: Record<FeatureCode, string> = {
  wiki_generation: "creator",
  browser_control: "geek",
  voice: "geek",
  skill_learning: "geek",
  knowledge_base: "geek",
  desktop_control: "expert",
  mobile_control: "expert",
  gantt: "enterprise",
  timesheet: "enterprise",
}

// 权益标识映射（使用 i18n key，UI 层通过 t(`features.${key}`) 翻译）
const FEATURE_NAME_MAP: Record<FeatureCode, string> = {
  browser_control: "browserControl",
  desktop_control: "desktopControl",
  mobile_control: "mobileControl",
  voice: "voice",
  skill_learning: "skillLearning",
  wiki_generation: "wikiGeneration",
  knowledge_base: "knowledgeBase",
  gantt: "gantt",
  timesheet: "timesheet",
}

export interface FeatureAccessResult {
  hasAccess: boolean
  isExpired: boolean
  requiredPlan: string
  featureName: string
  canUse: boolean
  isLoading: boolean
}

export interface BenefitsData {
  benefits: Record<string, boolean>
  is_expired: boolean
  level_name: string
  expire_time?: number
  remaining_days?: number
}

// 查询配置常量
const BENEFITS_STALE_TIME = 30 * 1000 // 30秒内数据视为新鲜
const BENEFITS_CACHE_TIME = 5 * 60 * 1000 // 缓存5分钟

/**
 * 获取权益数据的通用查询配置
 */
function useBenefitsQueryConfig() {
  return {
    queryKey: ["member", "benefits"],
    queryFn: async (): Promise<BenefitsData> => {
      const res = await MemberService.getMemberBenefitsApi()
      return (res as any).data as BenefitsData
    },
    staleTime: BENEFITS_STALE_TIME,
    gcTime: BENEFITS_CACHE_TIME,
    // 错误时重试3次
    retry: 3,
    retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30000),
  }
}

/**
 * 单功能权限检查 Hook
 */
export function useFeatureAccess(feature: FeatureCode): FeatureAccessResult {
  const { data: benefitsData, isLoading } = useQuery(useBenefitsQueryConfig())

  const benefits = benefitsData?.benefits
  const isExpired = benefitsData?.is_expired ?? false
  const hasAccess = benefits?.[feature] === true && !isExpired

  return {
    hasAccess,
    isExpired,
    requiredPlan: FEATURE_PLAN_MAP[feature],
    featureName: FEATURE_NAME_MAP[feature],
    canUse: hasAccess,
    isLoading,
  }
}

/**
 * 多功能批量权限检查 Hook
 * 性能优化：只发起一次API请求
 */
export function useMultipleFeatureAccess(
  features: FeatureCode[]
): Record<FeatureCode, FeatureAccessResult> & { isLoading: boolean } {
  const { data: benefitsData, isLoading } = useQuery(useBenefitsQueryConfig())

  const benefits = benefitsData?.benefits
  const isExpired = benefitsData?.is_expired ?? false

  const results = {} as Record<FeatureCode, FeatureAccessResult>

  for (const feature of features) {
    const hasAccess = benefits?.[feature] === true && !isExpired
    results[feature] = {
      hasAccess,
      isExpired,
      requiredPlan: FEATURE_PLAN_MAP[feature],
      featureName: FEATURE_NAME_MAP[feature],
      canUse: hasAccess,
      isLoading,
    }
  }

  return { ...results, isLoading }
}

/**
 * 使用批量API检查多项权益
 * 适用于需要精确检查大量权益的场景
 */
export function useBatchFeatureCheck(features: FeatureCode[]) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["member", "benefits", "batch", features.sort().join(",")],
    queryFn: async () => {
      const res = await MemberService.checkBenefitsBatch({
        requestBody: { benefit_codes: features },
      })
      return res
    },
    staleTime: BENEFITS_STALE_TIME,
    enabled: features.length > 0,
  })

  const results = {} as Record<FeatureCode, FeatureAccessResult>
  
  for (const feature of features) {
    const hasAccess = data?.results?.[feature] ?? false
    const isExpired = data?.is_expired ?? false
    results[feature] = {
      hasAccess,
      isExpired,
      requiredPlan: FEATURE_PLAN_MAP[feature],
      featureName: FEATURE_NAME_MAP[feature],
      canUse: hasAccess && !isExpired,
      isLoading,
    }
  }

  return { 
    results, 
    isLoading, 
    error,
    levelName: data?.level_name 
  }
}

/**
 * 手动刷新权益缓存
 */
export function useRefreshBenefits() {
  const queryClient = useQueryClient()
  
  return {
    refresh: async () => {
      // 使缓存失效并重新获取
      await queryClient.invalidateQueries({ queryKey: ["member", "benefits"] })
    },
    refreshAsync: () => {
      // 后台刷新，不阻塞UI
      queryClient.invalidateQueries({ queryKey: ["member", "benefits"] })
    }
  }
}

/**
 * 预加载权益数据（在应用启动时调用）
 */
export function prefetchBenefits(queryClient: ReturnType<typeof useQueryClient>) {
  return queryClient.prefetchQuery(useBenefitsQueryConfig())
}

/**
 * 获取权益显示名称
 */
export function getFeatureName(feature: FeatureCode): string {
  return FEATURE_NAME_MAP[feature] || feature
}

/**
 * 获取权益所需套餐名称
 */
export function getFeatureRequiredPlan(feature: FeatureCode): string {
  return FEATURE_PLAN_MAP[feature] || "higher"
}

/**
 * 检查是否有任意一项权益
 */
export function useHasAnyFeature(features: FeatureCode[]): boolean {
  const access = useMultipleFeatureAccess(features)
  return Object.values(access).some(
    (r): r is FeatureAccessResult => typeof r === 'object' && r !== null && 'hasAccess' in r && r.hasAccess === true
  )
}

/**
 * 检查是否拥有所有指定权益
 */
export function useHasAllFeatures(features: FeatureCode[]): boolean {
  const access = useMultipleFeatureAccess(features)
  return Object.values(access).every(
    (r): r is FeatureAccessResult => typeof r !== 'object' || r === null || !('hasAccess' in r) || r.hasAccess === true
  )
}
