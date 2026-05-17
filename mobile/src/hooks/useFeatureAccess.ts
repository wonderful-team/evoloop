// 功能权限检查 Hook
// 用于检查用户是否有权限使用某个功能

import { useCallback, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useLoading } from './useLoading';
import { checkBenefit, checkPermission } from '@/services/api/subscription';
import { useSubscription, useMemberBenefits } from './useSubscription';

// 权益编码常量
export const BENEFIT_CODES = {
  // AI 相关
  AI_QUOTA: 'ai_quota',
  AI_ADVANCED: 'ai_advanced',
  
  // 功能权限
  VOICE: 'voice',
  PROJECT_LIMIT: 'project_limit',
  GANTT: 'gantt',
  TIMESHEET: 'timesheet',
  
  // 桌面端功能
  DESKTOP_CONTROL: 'desktop_control',
  BROWSER_CONTROL: 'browser_control',
  MOBILE_CONTROL: 'mobile_control',
  
  // 学习相关
  SKILL_LEARNING: 'skill_learning',
  WIKI_GENERATION: 'wiki_generation',
  KNOWLEDGE_BASE: 'knowledge_base',
} as const;

/**
 * 检查单项权益
 */
export function useCheckBenefit() {
  const { isLoggedIn } = useAuthStore();
  const { isLoading, error, execute } = useLoading();

  const check = useCallback(async (benefitCode: string) => {
    if (!isLoggedIn) {
      return { has_benefit: false, value: null, benefit_code: benefitCode, expire_time: 0 };
    }
    return await execute(checkBenefit(benefitCode));
  }, [isLoggedIn, execute]);

  return {
    checkBenefit: check,
    isLoading,
    error,
  };
}

/**
 * 检查功能权限
 */
export function useCheckPermission() {
  const { isLoggedIn } = useAuthStore();
  const { isLoading, error, execute } = useLoading();

  const check = useCallback(async (feature: string) => {
    if (!isLoggedIn) {
      return { has_permission: false, required_level: '' };
    }
    return await execute(checkPermission(feature));
  }, [isLoggedIn, execute]);

  return {
    checkPermission: check,
    isLoading,
    error,
  };
}

/**
 * 功能访问控制器
 * 统一封装功能权限检查，支持缓存和批量检查
 */
