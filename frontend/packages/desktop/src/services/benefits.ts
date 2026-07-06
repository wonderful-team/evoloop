/**
 * 会员权益服务
 *
 * 提供权益相关的API调用和状态管理
 */

import i18n from "@evoloop/shared/i18n"
import { MemberService } from "@/client"
import type { FeatureCode } from "@/hooks/useFeatureAccess"

// 权益缓存
let benefitsCache: BenefitsCache | null = null
let cacheTimestamp = 0
const CACHE_TTL = 30 * 1000 // 30秒

interface BenefitsCache {
  benefits: Record<string, boolean>
  is_expired: boolean
  level_name: string
  expire_time?: number
  remaining_days?: number
}

/**
 * 获取会员权益
 * @param forceRefresh 是否强制刷新缓存
 */
export async function getMemberBenefits(
  forceRefresh = false,
): Promise<BenefitsCache> {
  // 检查缓存
  if (
    !forceRefresh &&
    benefitsCache &&
    Date.now() - cacheTimestamp < CACHE_TTL
  ) {
    return benefitsCache
  }

  const res = await MemberService.getMemberBenefitsApi({ forceRefresh })
  benefitsCache = (res as any).data as BenefitsCache
  cacheTimestamp = Date.now()

  return benefitsCache
}

/**
 * 批量检查权益
 */
export async function checkBenefitsBatch(
  features: FeatureCode[],
): Promise<Record<FeatureCode, boolean>> {
  const res = await MemberService.checkBenefitsBatch({
    benefit_codes: features,
  })

  return (res.data?.results || {}) as Record<FeatureCode, boolean>
}

/**
 * 清除权益缓存
 */
export function clearBenefitsCache(): void {
  benefitsCache = null
  cacheTimestamp = 0
}

/**
 * 检查特定权益
 */
export async function hasBenefit(feature: FeatureCode): Promise<boolean> {
  const data = await getMemberBenefits()
  return data.benefits?.[feature] === true && !data.is_expired
}

/**
 * 检查是否有任意一项权益
 */
export async function hasAnyBenefit(features: FeatureCode[]): Promise<boolean> {
  const data = await getMemberBenefits()
  if (data.is_expired) return false

  return features.some((f) => data.benefits?.[f] === true)
}

/**
 * 检查是否拥有所有指定权益
 */
export async function hasAllBenefits(
  features: FeatureCode[],
): Promise<boolean> {
  const data = await getMemberBenefits()
  if (data.is_expired) return false

  return features.every((f) => data.benefits?.[f] === true)
}

/**
 * 获取订阅状态
 */
export async function getSubscriptionStatus(): Promise<{
  isActive: boolean
  levelName: string
  remainingDays: number
  expireTime?: number
}> {
  const data = await getMemberBenefits()

  return {
    isActive: !data.is_expired,
    levelName: data.level_name || i18n.t("subscription.plans.free"),
    remainingDays: data.remaining_days || 0,
    expireTime: data.expire_time,
  }
}

/**
 * 预加载权益数据
 * 在应用启动时调用
 */
export function prefetchBenefits(): Promise<BenefitsCache> {
  return getMemberBenefits()
}

/**
 * 判断缓存是否过期
 */
export function isCacheExpired(): boolean {
  return !benefitsCache || Date.now() - cacheTimestamp > CACHE_TTL
}
