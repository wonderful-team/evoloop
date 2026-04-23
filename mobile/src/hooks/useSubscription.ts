// 订阅/会员管理 Hook
// 管理用户的订阅状态、套餐列表、权益信息

import { useCallback, useEffect, useState, useMemo, useRef } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { useLoading } from './useLoading';
import {
  getSubscriptionStatus,
  getSubscriptionDetail,
  getSubscriptionPlans,
  getMemberBenefits,
  createOrder,
  checkOrderStatus,
  cancelSubscription,
  calculateUpgradePrice,
  checkBenefit,
  checkPermission,
  type WechatPayParams,
} from '@/services/api/subscription';
import type { SubscriptionPlan, MemberBenefitsInfo } from '@/types/subscription';

// 缓存时间配置（毫秒）
const CACHE_TIME = {
  STATUS: 5 * 60 * 1000,      // 5分钟
  PLANS: 10 * 60 * 1000,      // 10分钟
  BENEFITS: 5 * 60 * 1000,    // 5分钟
};

// 内存缓存
const cache = {
  status: { data: null as any, timestamp: 0 },
  plans: { data: null as SubscriptionPlan[] | null, timestamp: 0 },
  benefits: { data: null as MemberBenefitsInfo | null, timestamp: 0 },
  detail: { data: null as any, timestamp: 0 },
};

/**
 * 订阅状态管理
 */
