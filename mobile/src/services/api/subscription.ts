// 订阅和权益 API - 直接访问 member-center (PHP)
// 链路: Mobile → member-center/backend (PHP)

import { api } from './client';
import i18n from '@/locales';

// PHP 后端标准响应格式
interface PHPResponse<T> {
  code: number;
  data: T;
  message?: string;
}

// 提取数据，处理错误
function extractData<T>(response: PHPResponse<T>): T {
  if (response.code < 0) {
    throw new Error(response.message || i18n.t('api.errors.requestFailed'));
  }
  return response.data;
}

/**
 * 获取订阅状态
 * GET /member/subscription/api/subscription/status
 */
export async function getSubscriptionStatus(): Promise<{
  has_subscription: boolean;
  level_id: number;
  status: string;
}> {
  const response = await api.get<PHPResponse<any>>(`/member/subscription/api/subscription/status`);
  return extractData(response) || response;
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
  level_info?: {
    sort: number;
    [key: string]: any;
  };
}> {
  const response = await api.get<PHPResponse<any>>(`/member/subscription/api/subscription/getDetail`);
  return extractData(response) || response;
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
  purchasable?: number;
  period?: number;
  duration?: number;
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
  const response = await api.get<PHPResponse<any[]>>(`/member/subscription/api/subscription/plans`);
  return extractData(response) || response || [];
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
  const response = await api.get<PHPResponse<any>>(`/member/subscription/api/subscription/benefits`, { params });
  return extractData(response) || response;
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
  const response = await api.post<PHPResponse<any>>(`/member/subscription/api/subscription/checkBenefit`, {
    code: benefitCode,
  });
  return extractData(response) || response;
}

/**
 * 检查功能权限
 * POST /member/subscription/api/subscription/checkPermission
 */
export async function checkPermission(feature: string): Promise<{
  has_permission: boolean;
  required_level: string;
}> {
  const response = await api.post<PHPResponse<any>>(`/member/subscription/api/subscription/checkPermission`, {
    feature,
  });
  return extractData(response) || response;
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
  const response = await api.post<PHPResponse<any>>(`/member/subscription/api/plan/calculateUpgradePrice`, {
    target_level_id: targetLevelId,
  });
  return extractData(response) || response;
}

// 微信支付参数（APP支付）
export interface WechatPayParams {
  appid: string;
  partnerid: string;
  prepayid: string;
  noncestr: string;
  timestamp: string;
  package: 'Sign=WXPay';
  sign: string;
}

/**
 * 创建订阅订单
 * POST /member/subscription/api/order/create
 * 
 * 返回微信支付 APP 支付参数，可直接调起微信 SDK
 */
export async function createOrder(data: {
  level_id: number;
  auto_renew?: number;
  app_type: 'app';
  pay_type?: 'wechatpay';
}): Promise<{
  order_id: string;
  out_trade_no: string;
  order: {
    order_no: string;
    order_money: string;
    level_name: string;
  };
  // 微信支付 APP 支付参数
  pay_data: WechatPayParams;
}> {
  const response = await api.post<PHPResponse<any>>(`/member/subscription/api/order/create`, {
    ...data,
    pay_type: 'wechatpay',
  });
  return extractData(response) || response;
}

/**
 * 检查订单状态
 * GET /member/subscription/api/order/checkStatus
 */
export async function checkOrderStatus(orderId: string): Promise<{
  order_id: number;
  pay_status: number;  // 0:未支付, 1:已支付
  pay_time: number;
  order_status: number;
}> {
  const response = await api.get<PHPResponse<any>>(`/member/subscription/api/order/checkStatus`, {
    params: { order_id: orderId },
  });
  return extractData(response) || response;
}

/**
 * 取消订阅
 * POST /member/subscription/api/subscription/cancel
 */
export async function cancelSubscription(
  cancelType: 'expire' | 'now',
  reason?: string
): Promise<{ message: string }> {
  const response = await api.post<PHPResponse<any>>(`/member/subscription/api/subscription/cancel`, {
    cancel_type: cancelType,
    reason,
  });
  return extractData(response) || response;
}

/**
 * 获取 AI 配额
 * GET /member/subscription/api/aiQuota
 * 返回 getQuotaInfo 口径：total = 总额，used = 本周期已用，remaining = 剩余
 */
export async function getAIQuota(): Promise<{
  total: number;
  used: number;
  remaining: number;
  is_unlimited: boolean;
}> {
  const response = await api.get<PHPResponse<any>>(`/member/subscription/api/aiQuota/getQuota`);
  return extractData(response) || response;
}

/**
 * 获取配额（简化版，用于 quota store）
 */
export async function getQuota(): Promise<{
  total: number;
  used: number;
  remaining: number;
  reset_time?: string;
}> {
  const result = await getAIQuota();
  return {
    total: result.total,
    used: result.used,
    remaining: result.remaining,
  };
}

// 导出为对象，兼容原有导入方式
export const subscriptionApi = {
  getSubscriptionStatus,
  getSubscriptionDetail,
  getSubscriptionPlans,
  getMemberBenefits,
  checkBenefit,
  checkPermission,
  calculateUpgradePrice,
  createOrder,
  checkOrderStatus,
  cancelSubscription,
  getAIQuota,
  getQuota,
};

