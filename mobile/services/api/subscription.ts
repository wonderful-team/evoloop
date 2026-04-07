// 订阅和权益 API - 通过 Gateway 访问 member-center
// 链路: Mobile → Gateway (evoloop/backend) → member-center/backend

import { api } from './client';
import { MEMBER_API } from '@/constants/api';

/**
 * 获取订阅状态
 * GET /member/subscription/api/subscription/status
 */
export async function getSubscriptionStatus(): Promise<{
  has_subscription: boolean;
  level_id: number;
  status: string;
}> {
  const response = await api.get(MEMBER_API.SUBSCRIPTION_STATUS);
  return response.data;
}

/**
 * 获取订阅详情
 * GET /member/subscription/api/subscription/getDetail
 */
export async function getSubscriptionDetail(): Promise<{
  member_id: number;
  level_id: number;
  level_name: string;
  status: string;
  expire_time: number;
  is_member: number;
  remaining_days: number;
}> {
  const response = await api.get(MEMBER_API.SUBSCRIPTION_DETAIL);
  return response.data;
}

/**
 * 获取套餐列表
 * GET /member/subscription/api/subscription/plans
 */
export async function getSubscriptionPlans(): Promise<Array<{
  level_id: number;
  level_name: string;
  price: string;
  market_price: string;
  subscription_quota: number;
  description?: string;
  benefits: {
    ai_quota: number;
    ai_advanced: boolean;
    voice: boolean;
    project_limit: number;
    gantt: boolean;
    timesheet: boolean;
    sort: number;
  };
}>> {
  const response = await api.get(MEMBER_API.SUBSCRIPTION_PLANS);
  return response.data;
}

/**
 * 获取会员权益
 * GET /member/subscription/api/subscription/benefits
 */
export async function getMemberBenefits(forceRefresh = false): Promise<{
  member_id: number;
  level_id: number;
  level_name: string;
  is_expired: boolean;
  expire_time: number;
  remaining_days: number;
  benefits: {
    ai_quota: number;
    ai_advanced: boolean;
    voice: boolean;
    project_limit: number;
    gantt: boolean;
    timesheet: boolean;
    [key: string]: any;
  };
}> {
  const params = forceRefresh ? { force_refresh: true } : {};
  const response = await api.get(MEMBER_API.SUBSCRIPTION_BENEFITS, { params });
  return response.data;
}

/**
 * 检查单项权益
 * POST /member/subscription/api/subscription/checkBenefit
 */
export async function checkBenefit(benefitCode: string): Promise<{
  has_benefit: boolean;
  value: any;
  benefit_code: string;
  expire_time: number;
}> {
  const response = await api.post(MEMBER_API.SUBSCRIPTION_CHECK_BENEFIT, {
    code: benefitCode,
  });
  return response.data;
}

/**
 * 检查功能权限
 * POST /member/subscription/api/subscription/checkPermission
 */
export async function checkPermission(feature: string): Promise<{
  has_permission: boolean;
  required_level: string;
}> {
  const response = await api.post(MEMBER_API.SUBSCRIPTION_CHECK_PERMISSION, {
    feature,
  });
  return response.data;
}

/**
 * 计算升级价格
 * POST /member/subscription/api/plan/calculateUpgradePrice
 */
export async function calculateUpgradePrice(targetLevelId: number): Promise<{
  is_upgrade: boolean;
  pay_amount: string;
  refund_amount: string;
  net_amount: string;
}> {
  const response = await api.post(MEMBER_API.CALCULATE_UPGRADE, {
    target_level_id: targetLevelId,
  });
  return response.data;
}

/**
 * 创建订阅订单
 * POST /member/subscription/api/order/create
 */
export async function createOrder(data: {
  level_id: number;
  auto_renew?: number;
  app_type: 'app';
}): Promise<{
  order_id: string;
  out_trade_no: string;
  order: {
    order_no: string;
    order_money: string;
    level_name: string;
  };
  pay_data: {
    appid: string;
    partnerid: string;
    prepayid: string;
    noncestr: string;
    timestamp: string;
    package: 'Sign=WXPay';
    sign: string;
  };
}> {
  const response = await api.post(MEMBER_API.CREATE_ORDER, data);
  return response.data;
}

/**
 * 检查订单状态
 * GET /member/subscription/api/order/checkStatus
 */
export async function checkOrderStatus(orderId: string): Promise<{
  order_id: number;
  pay_status: number;
  pay_time: number;
  order_status: number;
}> {
  const response = await api.get(MEMBER_API.ORDER_STATUS, {
    params: { order_id: orderId },
  });
  return response.data;
}

/**
 * 取消订阅
 * POST /member/subscription/api/subscription/cancel
 */
export async function cancelSubscription(
  cancelType: 'expire' | 'now',
  reason?: string
): Promise<{ message: string }> {
  const response = await api.post(MEMBER_API.CANCEL_SUBSCRIPTION, {
    cancel_type: cancelType,
    reason,
  });
  return response.data;
}

/**
 * 获取 AI 配额
 * GET /member/subscription/api/aiQuota
 */
export async function getAIQuota(): Promise<{
  quota: number;
  quota_used: number;
  remaining: number;
  is_unlimited: boolean;
}> {
  const response = await api.get(MEMBER_API.AI_QUOTA);
  return response.data;
}

/**
 * 获取配额使用历史
 * GET /member/subscription/api/aiQuota/getUsageHistory
 */
export async function getQuotaUsageHistory(
  page = 1,
  pageSize = 20
): Promise<{
  list: Array<{
    count: number;
    source: string;
    deducted_at: number;
  }>;
  count: number;
}> {
  const response = await api.get(MEMBER_API.AI_QUOTA_HISTORY, {
    params: { page, page_size: pageSize },
  });
  return response.data;
}