export function useSubscription() {
  const { isLoggedIn, userInfo } = useAuthStore();
  const [status, setStatus] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const hasFetchedRef = useRef(false);

  const { isLoading: isLoadingStatus, error: statusError, execute: executeStatus } = useLoading();
  const { isLoading: isLoadingDetail, error: detailError, execute: executeDetail } = useLoading();

  // 获取订阅状态
  const fetchStatus = useCallback(async (forceRefresh = false) => {
    if (!isLoggedIn) return null;
    
    // 检查缓存
    const now = Date.now();
    if (!forceRefresh && cache.status.data && now - cache.status.timestamp < CACHE_TIME.STATUS) {
      setStatus(cache.status.data);
      return cache.status.data;
    }
    
    const result = await executeStatus(getSubscriptionStatus());
    if (result) {
      cache.status = { data: result, timestamp: now };
      setStatus(result);
    }
    return result;
  }, [isLoggedIn, executeStatus]);

  // 获取订阅详情
  const fetchDetail = useCallback(async (forceRefresh = false) => {
    if (!isLoggedIn) return null;
    
    const now = Date.now();
    if (!forceRefresh && cache.detail.data && now - cache.detail.timestamp < CACHE_TIME.STATUS) {
      setDetail(cache.detail.data);
      return cache.detail.data;
    }
    
    const result = await executeDetail(getSubscriptionDetail());
    if (result) {
      cache.detail = { data: result, timestamp: now };
      setDetail(result);
    }
    return result;
  }, [isLoggedIn, executeDetail]);

  // 刷新所有订阅数据
  const refreshAll = useCallback(async () => {
    await Promise.all([fetchStatus(true), fetchDetail(true)]);
  }, [fetchStatus, fetchDetail]);

  // 初始加载 - 使用 ref 防止重复请求
  useEffect(() => {
    if (isLoggedIn && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      // 使用函数引用的稳定版本
      fetchStatus();
      fetchDetail();
    }
    // 登出时重置标记
    if (!isLoggedIn) {
      hasFetchedRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]); // 故意不依赖 fetchStatus/fetchDetail，避免无限循环

  // 计算属性
  const hasActiveSubscription = useMemo(() => {
    return detail?.is_member === 1 && (detail?.expire_time ?? 0) > Date.now() / 1000;
  }, [detail]);

  const isExpired = useMemo(() => {
    return detail?.is_member === 1 && (detail?.expire_time ?? 0) <= Date.now() / 1000;
  }, [detail]);

  return {
    // 状态
    status,
    detail,
    isLoading: isLoadingStatus || isLoadingDetail,
    error: statusError || detailError,
    
    // 计算属性
    hasActiveSubscription,
    isExpired,
    currentLevelId: detail?.level_id ?? 0,
    currentLevelName: detail?.level_name || '免费版',
    remainingDays: detail?.remaining_days ?? 0,
    expireTime: detail?.expire_time ?? 0,
    
    // 方法
    fetchStatus,
    fetchDetail,
    refreshAll,
  };
}

/**
 * 套餐列表
 */
export function useSubscriptionPlans() {
  const { isLoggedIn } = useAuthStore();
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const { isLoading, error, execute } = useLoading();
  const hasFetchedRef = useRef(false);

  const fetchPlans = useCallback(async (forceRefresh = false) => {
    if (!isLoggedIn) return [];

    // 检查缓存
    const now = Date.now();
    if (!forceRefresh && cache.plans.data && now - cache.plans.timestamp < CACHE_TIME.PLANS) {
      setPlans(cache.plans.data);
      return cache.plans.data;
    }

    const result = await execute(getSubscriptionPlans());
    if (result) {
      cache.plans = { data: result, timestamp: now };
      setPlans(result);
    }
    return result || [];
  }, [isLoggedIn, execute]);

  useEffect(() => {
    if (isLoggedIn && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchPlans();
    }
    if (!isLoggedIn) {
      hasFetchedRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]);

  return {
    plans,
    isLoading,
    error,
    fetchPlans,
    refresh: () => fetchPlans(true),
  };
}

/**
 * 会员权益
 */
export function useMemberBenefits() {
  const { isLoggedIn } = useAuthStore();
  const [benefits, setBenefits] = useState<MemberBenefitsInfo | null>(null);
  const { isLoading, error, execute } = useLoading();
  const hasFetchedRef = useRef(false);

  const fetchBenefits = useCallback(async (forceRefresh = false) => {
    if (!isLoggedIn) return null;

    // 检查缓存
    const now = Date.now();
    if (!forceRefresh && cache.benefits.data && now - cache.benefits.timestamp < CACHE_TIME.BENEFITS) {
      setBenefits(cache.benefits.data);
      return cache.benefits.data;
    }

    const result = await execute(getMemberBenefits(forceRefresh));
    if (result) {
      cache.benefits = { data: result, timestamp: now };
      setBenefits(result);
    }
    return result;
  }, [isLoggedIn, execute]);

  useEffect(() => {
    if (isLoggedIn && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchBenefits();
    }
    if (!isLoggedIn) {
      hasFetchedRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]);

  return {
    benefits,
    isLoading,
    error,
    fetchBenefits,
    refresh: () => fetchBenefits(true),
  };
}

/**
 * 检查是否为降级
 * 根据sort值判断：目标sort < 当前sort = 降级
 */
export function useIsDowngrade(targetLevelId: number | null) {
  const { plans } = useSubscriptionPlans();
  const { detail, hasActiveSubscription } = useSubscription();
  
  return useMemo(() => {
    if (!targetLevelId || !plans.length || !detail) {
      return {
        isDowngrade: false,
        isCurrentPlan: false,
        currentSort: 0,
        targetSort: 0,
        hasActiveSubscription: false,
      };
    }
    
    const currentSort = detail.level_info?.sort ?? detail.level_id ?? 0;
    
    // 查找目标套餐
    const targetPlan = plans.find(p => p.level_id === targetLevelId);
    const targetSort = targetPlan?.benefits?.sort ?? targetPlan?.level_id ?? 0;
    
    // 是当前套餐
    const isCurrentPlan = detail.level_id === targetLevelId && hasActiveSubscription;
    
    // 是降级：有活跃订阅且目标sort < 当前sort
    const isDowngrade = hasActiveSubscription && targetSort < currentSort;
    
    return {
      isDowngrade,
      isCurrentPlan,
      currentSort,
      targetSort,
      hasActiveSubscription,
    };
  }, [targetLevelId, plans, detail, hasActiveSubscription]);
}

/**
 * 创建订阅订单
 */
export function useCreateOrder() {
  const { execute, isLoading, error } = useLoading();

  const create = useCallback(async (data: {
    level_id: number;
    auto_renew?: number;
    app_type: 'app';
  }) => {
    return await execute(createOrder(data));
  }, [execute]);

  return {
    createOrder: create,
    isLoading,
    error,
  };
}

/**
 * 检查订单状态
 */
export function useOrderStatus(orderId: string) {
  const [status, setStatus] = useState<any>(null);
  const { isLoading, error, execute } = useLoading();

  const checkStatus = useCallback(async () => {
    if (!orderId) return null;
    const result = await execute(checkOrderStatus(orderId));
    if (result) {
      setStatus(result);
    }
    return result;
  }, [orderId, execute]);

  return {
    status,
    isLoading,
    error,
    checkStatus,
  };
}

/**
 * 取消订阅
 */
export function useCancelSubscription() {
  const { execute, isLoading, error } = useLoading();

  const cancel = useCallback(async (cancelType: 'expire' | 'now', reason?: string) => {
    return await execute(cancelSubscription(cancelType, reason));
  }, [execute]);

  return {
    cancelSubscription: cancel,
    isLoading,
    error,
  };
}

/**
 * 计算升级价格
 */
export function useUpgradePrice(targetLevelId: number) {
  const [priceInfo, setPriceInfo] = useState<any>(null);
  const { isLoading, error, execute } = useLoading();

  const calculate = useCallback(async () => {
    if (!targetLevelId) return null;
    const result = await execute(calculateUpgradePrice(targetLevelId));
    if (result) {
      setPriceInfo(result);
    }
    return result;
  }, [targetLevelId, execute]);

  useEffect(() => {
    if (targetLevelId) {
      calculate();
    }
  }, [targetLevelId, calculate]);

  return {
    priceInfo,
    isLoading,
    error,
    calculateUpgradePrice: calculate,
  };
}

/**
 * 清除所有订阅缓存
 * 用于登出或订阅状态变更后
 */
export function clearSubscriptionCache() {
  cache.status = { data: null, timestamp: 0 };
  cache.plans = { data: null, timestamp: 0 };
  cache.benefits = { data: null, timestamp: 0 };
  cache.detail = { data: null, timestamp: 0 };
}
