export interface SubscriptionPlan {
  level_id: number;
  level_name: string;
  price: string;
  market_price: string;
  description?: string;
  privileges?: string[];
  is_current?: boolean;
  benefits?: Record<string, number | boolean | string>;
  definitions?: Record<string, { name: string; desc: string; category: string }>;
  sort?: number;
}

export interface SubscriptionDetail {
  level_id: number;
  level_name: string;
  expire_time: number;
  status: string;
  is_member: number;
  is_auto_renew: boolean;
  order_no?: string;
}

export interface AiQuota {
  total: number;
  used: number;
  remaining: number;
  is_unlimited: boolean;
}

export interface UpgradeInfo {
  pay_amount: string;
  refund_amount: string;
  net_amount: string;
}

export interface OrderInfo {
  order_id: string;
  order_no: string;
  level_id: number;
  level_name: string;
  order_money: string;
}

export interface OrderData {
  order: OrderInfo;
  qrcode: string;
  is_upgrade: boolean;
  upgrade_info?: UpgradeInfo;
}

export interface OrderStatus {
  order_id: string;
  is_paid: boolean;
  pay_time?: number;
}
