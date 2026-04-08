// 功能权限检查 Hook
// 用于检查用户是否有权限使用某个功能

import { useCallback, useState, useEffect } from 'react';
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

// 权益名称映射
export const BENEFIT_NAMES: Record<string, string> = {
  [BENEFIT_CODES.AI_QUOTA]: 'AI 调用额度',
  [BENEFIT_CODES.AI_ADVANCED]: '高级模型',
  [BENEFIT_CODES.VOICE]: '语音交互',
  [BENEFIT_CODES.PROJECT_LIMIT]: '项目数量',
  [BENEFIT_CODES.GANTT]: '甘特图',
  [BENEFIT_CODES.TIMESHEET]: '工时表',
  [BENEFIT_CODES.DESKTOP_CONTROL]: '桌面控制',
  [BENEFIT_CODES.BROWSER_CONTROL]: '浏览器控制',
  [BENEFIT_CODES.MOBILE_CONTROL]: '手机控制',
  [BENEFIT_CODES.SKILL_LEARNING]: '技能学习',
  [BENEFIT_CODES.WIKI_GENERATION]: 'Wiki 生成',
  [BENEFIT_CODES.KNOWLEDGE_BASE]: '知识库',
};

// 权益到套餐的映射
export const BENEFIT_PLAN_MAP: Record<string, string> = {
  [BENEFIT_CODES.AI_QUOTA]: '探索者版',
  [BENEFIT_CODES.AI_ADVANCED]: '极客版',
  [BENEFIT_CODES.VOICE]: '极客版',
  [BENEFIT_CODES.PROJECT_LIMIT]: '探索者版',
  [BENEFIT_CODES.GANTT]: '企业版',
  [BENEFIT_CODES.TIMESHEET]: '企业版',
  [BENEFIT_CODES.DESKTOP_CONTROL]: '探索者版',
  [BENEFIT_CODES.BROWSER_CONTROL]: '探索者版',
  [BENEFIT_CODES.MOBILE_CONTROL]: '极客版',
  [BENEFIT_CODES.SKILL_LEARNING]: '极客版',
  [BENEFIT_CODES.WIKI_GENERATION]: '专家版',
  [BENEFIT_CODES.KNOWLEDGE_BASE]: '专家版',
};

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
  const { isLoggedIn } = useAuthStore();
  const { benefits, isLoading: isLoadingBenefits } = useMemberBenefits();
  const { detail, hasActiveSubscription } = useSubscription();
  const { checkBenefit, isLoading: isLoadingCheck } = useCheckBenefit();
  
  // 本地缓存的权益检查结果
  const [checkCache, setCheckCache] = useState<Record<string, boolean>>({});

  /**
   * 快速检查功能权限（基于本地缓存的权益数据）
   * 适用于非关键性检查（如UI显示控制）
   */
  const canUseFeature = useCallback((featureCode: string): boolean => {
    if (!isLoggedIn || !benefits) return false;
    
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
  }, [isLoggedIn, benefits]);

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
      benefitName: BENEFIT_NAMES[featureCode] || featureCode,
      requiredPlan: BENEFIT_PLAN_MAP[featureCode] || '更高等级',
    };
  }, [checkBenefit]);

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
    levelName: detail?.level_name || '免费版',
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
  };
}

/**
 * 检查特定功能的 Hook（适用于单个功能的详细检查）
 */
export function useFeature(featureCode: string) {
  const [hasAccess, setHasAccess] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const { checkFeatureStrict, canUseFeature } = useFeatureAccess();

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
    benefitName: BENEFIT_NAMES[featureCode] || featureCode,
    requiredPlan: BENEFIT_PLAN_MAP[featureCode] || '更高等级',
  };
}

/**
 * AI 配额检查
 */
export function useAIQuota() {
  const { benefits, isLoading } = useMemberBenefits();
  const { detail } = useSubscription();
  
  const quota = benefits?.benefits?.ai_quota ?? 0;
  const isUnlimited = quota === -1;
  const hasQuota = isUnlimited || quota > 0;
  
  return {
    quota,
    isUnlimited,
    hasQuota,
    isLoading,
    canUseAI: hasQuota,
  };
}

/**
 * 项目数量检查
 */
export function useProjectLimit() {
  const { benefits, isLoading } = useMemberBenefits();
  
  const limit = benefits?.benefits?.project_limit ?? 0;
  const isUnlimited = limit === -1;
  
  return {
    limit,
    isUnlimited,
    isLoading,
    canCreateProject: isUnlimited || limit > 0,
  };
}
