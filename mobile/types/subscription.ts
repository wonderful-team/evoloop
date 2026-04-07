// 订阅/会员相关类型

export interface SubscriptionPlan {
  level_id: number;
  level_name: string;
  price: string;
  market_price: string;
  subscription_quota: number;
  description?: string;
  benefits: MemberBenefits;
}

export interface MemberBenefits {
  ai_quota: number;
  ai_advanced: boolean;
  voice: boolean;
  project_limit: number;
  gantt: boolean;
  timesheet: boolean;
  [key: string]: any;
}

export interface SubscriptionStatus {
  has_subscription: boolean;
  level_id: number;
  level_name: string;
  status: string;
  expire_time: number;
  is_member: number;
  remaining_days: number;
}

export interface CreateOrderRequest {
  level_id: number;
  period: 'month' | 'year';
}

export interface CreateOrderResponse {
  out_trade_no: string;
  pay_money: string;
  pay_body: string;
}

export interface PayRequest {
  out_trade_no: string;
  pay_type: 'wechatpay';
}

export interface WechatPayParams {
  partnerId: string;
  prepayId: string;
  nonceStr: string;
  timeStamp: string;
  package: string;
  sign: string;
}

export interface PayStatus {
  pay_status: 0 | 1 | 2; // 0:未支付, 1:支付中, 2:已支付
  pay_money: string;
}

export interface PayResult {
  success: boolean;
  outTradeNo: string;
  message?: string;
}

export interface UpgradePriceInfo {
  is_upgrade: boolean;
  pay_amount: string;
  refund_amount: string;
  net_amount: string;
}