export function useFeatureAccess() {
  const { t } = useTranslation();
  const { isLoggedIn } = useAuthStore();
  const { benefits, isLoading: isLoadingBenefits } = useMemberBenefits();
  const { detail, hasActiveSubscription, isExpired } = useSubscription();
  const { checkBenefit, isLoading: isLoadingCheck } = useCheckBenefit();
  
  // 本地缓存的权益检查结果
  const [checkCache, setCheckCache] = useState<Record<string, boolean>>({});

  // 权益名称映射
  const getBenefitName = useCallback((code: string): string => {
    const map: Record<string, string> = {
      [BENEFIT_CODES.AI_QUOTA]: t('subscription.benefits.aiQuota'),
      [BENEFIT_CODES.AI_ADVANCED]: t('subscription.benefits.aiAdvanced'),
      [BENEFIT_CODES.VOICE]: t('subscription.benefits.voice'),
      [BENEFIT_CODES.PROJECT_LIMIT]: t('subscription.benefits.projectLimit'),
      [BENEFIT_CODES.GANTT]: t('subscription.benefits.gantt'),
      [BENEFIT_CODES.TIMESHEET]: t('subscription.benefits.timesheet'),
      [BENEFIT_CODES.DESKTOP_CONTROL]: t('subscription.benefits.desktopControl'),
      [BENEFIT_CODES.BROWSER_CONTROL]: t('subscription.benefits.browserControl'),
      [BENEFIT_CODES.MOBILE_CONTROL]: t('subscription.benefits.mobileControl'),
      [BENEFIT_CODES.SKILL_LEARNING]: t('subscription.benefits.skillLearning'),
      [BENEFIT_CODES.WIKI_GENERATION]: t('subscription.benefits.wikiGeneration'),
      [BENEFIT_CODES.KNOWLEDGE_BASE]: t('subscription.benefits.knowledgeBase'),
    };
    return map[code] || code;
  }, [t]);

  // 权益到套餐的映射
  const getBenefitPlan = useCallback((code: string): string => {
    const map: Record<string, string> = {
      [BENEFIT_CODES.AI_QUOTA]: t('subscription.plans.explorer'),
      [BENEFIT_CODES.AI_ADVANCED]: t('subscription.plans.geek'),
      [BENEFIT_CODES.VOICE]: t('subscription.plans.geek'),
      [BENEFIT_CODES.PROJECT_LIMIT]: t('subscription.plans.explorer'),
      [BENEFIT_CODES.GANTT]: t('subscription.plans.enterprise'),
      [BENEFIT_CODES.TIMESHEET]: t('subscription.plans.enterprise'),
      [BENEFIT_CODES.DESKTOP_CONTROL]: t('subscription.plans.explorer'),
      [BENEFIT_CODES.BROWSER_CONTROL]: t('subscription.plans.explorer'),
      [BENEFIT_CODES.MOBILE_CONTROL]: t('subscription.plans.geek'),
      [BENEFIT_CODES.SKILL_LEARNING]: t('subscription.plans.geek'),
      [BENEFIT_CODES.WIKI_GENERATION]: t('subscription.plans.expert'),
      [BENEFIT_CODES.KNOWLEDGE_BASE]: t('subscription.plans.expert'),
    };
    return map[code] || t('subscription.errors.higherLevel');
  }, [t]);

  /**
   * 快速检查功能权限（基于本地缓存的权益数据）
   * 适用于非关键性检查（如UI显示控制）
   */
  const canUseFeature = useCallback((featureCode: string): boolean => {
    if (!isLoggedIn || !benefits || isExpired) return false;
    
    // 从权益数据中检查
    const value = benefits.benefits?.[featureCode];
    
    // 布尔类型权益
    if (typeof value === 'boolean') {
      return value;
    }
    
    // 数值类型权益（如配额）
    if (typeof value === 'number') {
      return value > 0;
    }
    
    return false;
  }, [isLoggedIn, benefits, isExpired]);

  /**
   * 严格检查功能权限（请求后端确认）
   * 适用于关键操作前的权限确认
   */
  const checkFeatureStrict = useCallback(async (featureCode: string): Promise<{
    allowed: boolean;
    benefitName: string;
    requiredPlan: string;
  }> => {
    const result = await checkBenefit(featureCode);
    const hasBenefit = result?.has_benefit ?? false;
    
    // 更新缓存
    setCheckCache(prev => ({ ...prev, [featureCode]: hasBenefit }));
    
    return {
      allowed: hasBenefit,
      benefitName: getBenefitName(featureCode),
      requiredPlan: getBenefitPlan(featureCode),
    };
  }, [checkBenefit, getBenefitName, getBenefitPlan]);

  /**
   * 批量检查功能权限
   */
  const checkFeaturesBatch = useCallback(async (featureCodes: string[]): Promise<Record<string, boolean>> => {
    const results: Record<string, boolean> = {};
    
    await Promise.all(
      featureCodes.map(async (code) => {
        const result = await checkBenefit(code);
        results[code] = result?.has_benefit ?? false;
      })
    );
    
    setCheckCache(prev => ({ ...prev, ...results }));
    return results;
  }, [checkBenefit]);

  /**
   * 获取功能限制信息
   */
  const getFeatureLimit = useCallback((featureCode: string): {
    current: number;
    limit: number;
    isLimited: boolean;
  } => {
    if (!benefits) {
      return { current: 0, limit: 0, isLimited: true };
    }
    
    const value = benefits.benefits?.[featureCode];
    
    if (typeof value === 'number') {
      return {
        current: value,
        limit: value,
        isLimited: value <= 0,
      };
    }
    
    return { current: 0, limit: 0, isLimited: !value };
  }, [benefits]);

  /**
   * 检查是否为付费功能
   */
  const isPremiumFeature = useCallback((featureCode: string): boolean => {
    // 免费功能列表
    const freeFeatures = ['basic_chat', 'text_input'];
    return !freeFeatures.includes(featureCode);
  }, []);

  return {
    // 状态
    isLoading: isLoadingBenefits || isLoadingCheck,
    hasActiveSubscription,
    levelName: detail?.level_name || t('subscription.plans.free'),
    remainingDays: detail?.remaining_days || 0,
    expireTime: detail?.expire_time || 0,
    
    // 快速检查（本地）
    canUseFeature,
    getFeatureLimit,
    isPremiumFeature,
    
    // 严格检查（后端确认）
    checkFeatureStrict,
    checkFeaturesBatch,
    checkCache,
    
    // 名称映射
    getBenefitName,
    getBenefitPlan,
  };
}

/**
 * 检查特定功能的 Hook（适用于单个功能的详细检查）
 */
export function useFeature(featureCode: string) {
  const [hasAccess, setHasAccess] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const { checkFeatureStrict, canUseFeature, getBenefitName, getBenefitPlan } = useFeatureAccess();

  useEffect(() => {
    // 先使用本地缓存快速显示
    const localResult = canUseFeature(featureCode);
    setHasAccess(localResult);
    
    // 然后请求后端确认
    const verifyAccess = async () => {
      setIsChecking(true);
      try {
        const result = await checkFeatureStrict(featureCode);
        setHasAccess(result.allowed);
      } finally {
        setIsChecking(false);
      }
    };
    
    verifyAccess();
  }, [featureCode, canUseFeature, checkFeatureStrict]);

  return {
    hasAccess,
    isChecking,
    benefitName: getBenefitName(featureCode),
    requiredPlan: getBenefitPlan(featureCode),
  };
}

/**
 * AI 配额检查
 */
export function useAIQuota() {
  const { benefits, isLoading } = useMemberBenefits();
  const { detail, isExpired } = useSubscription();
  
  const quota = benefits?.benefits?.ai_quota ?? 0;
  const isUnlimited = quota === -1;
  const hasQuota = isUnlimited || quota > 0;
  
  return {
    quota,
    isUnlimited,
    hasQuota,
    isLoading,
    canUseAI: hasQuota && !isExpired,
  };
}

/**
 * 项目数量检查
 */
export function useProjectLimit() {
  const { benefits, isLoading } = useMemberBenefits();
  const { isExpired } = useSubscription();
  
  const limit = benefits?.benefits?.project_limit ?? 0;
  const isUnlimited = limit === -1;
  
  return {
    limit,
    isUnlimited,
    isLoading,
    canCreateProject: !isExpired && (isUnlimited || limit > 0),
  };
}
